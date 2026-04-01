"""EmbeddingsDB: armazenamento e busca de vetores para Cerebro"""

import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib


class EmbeddingsDB:
    """
    Banco de dados para embeddings vetoriais.

    Armazena vetores de embeddings gerados por modelos como
    sentence-transformers e oferece busca por similaridade.

    Nota: SQLite nativo não suporta operações vetoriais eficientes.
    Para produção, considerar sqlite-vec ou bancos vetoriais dedicados.
    Esta implementação usa armazenamento JSON + cálculo de similaridade
    em Python para demonstração.
    """

    def __init__(self, db_path: Path, model_name: str = "all-MiniLM-L6-v2"):
        """
        Inicializa o EmbeddingsDB.

        Args:
            db_path: Path para o arquivo do banco
            model_name: Nome do modelo sentence-transformers
        """
        self.db_path = db_path
        self.model_name = model_name
        self._model = None
        self._init_schema()

    @property
    def model(self):
        """Lazy load do modelo de embeddings"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers não instalado. "
                    "Instale com: pip install sentence-transformers"
                )
        return self._model

    def _connect(self) -> sqlite3.Connection:
        """Cria conexão com o banco"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self):
        """Cria schema do banco"""
        conn = self._connect()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id TEXT PRIMARY KEY,
                memory_id TEXT UNIQUE,
                type TEXT,
                project TEXT,
                embedding_json TEXT,
                content_hash TEXT,
                model_name TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (memory_id) REFERENCES memories(id)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_memory
            ON embeddings(memory_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_project
            ON embeddings(project)
        """)

        conn.commit()
        conn.close()

    def _compute_embedding(self, text: str) -> List[float]:
        """
        Computa embedding para texto.

        Args:
            text: Texto para embedar

        Returns:
            Lista de floats (vetor de embedding)
        """
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def _compute_hash(self, text: str) -> str:
        """
        Computa hash do conteúdo para cache.

        Args:
            text: Texto para hashear

        Returns:
            Hash SHA256 do texto
        """
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """
        Calcula similaridade cosseno entre dois vetores.

        Args:
            a: Primeiro vetor
            b: Segundo vetor

        Returns:
            Similaridade cosseno (0-1)
        """
        import math

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def upsert(
        self,
        memory_id: str,
        text: str,
        memory_type: str,
        project: str,
        force_recompute: bool = False
    ) -> str:
        """
        Insere ou atualiza embedding.

        Args:
            memory_id: ID da memória
            text: Texto para embedar
            memory_type: Tipo de memória (decision, error, etc)
            project: Nome do projeto
            force_recompute: Forçar recálculo mesmo com hash igual

        Returns:
            ID do embedding
        """
        content_hash = self._compute_hash(text)

        # Verifica se já existe embedding com mesmo hash
        if not force_recompute:
            existing = self.get_by_memory_id(memory_id)
            if existing and existing["content_hash"] == content_hash:
                return existing["id"]

        # Computa novo embedding
        embedding = self._compute_embedding(text)
        embedding_id = f"emb_{memory_id}"

        conn = self._connect()
        conn.execute("""
            INSERT OR REPLACE INTO embeddings
            (id, memory_id, type, project, embedding_json, content_hash, model_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            embedding_id,
            memory_id,
            memory_type,
            project,
            json.dumps(embedding),
            content_hash,
            self.model_name
        ))
        conn.commit()
        conn.close()

        return embedding_id

    def get_by_memory_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtém embedding por ID de memória.

        Args:
            memory_id: ID da memória

        Returns:
            Dados do embedding ou None
        """
        conn = self._connect()
        cursor = conn.execute(
            "SELECT * FROM embeddings WHERE memory_id = ?",
            (memory_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "id": row["id"],
                "memory_id": row["memory_id"],
                "type": row["type"],
                "project": row["project"],
                "embedding": json.loads(row["embedding_json"]),
                "content_hash": row["content_hash"],
                "model_name": row["model_name"],
                "created_at": row["created_at"]
            }
        return None

    def search_similar(
        self,
        query: str,
        project: Optional[str] = None,
        limit: int = 10,
        threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Busca memórias similares por similaridade de embeddings.

        Args:
            query: Texto de busca
            project: Filtrar por projeto (opcional)
            limit: Limite de resultados
            threshold: Threshold mínimo de similaridade

        Returns:
            Lista de memórias similares com score
        """
        # Computa embedding da query
        query_embedding = self._compute_embedding(query)

        conn = self._connect()

        # Carrega todos os embeddings (em produção, usar índice vetorial)
        if project:
            cursor = conn.execute(
                "SELECT * FROM embeddings WHERE project = ?",
                (project,)
            )
        else:
            cursor = conn.execute("SELECT * FROM embeddings")

        results = []
        for row in cursor.fetchall():
            stored_embedding = json.loads(row["embedding_json"])
            similarity = self._cosine_similarity(query_embedding, stored_embedding)

            if similarity >= threshold:
                results.append({
                    "memory_id": row["memory_id"],
                    "type": row["type"],
                    "project": row["project"],
                    "similarity": similarity,
                    "content_hash": row["content_hash"]
                })

        conn.close()

        # Ordena por similaridade e limita
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    def delete(self, memory_id: str) -> None:
        """
        Remove embedding.

        Args:
            memory_id: ID da memória
        """
        conn = self._connect()
        conn.execute(
            "DELETE FROM embeddings WHERE memory_id = ?",
            (memory_id,)
        )
        conn.commit()
        conn.close()

    def list_embeddings(self, project: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista embeddings.

        Args:
            project: Filtrar por projeto (opcional)

        Returns:
            Lista de embeddings (sem vetores)
        """
        conn = self._connect()

        if project:
            cursor = conn.execute(
                "SELECT id, memory_id, type, project, content_hash, model_name, created_at "
                "FROM embeddings WHERE project = ?",
                (project,)
            )
        else:
            cursor = conn.execute(
                "SELECT id, memory_id, type, project, content_hash, model_name, created_at "
                "FROM embeddings"
            )

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def get_stats(self) -> Dict[str, Any]:
        """
        Obtém estatísticas do banco.

        Returns:
            Dicionário com estatísticas
        """
        conn = self._connect()

        total = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        by_type = conn.execute(
            "SELECT type, COUNT(*) FROM embeddings GROUP BY type"
        ).fetchall()
        by_project = conn.execute(
            "SELECT project, COUNT(*) FROM embeddings GROUP BY project"
        ).fetchall()

        conn.close()

        return {
            "total_embeddings": total,
            "by_type": dict(by_type),
            "by_project": dict(by_project),
            "model_name": self.model_name
        }

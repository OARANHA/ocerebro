"""EmbeddingsDB: armazenamento e busca vetorial com sqlite-vec para Cerebro"""

import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib


class EmbeddingsDB:
    """
    Banco de dados para embeddings vetoriais usando sqlite-vec.

    Armazena vetores de embeddings gerados por modelos como
    sentence-transformers e oferece busca por similaridade com
    ANN (Approximate Nearest Neighbor) via sqlite-vec.

    sqlite-vec fornece:
    - Busca vetorial eficiente dentro do SQLite
    - Zero dependências externas
    - Ideal para centenas/milhares de vetores
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
        self._init_sqlite_vec()
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

    def _init_sqlite_vec(self):
        """Inicializa extensão sqlite-vec"""
        try:
            import sqlite_vec
            self._sqlite_vec_available = True
        except ImportError:
            self._sqlite_vec_available = False

    def _connect(self) -> sqlite3.Connection:
        """Cria conexão com o banco e carrega sqlite-vec"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")

        # Carrega extensão sqlite-vec se disponível
        if self._sqlite_vec_available:
            import sqlite_vec
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)

        return conn

    def _init_schema(self):
        """Cria schema do banco"""
        conn = self._connect()

        # Tabela de embeddings com suporte a vetor
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id TEXT PRIMARY KEY,
                memory_id TEXT UNIQUE,
                type TEXT,
                project TEXT,
                embedding BLOB,  -- sqlite-vec armazena como BLOB
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

        if self._sqlite_vec_available:
            # Usa sqlite-vec para armazenamento otimizado
            import sqlite_vec
            embedding_blob = sqlite_vec.serialize_float32(embedding)
        else:
            # Fallback para JSON
            embedding_blob = json.dumps(embedding)

        conn.execute("""
            INSERT OR REPLACE INTO embeddings
            (id, memory_id, type, project, embedding, content_hash, model_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            embedding_id,
            memory_id,
            memory_type,
            project,
            embedding_blob,
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
            # Desserializa embedding
            if self._sqlite_vec_available:
                import numpy as np
                embedding = np.frombuffer(row["embedding"], dtype=np.float32).tolist()
            else:
                embedding = json.loads(row["embedding"])

            return {
                "id": row["id"],
                "memory_id": row["memory_id"],
                "type": row["type"],
                "project": row["project"],
                "embedding": embedding,
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
        Busca memórias similares usando sqlite-vec ANN.

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

        if self._sqlite_vec_available:
            # Usa busca vetorial do sqlite-vec (ANN)
            import sqlite_vec
            query_blob = sqlite_vec.serialize_float32(query_embedding)

            # sqlite-vec usa similaridade de cosseno via operador MATCH
            if project:
                cursor = conn.execute("""
                    SELECT id, memory_id, type, project, content_hash,
                           vec_distance_cosine(embedding, ?) as distance
                    FROM embeddings
                    WHERE project = ?
                    ORDER BY distance ASC
                    LIMIT ?
                """, (query_blob, project, limit))
            else:
                cursor = conn.execute("""
                    SELECT id, memory_id, type, project, content_hash,
                           vec_distance_cosine(embedding, ?) as distance
                    FROM embeddings
                    ORDER BY distance ASC
                    LIMIT ?
                """, (query_blob, limit))

            results = []
            for row in cursor.fetchall():
                # sqlite-vec retorna distância (1 - similaridade)
                similarity = 1.0 - row["distance"]
                if similarity >= threshold:
                    results.append({
                        "memory_id": row["memory_id"],
                        "type": row["type"],
                        "project": row["project"],
                        "similarity": similarity,
                        "content_hash": row["content_hash"]
                    })
        else:
            # Fallback: carrega todos e calcula em Python
            import math

            if project:
                cursor = conn.execute(
                    "SELECT * FROM embeddings WHERE project = ?",
                    (project,)
                )
            else:
                cursor = conn.execute("SELECT * FROM embeddings")

            results = []
            for row in cursor.fetchall():
                stored_embedding = json.loads(row["embedding"])

                # Calcula similaridade cosseno manual
                dot_product = sum(x * y for x, y in zip(query_embedding, stored_embedding))
                norm_query = math.sqrt(sum(x * x for x in query_embedding))
                norm_stored = math.sqrt(sum(x * x for x in stored_embedding))

                if norm_query > 0 and norm_stored > 0:
                    similarity = dot_product / (norm_query * norm_stored)
                else:
                    similarity = 0.0

                if similarity >= threshold:
                    results.append({
                        "memory_id": row["memory_id"],
                        "type": row["type"],
                        "project": row["project"],
                        "similarity": similarity,
                        "content_hash": row["content_hash"]
                    })

        conn.close()
        return results

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
            "model_name": self.model_name,
            "sqlite_vec_available": self._sqlite_vec_available
        }

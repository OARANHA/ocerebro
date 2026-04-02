"""EntitiesDB: Grafo de experiência com entidades e relacionamentos"""

import sqlite3
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from datetime import datetime
from collections import deque


class EntitiesDB:
    """
    Banco de dados para grafo de experiência usando SQLite.

    Armazena entidades extraídas de memórias (ORG, PERSON, TECH, etc)
    e relacionamentos entre elas. Permite busca associativa por traversal.

    Diferencial vs LightRAG:
    - Extração local com spaCy NER (offline, grátis)
    - Frontmatter como nós iniciais (sem LLM)
    - Arestas implícitas por projeto/tags/type
    """

    def __init__(self, db_path: Path):
        """
        Inicializa o EntitiesDB.

        Args:
            db_path: Path para o arquivo do banco
        """
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        """Cria conexão com o banco"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self):
        """Cria schema do banco"""
        conn = self._connect()

        # Tabela de entidades
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                memory_id TEXT,
                entity_name TEXT,
                entity_type TEXT,
                confidence REAL DEFAULT 1.0,
                span_start INTEGER,
                span_end INTEGER,
                context_snippet TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (memory_id) REFERENCES memories(id)
            )
        """)

        # Índices para performance
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_entities_name
            ON entities(entity_name)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_entities_type
            ON entities(entity_type)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_entities_memory
            ON entities(memory_id)
        """)

        # Tabela de relacionamentos
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entity_relationships (
                id TEXT PRIMARY KEY,
                source_entity TEXT,
                target_entity TEXT,
                relationship_type TEXT,
                memory_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (memory_id) REFERENCES memories(id)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_source
            ON entity_relationships(source_entity)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_target
            ON entity_relationships(target_entity)
        """)

        conn.commit()
        conn.close()

    # ========================================================================
    # OPERAÇÕES DE ENTIDADES
    # ========================================================================

    def insert_entity(
        self,
        memory_id: str,
        entity_name: str,
        entity_type: str,
        confidence: float = 1.0,
        span_start: int = 0,
        span_end: int = 0,
        context_snippet: str = ""
    ) -> str:
        """
        Insere uma entidade.

        Args:
            memory_id: ID da memória de origem
            entity_name: Nome da entidade
            entity_type: Tipo (ORG, PERSON, TECH, etc)
            confidence: Confiança da extração (0-1)
            span_start: Posição inicial no texto
            span_end: Posição final no texto
            context_snippet: Contexto ao redor da entidade

        Returns:
            ID da entidade
        """
        entity_id = f"ent_{memory_id}_{entity_name.lower().replace(' ', '_')}"

        conn = self._connect()
        conn.execute("""
            INSERT OR REPLACE INTO entities
            (id, memory_id, entity_name, entity_type, confidence, span_start, span_end, context_snippet)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entity_id,
            memory_id,
            entity_name,
            entity_type,
            confidence,
            span_start,
            span_end,
            context_snippet
        ))
        conn.commit()
        conn.close()

        return entity_id

    def get_entities_by_memory(self, memory_id: str) -> List[Dict[str, Any]]:
        """
        Obtém entidades de uma memória.

        Args:
            memory_id: ID da memória

        Returns:
            Lista de entidades
        """
        conn = self._connect()
        cursor = conn.execute(
            "SELECT * FROM entities WHERE memory_id = ?",
            (memory_id,)
        )
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def get_entities_by_name(self, entity_name: str) -> List[Dict[str, Any]]:
        """
        Busca entidades por nome (case-insensitive).

        Args:
            entity_name: Nome da entidade

        Returns:
            Lista de entidades
        """
        conn = self._connect()
        cursor = conn.execute(
            "SELECT * FROM entities WHERE LOWER(entity_name) = LOWER(?)",
            (entity_name,)
        )
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def delete_entities_by_memory(self, memory_id: str) -> int:
        """
        Remove entidades de uma memória.

        Args:
            memory_id: ID da memória

        Returns:
            Número de entidades removidas
        """
        conn = self._connect()
        cursor = conn.execute(
            "DELETE FROM entities WHERE memory_id = ?",
            (memory_id,)
        )
        deleted = cursor.rowcount

        # Remove relacionamentos também
        conn.execute(
            "DELETE FROM entity_relationships WHERE memory_id = ?",
            (memory_id,)
        )

        conn.commit()
        conn.close()
        return deleted

    # ========================================================================
    # OPERAÇÕES DE RELACIONAMENTOS
    # ========================================================================

    def insert_relationship(
        self,
        source_entity: str,
        target_entity: str,
        relationship_type: str,
        memory_id: str
    ) -> str:
        """
        Insere relacionamento entre entidades.

        Args:
            source_entity: Nome da entidade origem
            target_entity: Nome da entidade alvo
            relationship_type: Tipo do relacionamento
            memory_id: ID da memória de origem

        Returns:
            ID do relacionamento
        """
        rel_id = f"rel_{source_entity}_{target_entity}_{memory_id}"

        conn = self._connect()
        conn.execute("""
            INSERT OR REPLACE INTO entity_relationships
            (id, source_entity, target_entity, relationship_type, memory_id)
            VALUES (?, ?, ?, ?, ?)
        """, (rel_id, source_entity, target_entity, relationship_type, memory_id))
        conn.commit()
        conn.close()

        return rel_id

    def get_relationships(self, entity_name: str) -> List[Dict[str, Any]]:
        """
        Obtém relacionamentos de uma entidade.

        Args:
            entity_name: Nome da entidade

        Returns:
            Lista de relacionamentos (ida e volta)
        """
        conn = self._connect()

        # Relacionamentos onde é origem
        cursor = conn.execute("""
            SELECT 'outgoing' as direction, r.*, e.entity_type as target_type
            FROM entity_relationships r
            LEFT JOIN entities e ON LOWER(e.entity_name) = LOWER(r.target_entity)
            WHERE LOWER(r.source_entity) = LOWER(?)
        """, (entity_name,))
        outgoing = [dict(row) for row in cursor.fetchall()]

        # Relacionamentos onde é alvo
        cursor = conn.execute("""
            SELECT 'incoming' as direction, r.*, e.entity_type as source_type
            FROM entity_relationships r
            LEFT JOIN entities e ON LOWER(e.entity_name) = LOWER(r.source_entity)
            WHERE LOWER(r.target_entity) = LOWER(?)
        """, (entity_name,))
        incoming = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return outgoing + incoming

    # ========================================================================
    # TRAVESSIA DO GRAFO (BFS)
    # ========================================================================

    def traverse(
        self,
        start_entity: str,
        depth: int = 2,
        entity_types: Optional[List[str]] = None,
        max_nodes: int = 50
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Faz traversal BFS a partir de uma entidade.

        Args:
            start_entity: Nome da entidade inicial
            depth: Profundidade máxima (1-3 recomendado)
            entity_types: Filtrar por tipos de entidade
            max_nodes: Limite máximo de nós retornados

        Returns:
            Tupla (nodes, edges) para visualização do grafo
        """
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []

        # Fila BFS: (entidade, profundidade)
        queue: deque = deque([(start_entity, 0)])
        visited: Set[str] = set()

        while queue and len(nodes) < max_nodes:
            entity_name, current_depth = queue.popleft()

            if entity_name in visited:
                continue
            visited.add(entity_name)

            # Busca entidade
            entities = self.get_entities_by_name(entity_name)
            if not entities:
                continue

            entity = entities[0]  # Pega primeiro match

            # Filtra por tipo se especificado
            if entity_types and entity["entity_type"] not in entity_types:
                continue

            # Adiciona nó
            node_key = entity["entity_name"].lower()
            if node_key not in nodes:
                nodes[node_key] = {
                    "name": entity["entity_name"],
                    "type": entity["entity_type"],
                    "depth": current_depth,
                    "memory_count": 1
                }
            else:
                nodes[node_key]["memory_count"] += 1

            # Se atingiu profundidade máxima, não expande
            if current_depth >= depth:
                continue

            # Busca relacionamentos
            relationships = self.get_relationships(entity_name)

            for rel in relationships:
                if rel["direction"] == "outgoing":
                    target = rel["target_entity"]
                    source = rel["source_entity"]
                else:
                    target = rel["target_entity"]
                    source = rel["source_entity"]

                # Adiciona aresta
                edge_key = f"{source.lower()}_{target.lower()}"
                if not any(e.get("key") == edge_key for e in edges):
                    edges.append({
                        "key": edge_key,
                        "source": source,
                        "target": target,
                        "type": rel["relationship_type"],
                        "memory_id": rel.get("memory_id")
                    })

                # Adiciona próximo nó na fila
                next_entity = target if rel["direction"] == "outgoing" else source
                if next_entity not in visited:
                    queue.append((next_entity, current_depth + 1))

        return list(nodes.values()), edges

    # ========================================================================
    # BUSCA POR ENTIDADES (integra com QueryEngine)
    # ========================================================================

    def search_by_query(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Busca memórias por entidades relacionadas à query.

        Extrai entidades da query e retorna memórias conectadas.

        Args:
            query: Texto de busca
            limit: Limite de resultados

        Returns:
            Lista de memórias com score de grafo
        """
        # Tenta extrair entidades da query (palavras-chave)
        query_entities = self._extract_query_entities(query)

        if not query_entities:
            return []

        # Busca memórias conectadas às entidades
        conn = self._connect()

        results = {}
        for entity_name in query_entities:
            cursor = conn.execute("""
                SELECT DISTINCT e.memory_id, e.entity_name, e.entity_type,
                       COUNT(*) as entity_count
                FROM entities e
                WHERE LOWER(e.entity_name) = LOWER(?)
                GROUP BY e.memory_id
                ORDER BY entity_count DESC
                LIMIT ?
            """, (entity_name, limit))

            for row in cursor.fetchall():
                memory_id = row["memory_id"]
                if memory_id not in results:
                    results[memory_id] = {
                        "memory_id": memory_id,
                        "matched_entities": [],
                        "score": 0.0
                    }

                results[memory_id]["matched_entities"].append({
                    "name": row["entity_name"],
                    "type": row["entity_type"]
                })
                results[memory_id]["score"] += 0.5  # Score base por entidade

        conn.close()

        # Normaliza scores
        if results:
            max_score = max(r["score"] for r in results.values())
            for r in results.values():
                r["score"] = r["score"] / max_score if max_score > 0 else 0

        return list(results.values())

    def _extract_query_entities(self, query: str) -> List[str]:
        """
        Extrai possíveis entidades de uma query.

        Usa heurísticas simples (sem spaCy para evitar dependência aqui):
        - Palavras capitalizadas
        - Termos entre aspas
        - Acrônimos

        Args:
            query: Texto de busca

        Returns:
            Lista de nomes de entidades candidatas
        """
        entities = set()

        # Termos entre aspas
        quoted = re.findall(r'"([^"]+)"', query)
        entities.update(quoted)

        # Palavras capitalizadas (prováveis nomes próprios)
        capitalized = re.findall(r'\b[A-Z][a-zA-Z]*\b', query)
        entities.update(capitalized)

        # Acrônimos
        acronyms = re.findall(r'\b[A-Z]{2,}\b', query)
        entities.update(acronyms)

        # Remove stop words e termos muito curtos
        stop_words = {"A", "O", "Os", "As", "Um", "Uma", "Em", "De", "Do", "Da", "Com", "Por", "Para"}
        entities = {e for e in entities if e not in stop_words and len(e) > 2}

        return list(entities)

    # ========================================================================
    # MÉTODOS DE INTEGRAÇÃO COM FRONTMATTER
    # ========================================================================

    def extract_from_frontmatter(
        self,
        memory_id: str,
        frontmatter: Dict[str, Any],
        project: str
    ) -> List[str]:
        """
        Extrai entidades do frontmatter de uma memória.

        Args:
            memory_id: ID da memória
            frontmatter: Dicionário com metadados
            project: Nome do projeto

        Returns:
            Lista de IDs de entidades criadas
        """
        entity_ids = []

        # Type como entidade
        if "type" in frontmatter:
            eid = self.insert_entity(
                memory_id,
                f"TYPE:{frontmatter['type']}",
                "META",
                confidence=1.0
            )
            entity_ids.append(eid)

        # Project como entidade
        if project:
            eid = self.insert_entity(
                memory_id,
                project,
                "PROJECT",
                confidence=1.0
            )
            entity_ids.append(eid)

        # Tags como entidades
        if "tags" in frontmatter:
            tags = frontmatter.get("tags", "")
            if isinstance(tags, str):
                for tag in [t.strip() for t in tags.split(",") if t.strip()]:
                    eid = self.insert_entity(
                        memory_id,
                        f"TAG:{tag}",
                        "TAG",
                        confidence=1.0
                    )
                    entity_ids.append(eid)
            elif isinstance(tags, list):
                for tag in tags:
                    eid = self.insert_entity(
                        memory_id,
                        f"TAG:{tag}",
                        "TAG",
                        confidence=1.0
                    )
                    entity_ids.append(eid)

        return entity_ids

    # ========================================================================
    # ESTATÍSTICAS
    # ========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """
        Obtém estatísticas do grafo.

        Returns:
            Dicionário com estatísticas
        """
        conn = self._connect()

        total_entities = conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0]

        total_relationships = conn.execute(
            "SELECT COUNT(*) FROM entity_relationships"
        ).fetchone()[0]

        by_type = conn.execute(
            "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type"
        ).fetchall()

        conn.close()

        return {
            "total_entities": total_entities,
            "total_relationships": total_relationships,
            "by_type": dict(by_type),
            "avg_relationships_per_entity": (
                total_relationships / total_entities if total_entities > 0 else 0
            )
        }

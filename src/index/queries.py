"""QueryEngine: consultas híbridas para Cerebro"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from .metadata_db import MetadataDB
from .embeddings_db import EmbeddingsDB
from .entities_db import EntitiesDB


@dataclass
class QueryResult:
    """Resultado de consulta"""
    memory_id: str
    type: str
    project: str
    title: str
    score: float
    source: str  # 'fts', 'semantic', 'metadata', 'graph'
    metadata: Dict[str, Any] = None


class QueryEngine:
    """
    Engine de consultas híbridas.

    Combina quatro tipos de busca:
    - Metadata: filtros estruturados (projeto, tipo, tags)
    - FTS: busca full-text no conteúdo
    - Semantic: busca por similaridade de embeddings
    - Graph: busca por entidades e relacionamentos
    """

    def __init__(
        self,
        metadata_db: MetadataDB,
        embeddings_db: EmbeddingsDB,
        entities_db: Optional[EntitiesDB] = None
    ):
        """
        Inicializa o QueryEngine.

        Args:
            metadata_db: Instância do MetadataDB
            embeddings_db: Instância do EmbeddingsDB
            entities_db: Instância do EntitiesDB (opcional)
        """
        self.metadata_db = metadata_db
        self.embeddings_db = embeddings_db
        self.entities_db = entities_db

    def search(
        self,
        query: str,
        project: Optional[str] = None,
        mem_type: Optional[str] = None,
        limit: int = 10,
        use_fts: bool = True,
        use_semantic: bool = True,
        use_graph: bool = True,
        fts_weight: float = 0.3,
        semantic_weight: float = 0.5,
        graph_weight: float = 0.2
    ) -> List[QueryResult]:
        """
        Busca híbrida combinando FTS, semantic e graph.

        Args:
            query: Texto de busca
            project: Filtrar por projeto
            mem_type: Filtrar por tipo
            limit: Limite de resultados
            use_fts: Usar busca FTS
            use_semantic: Usar busca semantic
            use_graph: Usar busca por graph
            fts_weight: Peso da busca FTS
            semantic_weight: Peso da busca semantic
            graph_weight: Peso da busca graph

        Returns:
            Lista de resultados ordenados por relevância
        """
        results: Dict[str, QueryResult] = {}

        # Busca FTS
        if use_fts:
            fts_results = self._search_fts(query, project, mem_type, limit)
            for r in fts_results:
                r.score *= fts_weight  # Aplica peso FTS desde o início
                results[r.memory_id] = r

        # Busca Semantic
        if use_semantic:
            semantic_results = self._search_semantic(query, project, limit)
            for r in semantic_results:
                if r.memory_id in results:
                    # Combina scores: média ponderada (FTS já tem peso aplicado)
                    existing = results[r.memory_id]
                    combined_score = existing.score + (r.score * semantic_weight)
                    results[r.memory_id] = QueryResult(
                        memory_id=r.memory_id,
                        type=r.type,
                        project=r.project,
                        title=r.title,
                        score=combined_score,
                        source="hybrid",
                        metadata=r.metadata
                    )
                else:
                    r.score *= semantic_weight
                    results[r.memory_id] = r

        # Busca por Graph (entidades)
        if use_graph and self.entities_db:
            graph_results = self._search_by_graph(query, limit)
            for r in graph_results:
                if r.memory_id in results:
                    # Combina scores: soma ponderada (scores anteriores já têm peso)
                    existing = results[r.memory_id]
                    combined_score = existing.score + (r.score * graph_weight)
                    results[r.memory_id] = QueryResult(
                        memory_id=r.memory_id,
                        type=r.type,
                        project=r.project,
                        title=r.title,
                        score=combined_score,
                        source="hybrid",
                        metadata=r.metadata
                    )
                else:
                    r.score *= graph_weight
                    results[r.memory_id] = r

        # Filtra por tipo se especificado
        if mem_type:
            results = {
                k: v for k, v in results.items()
                if v.type == mem_type
            }

        # Ordena por score e limita
        sorted_results = sorted(
            results.values(),
            key=lambda x: x.score,
            reverse=True
        )

        return sorted_results[:limit]

    def _search_fts(
        self,
        query: str,
        project: Optional[str],
        mem_type: Optional[str],
        limit: int
    ) -> List[QueryResult]:
        """
        Busca full-text.

        Args:
            query: Texto de busca
            project: Filtrar por projeto
            mem_type: Filtrar por tipo
            limit: Limite de resultados

        Returns:
            Lista de resultados
        """
        fts_results = self.metadata_db.search_fts(query, project)

        results = []
        for row in fts_results[:limit]:
            results.append(QueryResult(
                memory_id=row["id"],
                type=row["type"],
                project=row["project"],
                title=row.get("title", row["id"]),
                score=1.0,  # FTS não retorna score normalizado
                source="fts",
                metadata={
                    "tags": row.get("tags"),
                    "severity": row.get("severity"),
                    "access_count": row.get("access_count", 0)
                }
            ))

        return results

    def _search_semantic(
        self,
        query: str,
        project: Optional[str],
        limit: int
    ) -> List[QueryResult]:
        """
        Busca semântica por similaridade.

        Args:
            query: Texto de busca
            project: Filtrar por projeto
            limit: Limite de resultados

        Returns:
            Lista de resultados
        """
        try:
            similar = self.embeddings_db.search_similar(query, project, limit * 2)
        except (ImportError, Exception):
            # Busca semântica não disponível ou falhou
            return []

        results = []
        for item in similar:
            # Busca metadados adicionais
            memory = self.metadata_db.get_by_id(item["memory_id"])

            results.append(QueryResult(
                memory_id=item["memory_id"],
                type=item["type"],
                project=item["project"],
                title=memory.get("title", item["memory_id"]) if memory else item["memory_id"],
                score=item["similarity"],
                source="semantic",
                metadata={
                    "similarity": item["similarity"],
                    "content_hash": item.get("content_hash")
                }
            ))

        return results

    def _search_by_graph(
        self,
        query: str,
        limit: int
    ) -> List[QueryResult]:
        """
        Busca por entidades no grafo.

        Extrai entidades da query e retorna memórias conectadas.

        Args:
            query: Texto de busca
            limit: Limite de resultados

        Returns:
            Lista de resultados com score de grafo
        """
        if not self.entities_db:
            return []

        graph_results = self.entities_db.search_by_query(query, limit * 2)

        results = []
        for item in graph_results:
            # Busca metadados adicionais
            memory = self.metadata_db.get_by_id(item["memory_id"])

            results.append(QueryResult(
                memory_id=item["memory_id"],
                type=memory.get("type", "unknown") if memory else "unknown",
                project=memory.get("project", "unknown") if memory else "unknown",
                title=memory.get("title", item["memory_id"]) if memory else item["memory_id"],
                score=item["score"],
                source="graph",
                metadata={
                    "matched_entities": item.get("matched_entities", []),
                    "graph_score": item["score"]
                }
            ))

        return results

    def search_by_metadata(
        self,
        project: Optional[str] = None,
        mem_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_score: Optional[float] = None,
        limit: int = 50
    ) -> List[QueryResult]:
        """
        Busca apenas por metadados.

        Args:
            project: Filtrar por projeto
            mem_type: Filtrar por tipo
            tags: Filtrar por tags
            min_score: Score mínimo
            limit: Limite de resultados

        Returns:
            Lista de resultados
        """
        memories = self.metadata_db.search(project, mem_type)

        results = []
        for m in memories:
            # Filtra por tags
            if tags:
                memory_tags = (m.get("tags") or "").split(",")
                if not any(t in memory_tags for t in tags):
                    continue

            # Filtra por score
            if min_score and m.get("total_score", 0) < min_score:
                continue

            results.append(QueryResult(
                memory_id=m["id"],
                type=m["type"],
                project=m["project"],
                title=m.get("title", m["id"]),
                score=m.get("total_score", 0),
                source="metadata",
                metadata={
                    "tags": m.get("tags"),
                    "severity": m.get("severity"),
                    "access_count": m.get("access_count", 0),
                    "created_at": m.get("created_at"),
                    "updated_at": m.get("updated_at")
                }
            ))

            if len(results) >= limit:
                break

        return results

    def find_similar_to_memory(
        self,
        memory_id: str,
        limit: int = 5,
        threshold: float = 0.7
    ) -> List[QueryResult]:
        """
        Encontra memórias similares a uma memória específica.

        Args:
            memory_id: ID da memória de referência
            limit: Limite de resultados
            threshold: Threshold de similaridade

        Returns:
            Lista de memórias similares
        """
        # Obtém memória de referência
        memory = self.metadata_db.get_by_id(memory_id)
        if not memory:
            return []

        # Busca similares
        query = memory.get("title", "") + " " + (memory.get("content", "") or "")[:200]
        similar = self.embeddings_db.search_similar(
            query,
            memory.get("project"),
            limit + 1,
            threshold
        )

        # Remove a própria memória dos resultados
        similar = [s for s in similar if s["memory_id"] != memory_id]

        results = []
        for item in similar[:limit]:
            mem = self.metadata_db.get_by_id(item["memory_id"])
            results.append(QueryResult(
                memory_id=item["memory_id"],
                type=item["type"],
                project=item["project"],
                title=mem.get("title", item["memory_id"]) if mem else item["memory_id"],
                score=item["similarity"],
                source="semantic",
                metadata={"similarity": item["similarity"]}
            ))

        return results

    def get_related(
        self,
        memory_id: str,
        by_tags: bool = True,
        by_semantic: bool = True,
        limit: int = 10
    ) -> List[QueryResult]:
        """
        Obtém memórias relacionadas por múltiplos critérios.

        Args:
            memory_id: ID da memória
            by_tags: Buscar por tags similares
            by_semantic: Buscar por similaridade semântica
            limit: Limite de resultados

        Returns:
            Lista de memórias relacionadas
        """
        memory = self.metadata_db.get_by_id(memory_id)
        if not memory:
            return []

        related: Dict[str, QueryResult] = {}

        # Por tags
        if by_tags and memory.get("tags"):
            tags = memory["tags"].split(",")
            for tag in tags:
                tag_results = self.search_by_metadata(tags=[tag.strip()], limit=limit)
                for r in tag_results:
                    if r.memory_id != memory_id:
                        if r.memory_id not in related:
                            related[r.memory_id] = r
                        else:
                            related[r.memory_id].score += 0.1

        # Por similaridade semântica
        if by_semantic:
            semantic_results = self.find_similar_to_memory(memory_id, limit)
            for r in semantic_results:
                if r.memory_id not in related:
                    related[r.memory_id] = r

        # Ordena e limita
        sorted_related = sorted(
            related.values(),
            key=lambda x: x.score,
            reverse=True
        )

        return sorted_related[:limit]

    def is_semantic_available(self) -> bool:
        """
        Verifica se busca semântica está disponível.

        Returns:
            True se sentence-transformers está instalado e operacional, False caso contrário
        """
        return self.embeddings_db.is_semantic_available()

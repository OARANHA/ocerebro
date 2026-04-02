"""API endpoints para o Dashboard do OCerebro"""

from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
from typing import Any, Dict, List, Optional
import sqlite3
import json
from datetime import datetime


def create_router(
    metadata_db,
    embeddings_db,
    entities_db,
    cerebro_path: Path
) -> APIRouter:
    """Cria o router com todos os endpoints da API"""

    router = APIRouter(prefix="/api")

    # Store references to databases
    router.metadata_db = metadata_db
    router.embeddings_db = embeddings_db
    router.entities_db = entities_db
    router.cerebro_path = cerebro_path

    @router.get("/status")
    async def get_status():
        """Retorna status geral do sistema"""
        try:
            # Total de memórias
            conn = router.metadata_db._connect()
            total_memories = conn.execute(
                "SELECT COUNT(*) FROM memories"
            ).fetchone()[0]

            # Última atividade
            last_activity = conn.execute(
                "SELECT created_at FROM memories ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            last_activity = last_activity[0] if last_activity else None
            conn.close()

            # Stats do grafo
            graph_stats = router.entities_db.get_stats()

            # Projetos únicos
            conn = router.metadata_db._connect()
            projects = conn.execute(
                "SELECT COUNT(DISTINCT project) FROM memories"
            ).fetchone()[0]
            conn.close()

            return {
                "total_memories": total_memories,
                "total_entities": graph_stats["total_entities"],
                "total_relationships": graph_stats["total_relationships"],
                "projects": projects,
                "last_activity": last_activity
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/projects")
    async def get_projects():
        """Retorna lista de projetos com contagem de memórias"""
        try:
            conn = router.metadata_db._connect()

            # Projetos com contagem
            rows = conn.execute("""
                SELECT project, COUNT(*) as memory_count
                FROM memories
                GROUP BY project
                ORDER BY memory_count DESC
            """).fetchall()

            projects = []
            for row in rows:
                project = row["project"]

                # Contagem por tipo
                types_rows = conn.execute("""
                    SELECT type, COUNT(*) as count
                    FROM memories
                    WHERE project = ?
                    GROUP BY type
                """, (project,)).fetchall()

                types = {r["type"]: r["count"] for r in types_rows}

                projects.append({
                    "name": project,
                    "memory_count": row["memory_count"],
                    "types": types
                })

            conn.close()
            return projects
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/graph")
    async def get_graph(
        project: Optional[str] = Query(None),
        types: Optional[str] = Query(None)
    ):
        """Retorna grafo de entidades no formato Cytoscape.js"""
        try:
            # Parse tipos
            type_list = types.split(",") if types else None

            conn = router.entities_db._connect()

            # Busca entidades
            if project:
                if type_list:
                    placeholders = ",".join("?" * len(type_list))
                    query = f"""
                        SELECT DISTINCT e.id, e.entity_name, e.entity_type, e.memory_id
                        FROM entities e
                        WHERE e.entity_type IN ({placeholders})
                        AND EXISTS (
                            SELECT 1 FROM memories m
                            WHERE m.id = e.memory_id AND m.project = ?
                        )
                        LIMIT 100
                    """
                    params = type_list + [project]
                else:
                    query = """
                        SELECT DISTINCT e.id, e.entity_name, e.entity_type, e.memory_id
                        FROM entities e
                        WHERE EXISTS (
                            SELECT 1 FROM memories m
                            WHERE m.id = e.memory_id AND m.project = ?
                        )
                        LIMIT 100
                    """
                    params = [project]

                cursor = conn.execute(query, params)
            else:
                if type_list:
                    placeholders = ",".join("?" * len(type_list))
                    query = f"""
                        SELECT DISTINCT e.id, e.entity_name, e.entity_type, e.memory_id
                        FROM entities e
                        WHERE e.entity_type IN ({placeholders})
                        LIMIT 100
                    """
                    cursor = conn.execute(query, type_list)
                else:
                    cursor = conn.execute("""
                        SELECT DISTINCT e.id, e.entity_name, e.entity_type, e.memory_id
                        FROM entities e
                        LIMIT 100
                    """)

            entities = cursor.fetchall()

            # Constrói nós
            nodes = []
            entity_ids = set()
            for e in entities:
                entity_ids.add(e["entity_name"])
                nodes.append({
                    "data": {
                        "id": e["entity_name"],
                        "label": e["entity_name"],
                        "type": e["entity_type"],
                        "memory_id": e["memory_id"]
                    }
                })

            # Busca relacionamentos
            if entity_ids:
                placeholders = ",".join("?" * len(entity_ids))
                rels_query = f"""
                    SELECT source_entity, target_entity, relationship_type
                    FROM entity_relationships
                    WHERE source_entity IN ({placeholders})
                    OR target_entity IN ({placeholders})
                    LIMIT 500
                """
                cursor = conn.execute(rels_query, list(entity_ids) + list(entity_ids))
                rels = cursor.fetchall()

                edges = []
                for r in rels:
                    edges.append({
                        "data": {
                            "id": f"{r['source_entity']}_{r['target_entity']}",
                            "source": r["source_entity"],
                            "target": r["target_entity"],
                            "label": r["relationship_type"]
                        }
                    })
            else:
                edges = []

            conn.close()

            return {"nodes": nodes, "edges": edges}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/memories")
    async def get_memories(
        project: Optional[str] = Query(None),
        mem_type: Optional[str] = Query(None),
        q: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200)
    ):
        """Retorna lista de memórias com metadados"""
        try:
            if q:
                # Busca full-text usando método existente
                rows = router.metadata_db.search_fts(q, project)
                # Limita resultados
                rows = rows[:limit]
            else:
                # Busca com filtros
                conn = router.metadata_db._connect()
                query = "SELECT id, title, type, project, tags, created_at, updated_at FROM memories WHERE 1=1"
                params = []

                if project:
                    query += " AND project = ?"
                    params.append(project)

                if mem_type:
                    query += " AND type = ?"
                    params.append(mem_type)

                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(query, params).fetchall()
                conn.close()

            memories = []
            for row in rows:
                # Calcula GC risk
                from src.forgetting.gc import calculate_rfms_score
                memory_dict = dict(row)
                gc_risk = 1.0 - calculate_rfms_score(memory_dict)

                memories.append({
                    "id": memory_dict["id"],
                    "title": memory_dict["title"] or memory_dict["id"],
                    "type": memory_dict["type"],
                    "project": memory_dict["project"],
                    "tags": memory_dict["tags"].split(",") if memory_dict["tags"] else [],
                    "created_at": memory_dict["created_at"],
                    "updated_at": memory_dict["updated_at"],
                    "gc_risk": round(gc_risk, 2)
                })

            return memories
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/memory/{memory_id}")
    async def get_memory(memory_id: str):
        """Retorna conteúdo completo de uma memória"""
        try:
            # Busca metadados
            memory = router.metadata_db.get_by_id(memory_id)
            if not memory:
                raise HTTPException(status_code=404, detail="Memória não encontrada")

            # Tenta encontrar o arquivo .md
            content = ""

            # Procura em official/
            official_path = router.cerebro_path / "official"
            if official_path.exists():
                # Procura recursivamente
                for md_file in official_path.rglob(f"{memory_id}.md"):
                    content = md_file.read_text(encoding="utf-8")
                    break

                # Se não achou, procura em working/
                if not content:
                    working_path = router.cerebro_path / "working"
                    for yaml_file in working_path.rglob(f"{memory_id}.yaml"):
                        content = yaml_file.read_text(encoding="utf-8")
                        break

                # Se ainda não achou, procura em raw/
                if not content:
                    raw_path = router.cerebro_path / "raw"
                    for jsonl_file in raw_path.rglob("*.jsonl"):
                        with open(jsonl_file, "r", encoding="utf-8") as f:
                            for line in f:
                                event = json.loads(line)
                                if event.get("id") == memory_id:
                                    content = f"# {memory_id}\n\n```json\n{json.dumps(event, indent=2)}\n```"
                                    break

            # Fallback: tenta auto memory
            if not content:
                from src.core.paths import get_auto_mem_path
                auto_path = get_auto_mem_path()
                for md_file in auto_path.rglob(f"{memory_id}.md"):
                    content = md_file.read_text(encoding="utf-8")
                    break

            return {
                "id": memory_id,
                "content": content,
                "metadata": memory
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/timeline")
    async def get_timeline(
        project: Optional[str] = Query(None),
        days: int = Query(30, ge=1, le=90)
    ):
        """Retorna dados para timeline agrupados por dia"""
        try:
            conn = router.metadata_db._connect()

            if project:
                query = """
                    SELECT DATE(created_at) as date, type, COUNT(*) as count
                    FROM memories
                    WHERE project = ?
                    AND created_at >= DATE('now', ?)
                    GROUP BY DATE(created_at), type
                    ORDER BY date
                """
                params = (project, f"-{days} days")
            else:
                query = """
                    SELECT DATE(created_at) as date, type, COUNT(*) as count
                    FROM memories
                    WHERE created_at >= DATE('now', ?)
                    GROUP BY DATE(created_at), type
                    ORDER BY date
                """
                params = (f"-{days} days",)

            rows = conn.execute(query, params).fetchall()
            conn.close()

            # Agrupa por data
            by_date = {}
            types_set = set()

            for row in rows:
                date = row["date"]
                mem_type = row["type"]
                count = row["count"]

                if date not in by_date:
                    by_date[date] = {}

                by_date[date][mem_type] = count
                types_set.add(mem_type)

            # Formata para Chart.js
            labels = sorted(by_date.keys())
            datasets = []

            colors = {
                "decision": "#3B82F6",
                "error": "#EF4444",
                "reference": "#10B981",
                "feedback": "#F59E0B",
                "default": "#6366F1"
            }

            for mem_type in sorted(types_set):
                data = [by_date.get(date, {}).get(mem_type, 0) for date in labels]
                color = colors.get(mem_type, colors["default"])

                datasets.append({
                    "label": mem_type,
                    "data": data,
                    "borderColor": color,
                    "backgroundColor": color + "40",  # 25% opacity
                    "tension": 0.3,
                    "fill": True
                })

            return {"labels": labels, "datasets": datasets}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router

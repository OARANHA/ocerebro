"""MCP Server do Cerebro: Integração com Claude Code"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.core.jsonl_storage import JSONLStorage
from src.core.session_manager import SessionManager
from src.working.yaml_storage import YAMLStorage
from src.working.memory_view import MemoryView
from src.official.markdown_storage import MarkdownStorage
from src.consolidation.extractor import Extractor
from src.consolidation.promoter import Promoter
from src.index.metadata_db import MetadataDB
from src.index.embeddings_db import EmbeddingsDB
from src.index.queries import QueryEngine


class CerebroMCP:
    """
    MCP Server para integração do Cerebro com Claude Code.

    Ferramentas disponíveis:
    - cerebro_memory: Visualizar memória ativa
    - cerebro_search: Buscar memórias
    - cerebro_checkpoint: Criar checkpoint manual
    - cerebro_promote: Promover draft para official
    - cerebro_status: Status do sistema
    """

    def __init__(self, cerebro_path: Optional[Path] = None):
        """
        Inicializa o MCP Server.

        Args:
            cerebro_path: Diretório base do Cerebro (default: .cerebro)
        """
        self.cerebro_path = cerebro_path or Path(".cerebro")
        self.cerebro_path.mkdir(parents=True, exist_ok=True)

        # Inicializa componentes
        self.raw_storage = JSONLStorage(self.cerebro_path / "raw")
        self.working_storage = YAMLStorage(self.cerebro_path / "working")
        self.official_storage = MarkdownStorage(self.cerebro_path / "official")
        self.session_manager = SessionManager(self.cerebro_path)

        self.metadata_db = MetadataDB(self.cerebro_path / "index" / "metadata.db")
        self.embeddings_db = EmbeddingsDB(self.cerebro_path / "index" / "embeddings.db")
        self.query_engine = QueryEngine(self.metadata_db, self.embeddings_db)

        self.extractor = Extractor(self.raw_storage, self.working_storage)
        self.promoter = Promoter(self.working_storage, self.official_storage)

        self.memory_view = MemoryView(
            self.cerebro_path,
            self.official_storage,
            self.working_storage
        )

    def get_tools(self) -> List[Tool]:
        """
        Retorna lista de ferramentas MCP.

        Returns:
            Lista de ferramentas disponíveis
        """
        return [
            Tool(
                name="cerebro_memory",
                description="Visualizar memória ativa do projeto (MEMORY.md)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome do projeto"
                        }
                    },
                    "required": ["project"]
                }
            ),
            Tool(
                name="cerebro_search",
                description="Buscar memórias por texto, tags ou metadados",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Texto de busca"
                        },
                        "project": {
                            "type": "string",
                            "description": "Filtrar por projeto"
                        },
                        "type": {
                            "type": "string",
                            "description": "Tipo (decision, error, etc)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Limite de resultados",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="cerebro_checkpoint",
                description="Criar checkpoint manual de uma sessão",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome do projeto"
                        },
                        "session_id": {
                            "type": "string",
                            "description": "ID da sessão (opcional, usa atual)"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Motivo do checkpoint",
                            "default": "manual"
                        }
                    },
                    "required": ["project"]
                }
            ),
            Tool(
                name="cerebro_promote",
                description="Promover draft da working layer para official",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome do projeto"
                        },
                        "draft_id": {
                            "type": "string",
                            "description": "ID do draft"
                        },
                        "draft_type": {
                            "type": "string",
                            "description": "Tipo do draft",
                            "default": "session"
                        },
                        "promote_to": {
                            "type": "string",
                            "description": "Tipo de destino",
                            "default": "decision"
                        }
                    },
                    "required": ["project", "draft_id"]
                }
            ),
            Tool(
                name="cerebro_status",
                description="Obter status do sistema Cerebro",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            )
        ]

    async def handle_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """
        Processa chamada de ferramenta.

        Args:
            name: Nome da ferramenta
            arguments: Argumentos da chamada

        Returns:
            Resultado como lista de TextContent
        """
        try:
            if name == "cerebro_memory":
                result = self._memory(arguments)
            elif name == "cerebro_search":
                result = self._search(arguments)
            elif name == "cerebro_checkpoint":
                result = self._checkpoint(arguments)
            elif name == "cerebro_promote":
                result = self._promote(arguments)
            elif name == "cerebro_status":
                result = self._status()
            else:
                return [TextContent(type="text", text=f"Ferramenta desconhecida: {name}")]

            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Erro: {str(e)}")]

    def _memory(self, args: Dict[str, Any]) -> str:
        """Gera memória ativa"""
        project = args.get("project")
        if not project:
            return "Erro: project é obrigatório"

        return self.memory_view.generate(project)

    def _search(self, args: Dict[str, Any]) -> str:
        """Busca memórias"""
        query = args.get("query", "")
        project = args.get("project")
        mem_type = args.get("type")
        limit = args.get("limit", 10)

        results = self.query_engine.search(
            query=query,
            project=project,
            mem_type=mem_type,
            limit=limit
        )

        if not results:
            return "Nenhum resultado encontrado."

        lines = [f"Resultados para '{query}':\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. [{r.type}] {r.title}")
            lines.append(f"   Projeto: {r.project} | Score: {r.score:.3f} | Fonte: {r.source}")

        return "\n".join(lines)

    def _checkpoint(self, args: Dict[str, Any]) -> str:
        """Cria checkpoint"""
        project = args.get("project")
        if not project:
            return "Erro: project é obrigatório"

        session_id = args.get("session_id") or self.session_manager.get_session_id()
        reason = args.get("reason", "manual")

        try:
            result = self.extractor.extract_session(project, session_id)
        except Exception as e:
            return f"Erro ao extrair sessão: {e}"

        if not result.events:
            return f"Nenhum evento encontrado para sessão {session_id}"

        draft = self.extractor.create_draft(result, "session")
        draft["checkpoint_reason"] = reason
        draft_name = self.extractor.write_draft(project, draft, "session")

        # Registra evento
        from src.core.event_schema import Event, EventType, EventOrigin
        checkpoint_event = Event(
            project=project,
            origin=EventOrigin.USER,
            event_type=EventType.CHECKPOINT_CREATED,
            subtype="mcp",
            payload={
                "session_id": session_id,
                "draft_name": draft_name,
                "reason": reason
            }
        )
        self.raw_storage.append(checkpoint_event)

        return f"Checkpoint criado: {draft_name} ({len(result.events)} eventos)"

    def _promote(self, args: Dict[str, Any]) -> str:
        """Promove draft"""
        project = args.get("project")
        draft_id = args.get("draft_id")

        if not project:
            return "Erro: project é obrigatório"
        if not draft_id:
            return "Erro: draft_id é obrigatório"

        draft_type = args.get("draft_type", "session")
        promote_to = args.get("promote_to", "decision")

        if draft_type == "session":
            result = self.promoter.promote_session(project, draft_id, promote_to)
        elif draft_type == "feature":
            result = self.promoter.promote_feature(project, draft_id, promote_to)
        else:
            return f"Erro: Tipo de draft desconhecido: {draft_type}"

        if result is None:
            return "Draft não encontrado."

        if result.success:
            self.promoter.mark_promoted(project, draft_id, draft_type, result)
            return f"Promovido para: {result.target_path}"
        else:
            return f"Promoção falhou: {result.metadata.get('reason', 'desconhecido')}"

    def _status(self) -> str:
        """Status do sistema"""
        session_id = self.session_manager.get_session_id()

        lines = [
            "Status do Cerebro:",
            f"  Session ID: {session_id}",
            f"  Path: {self.cerebro_path.absolute()}",
            "",
            "Storages:",
            f"  Raw: {self.cerebro_path / 'raw'}",
            f"  Working: {self.cerebro_path / 'working'}",
            f"  Official: {self.cerebro_path / 'official'}",
            "",
            "Índice:",
            f"  Metadata DB: {self.cerebro_path / 'index' / 'metadata.db'}",
            f"  Embeddings DB: {self.cerebro_path / 'index' / 'embeddings.db'}"
        ]

        return "\n".join(lines)


async def main():
    """Entry point do MCP Server"""
    server = Server("cerebro")
    cerebro = CerebroMCP()

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        return cerebro.get_tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        return await cerebro.handle_tool(name, arguments)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

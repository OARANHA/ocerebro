"""MCP Server do Cerebro: Integração com Claude Code"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


def _safe_print_error(msg: str) -> None:
    """Print seguro para stderr com fallback de encoding."""
    try:
        print(msg, file=sys.stderr)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"), file=sys.stderr)

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
from src.hooks.custom_loader import HooksLoader, HookRunner
from src.diff.memory_diff import MemoryDiff
from src.consolidation.dream import run_dream, generate_dream_report
from src.consolidation.remember import run_remember, generate_remember_report
from src.forgetting.gc import GarbageCollector
from src.core.paths import get_auto_mem_path


class CerebroMCP:
    """
    MCP Server para integração do Cerebro com Claude Code.

    Ferramentas disponíveis:
    - cerebro_memory: Visualizar memória ativa
    - cerebro_search: Buscar memórias
    - cerebro_checkpoint: Criar checkpoint manual
    - cerebro_promote: Promover draft para official
    - cerebro_status: Status do sistema
    - cerebro_hooks: Listar e gerenciar hooks customizados
    """

    def __init__(self, cerebro_path: Optional[Path] = None):
        """
        Inicializa o MCP Server.

        Args:
            cerebro_path: Diretório base do OCerebro (default: .ocerebro)
        """
        self.cerebro_path = cerebro_path or Path(".ocerebro")
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

        # Inicializa memory diff
        self.memory_diff = MemoryDiff(
            self.official_storage,
            self.working_storage,
            self.raw_storage
        )

        # Inicializa hooks com tratamento de erro
        # WARN-04 FIX: hooks.yaml com erro não derruba o servidor
        hooks_config = self.cerebro_path.parent / "hooks.yaml"
        try:
            self.hooks_loader = HooksLoader(hooks_config) if hooks_config.exists() else None
            self.hooks_runner = HookRunner(self.hooks_loader) if self.hooks_loader else None
        except Exception as e:
            # WINDOWS FIX: Usa _safe_print_error para evitar UnicodeEncodeError
            _safe_print_error(f"[CEREBRO] Aviso: hooks.yaml com erro ({e}). Hooks desativados.")
            self.hooks_loader = None
            self.hooks_runner = None

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
            ),
            Tool(
                name="cerebro_hooks",
                description="Listar e gerenciar hooks customizados",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "Ação: list, test, info",
                            "enum": ["list", "test", "info"],
                            "default": "list"
                        },
                        "event_type": {
                            "type": "string",
                            "description": "Filtrar por tipo de evento"
                        },
                        "hook_name": {
                            "type": "string",
                            "description": "Nome do hook (para ação 'info')"
                        }
                    }
                }
            ),
            Tool(
                name="cerebro_diff",
                description="Análise diferencial de memória entre dois pontos no tempo - mostra decisões adicionadas, erros documentados, drafts pendentes e memórias em risco de GC",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome do projeto"
                        },
                        "period_days": {
                            "type": "integer",
                            "description": "Dias do período (padrão: 7)",
                            "default": 7
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Data de início (ISO format, ex: 2026-03-01)"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Data de fim (ISO format, ex: 2026-03-31)"
                        },
                        "gc_threshold": {
                            "type": "number",
                            "description": "Threshold para GC risk (padrão: 0.3)",
                            "default": 0.3
                        },
                        "format": {
                            "type": "string",
                            "description": "Formato de saída",
                            "enum": ["markdown", "json"],
                            "default": "markdown"
                        }
                    },
                    "required": ["project"]
                }
            ),
            Tool(
                name="cerebro_dream",
                description="Extração automática de memórias (replica extractMemories do Claude Code) - analisa transcript e extrai memórias para user/feedback/project/reference",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "since_days": {
                            "type": "integer",
                            "description": "Dias para analisar (padrão: 7)",
                            "default": 7
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "Se True, apenas simula (padrão: True)",
                            "default": True
                        }
                    }
                }
            ),
            Tool(
                name="cerebro_remember",
                description="Revisão e promoção de memórias (replica /remember do Claude Code) - classifica memórias por tipo e detecta duplicatas/conflitos entre camadas",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "dry_run": {
                            "type": "boolean",
                            "description": "Se True, apenas gera relatório (padrão: True)",
                            "default": True
                        }
                    }
                }
            ),
            Tool(
                name="cerebro_gc",
                description="Garbage collection de memórias - lista memórias stale por mtime e remove candidatas (nunca remove user/feedback)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "threshold_days": {
                            "type": "integer",
                            "description": "Dias para considerar memória stale (padrão: 7)",
                            "default": 7
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "Se True, apenas lista candidatas (padrão: True)",
                            "default": True
                        }
                    }
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
            elif name == "cerebro_hooks":
                result = self._hooks(arguments)
            elif name == "cerebro_diff":
                result = self._diff(arguments)
            elif name == "cerebro_dream":
                result = self._dream(arguments)
            elif name == "cerebro_remember":
                result = self._remember(arguments)
            elif name == "cerebro_gc":
                result = self._gc(arguments)
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

    def _hooks(self, args: Dict[str, Any]) -> str:
        """Lista e gerencia hooks customizados"""
        action = args.get("action", "list")
        event_type = args.get("event_type")
        hook_name = args.get("hook_name")

        if self.hooks_loader is None:
            return "Hooks não configurados. Crie um arquivo hooks.yaml na raiz do projeto."

        if action == "list":
            hooks = self.hooks_loader.hooks

            if event_type:
                hooks = [h for h in hooks if h.event_type == event_type or h.event_type == "*"]

            if not hooks:
                return "Nenhum hook configurado."

            lines = ["Hooks customizados configurados:\n"]
            for i, hook in enumerate(hooks, 1):
                lines.append(f"{i}. **{hook.name}**")
                lines.append(f"   - Evento: {hook.event_type}:{hook.event_subtype or '*'}")
                lines.append(f"   - Módulo: {hook.module_path}")
                lines.append(f"   - Função: {hook.function}")
                if hook.config:
                    lines.append(f"   - Config: {hook.config}")
                lines.append("")

            return "\n".join(lines)

        elif action == "info":
            if not hook_name:
                return "Erro: hook_name é obrigatório para ação 'info'"

            hook = next((h for h in self.hooks_loader.hooks if h.name == hook_name), None)
            if not hook:
                return f"Hook '{hook_name}' não encontrado."

            lines = [
                f"## Hook: {hook.name}",
                "",
                f"- **Evento:** {hook.event_type}:{hook.event_subtype or '*'}",
                f"- **Módulo:** {hook.module_path}",
                f"- **Função:** {hook.function}",
                f"- **Config:** {hook.config or {}}",
                "",
                "### Assinatura da função",
                "",
                "```python",
                f"def {hook.function}(event: Event, context: dict, config: dict) -> dict:",
                "    # Seu código aqui",
                "```"
            ]

            return "\n".join(lines)

        elif action == "test":
            # Simula execução de hook de teste
            from src.core.event_schema import Event, EventType, EventOrigin

            test_event = Event(
                project="test",
                origin=EventOrigin.CLAUDE_CODE,
                event_type=EventType.TOOL_CALL,
                subtype="bash",
                payload={"command": "echo test", "duration": 0.1}
            )

            if self.hooks_runner is None:
                return "Hooks runner não inicializado."

            results = self.hooks_runner.execute(test_event)

            lines = ["Resultado do teste de hooks:\n"]
            for name, result in results.items():
                status = "✅" if result["success"] else "❌"
                lines.append(f"{status} {name}: {result.get('result', result.get('error', 'N/A'))}")

            return "\n".join(lines)

        return f"Ação desconhecida: {action}"

    def _diff(self, args: Dict[str, Any]) -> str:
        """Análise diferencial de memória"""
        project = args.get("project")
        if not project:
            return "Erro: project é obrigatório"

        period_days = args.get("period_days", 7)
        start_date = args.get("start_date")
        end_date = args.get("end_date")
        gc_threshold = args.get("gc_threshold", 0.3)
        format = args.get("format", "markdown")

        result = self.memory_diff.analyze(
            project=project,
            period_days=period_days if not start_date else None,
            start_date=start_date,
            end_date=end_date,
            gc_threshold=gc_threshold
        )

        return self.memory_diff.generate_report(result, format=format)

    def _dream(self, args: Dict[str, Any]) -> str:
        """Extração automática de memórias"""
        since_days = args.get("since_days", 7)
        dry_run = args.get("dry_run", True)

        memory_dir = get_auto_mem_path()
        result = run_dream(memory_dir=memory_dir, since_days=since_days, dry_run=dry_run)
        return generate_dream_report(result)

    def _remember(self, args: Dict[str, Any]) -> str:
        """Revisão e promoção de memórias"""
        dry_run = args.get("dry_run", True)

        report = run_remember(dry_run=dry_run)
        return generate_remember_report(report)

    def _gc(self, args: Dict[str, Any]) -> str:
        """Garbage collection de memórias"""
        threshold_days = args.get("threshold_days", 7)
        dry_run = args.get("dry_run", True)

        memory_dir = get_auto_mem_path()
        gc = GarbageCollector(memory_dir)
        results = gc.run_gc(
            memory_dir=memory_dir,
            archive_threshold_days=threshold_days,
            deletion_threshold_days=threshold_days * 4,
            dry_run=dry_run
        )
        return gc.generate_gc_report(results)


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

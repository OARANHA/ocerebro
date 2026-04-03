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
from src.index.entities_db import EntitiesDB
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

    @staticmethod
    def _get_configured_path() -> Path:
        """Lê o caminho configurado em ~/.ocerebro_config ou usa default."""
        config_file = Path.home() / ".ocerebro_config"
        if config_file.exists():
            try:
                content = config_file.read_text(encoding="utf-8")
                for line in content.strip().splitlines():
                    if line.startswith("base_path="):
                        return Path(line.split("=", 1)[1].strip())
            except Exception:
                pass
        # Fallback: .ocerebro no diretório atual
        return Path(".ocerebro")

    def __init__(self, cerebro_path: Optional[Path] = None):
        """
        Inicializa o MCP Server.

        Args:
            cerebro_path: Diretório base do OCerebro (default: lê de ~/.ocerebro_config)
        """
        self.cerebro_path = cerebro_path or self._get_configured_path()
        self.cerebro_path.mkdir(parents=True, exist_ok=True)

        # Inicializa componentes
        self.raw_storage = JSONLStorage(self.cerebro_path / "raw")
        self.working_storage = YAMLStorage(self.cerebro_path / "working")
        self.official_storage = MarkdownStorage(self.cerebro_path / "official")
        self.session_manager = SessionManager(self.cerebro_path)

        self.metadata_db = MetadataDB(self.cerebro_path / "index" / "metadata.db")
        self.embeddings_db = EmbeddingsDB(self.cerebro_path / "index" / "embeddings.db")
        self.entities_db = EntitiesDB(self.cerebro_path / "index" / "entities.db")
        self.query_engine = QueryEngine(self.metadata_db, self.embeddings_db, self.entities_db)

        self.extractor = Extractor(self.raw_storage, self.working_storage)
        self.promoter = Promoter(
            self.working_storage,
            self.official_storage,
            self.cerebro_path / "index" / "entities.db"
        )

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

        # Inicializa hooks APENAS se .ocerebro existir e hooks.yaml estiver presente
        # FIX: Não carrega hooks em projetos sem .ocerebro
        hooks_config = self.cerebro_path.parent / "hooks.yaml"
        try:
            # Verifica se hooks.yaml existe antes de carregar
            if hooks_config.exists():
                self.hooks_loader = HooksLoader(hooks_config)
                self.hooks_runner = HookRunner(self.hooks_loader)
            else:
                self.hooks_loader = None
                self.hooks_runner = None
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
                description="Prepara prompt para extração de memórias - use cerebro_capture_memory após receber o prompt",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "since_days": {
                            "type": "integer",
                            "description": "Dias para analisar (padrão: 7)",
                            "default": 7
                        }
                    }
                }
            ),
            Tool(
                name="cerebro_capture_memory",
                description="Salva uma memória diretamente em ~/.claude/memory/ (formato nativo Claude Code). Chame uma vez por memória com o conteúdo Markdown completo.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "memory_content": {
                            "type": "string",
                            "description": "Conteúdo Markdown completo com frontmatter obrigatório: name, description, type (user|feedback|project|reference)"
                        }
                    },
                    "required": ["memory_content"]
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
            ),
            Tool(
                name="cerebro_graph",
                description="Explora grafo de entidades - mostra conexões entre projetos, tecnologias, pessoas e decisões",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity": {
                            "type": "string",
                            "description": "Nome da entidade para iniciar traversal (ex: 'MedicsPro', 'JWT', 'autenticação')"
                        },
                        "depth": {
                            "type": "integer",
                            "description": "Profundidade máxima do traversal (1-3, padrão: 2)",
                            "default": 2
                        },
                        "types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filtrar por tipos de entidade (ex: ['ORG', 'TECH'])",
                            "default": ["ORG", "TECH", "PERSON", "PROJECT"]
                        }
                    },
                    "required": ["entity"]
                }
            ),
            Tool(
                name="cerebro_dashboard",
                description="Abre o dashboard visual do OCerebro no browser (localhost:7999) - interface gráfica para explorar memórias, grafo de entidades e timeline",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "port": {
                            "type": "integer",
                            "description": "Porta do servidor (padrão: 7999)",
                            "default": 7999
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
            elif name == "cerebro_capture_memory":
                result = self._capture_memory(arguments)
            elif name == "cerebro_graph":
                result = self._cerebro_graph(arguments)
            elif name == "cerebro_dashboard":
                result = self._cerebro_dashboard(arguments)
            else:
                return [TextContent(type="text", text=f"Ferramenta desconhecida: {name}")]

            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Erro: {str(e)}")]

    def _memory(self, args: Dict[str, Any]) -> str:
        """Gera memória ativa e escreve no diretório nativo do Claude Code para auto-load."""
        project = args.get("project")
        if not project:
            return "Erro: project é obrigatório"

        content = self.memory_view.generate(project)

        # FIX 4: Escreve MEMORY.md no diretório nativo do Claude Code
        # Assim o Claude Code carrega automaticamente na próxima sessão
        try:
            from src.core.paths import get_auto_mem_path, get_memory_index
            auto_mem_dir = get_auto_mem_path()
            auto_mem_dir.mkdir(parents=True, exist_ok=True)
            index_path = get_memory_index(auto_mem_dir)

            # Gera conteúdo compatível com o formato que Claude Code espera
            # Formato: # <title>\n\n- [type] filename (date): description
            claude_format_lines = ["# OCerebro - Memória Ativa", ""]
            claude_format_lines.append(f"## {project}")
            claude_format_lines.append("")

            # Parse do conteúdo gerado para extrair itens
            for line in content.splitlines():
                if line.startswith("- ["):
                    claude_format_lines.append(line)

            claude_content = "\n".join(claude_format_lines)
            index_path.write_text(claude_content, encoding="utf-8")
        except Exception:
            pass  # Falha silenciosa - não bloqueia o retorno

        return content

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
        """Status do sistema com contagem de memórias por tipo"""
        session_id = self.session_manager.get_session_id()

        lines = [
            "╔══════════════════════════════════════════════════════════════╗",
            "║                    🧠 OCEREBRO STATUS                        ║",
            "╚══════════════════════════════════════════════════════════════╝",
            "",
            f"Session ID: {session_id}",
            f"Path: {self.cerebro_path.absolute()}",
            "",
        ]

        # Contagem de memórias por tipo (entities DB)
        try:
            import sqlite3
            conn = sqlite3.connect(str(self.cerebro_path / "index" / "entities.db"))
            cursor = conn.cursor()
            cursor.execute("SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type ORDER BY COUNT(*) DESC")
            type_counts = cursor.fetchall()
            conn.close()

            if type_counts:
                total = sum(c for _, c in type_counts)
                lines.append(f"📊 Memórias: {total} total")
                lines.append("")
                lines.append("Por tipo:")
                for entity_type, count in type_counts:
                    icon = self._get_type_icon(entity_type)
                    lines.append(f"  {icon} {entity_type}: {count}")
            else:
                lines.append("📊 Memórias: 0")
        except Exception:
            lines.append("📊 Memórias: (banco não acessível)")

        lines.append("")
        lines.append("Storages:")
        lines.append(f"  📁 Raw: {self.cerebro_path / 'raw'}")
        lines.append(f"  📝 Working: {self.cerebro_path / 'working'}")
        lines.append(f"  📋 Official: {self.cerebro_path / 'official'}")

        return "\n".join(lines)

    def _get_type_icon(self, entity_type: str) -> str:
        """Retorna ícone para tipo de memória"""
        icons = {
            "USER": "👤",
            "FEEDBACK": "💬",
            "PROJECT": "📂",
            "REFERENCE": "🔗",
            "TAG": "🏷️",
            "TYPE": "📌",
            "META": "⚙️",
            "DECISION": "✅",
            "ERROR": "❌",
            "DRAFT": "📝",
        }
        return icons.get(entity_type, "📄")

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
        """Prepara prompt para extração de memórias.

        Retorna o prompt de extração + instruções para usar cerebro_capture_memory.
        """
        from src.consolidation.dream import (
            run_dream,
            build_extract_dream_prompt,
            scan_memory_files,
            format_memory_manifest,
            count_transcript_messages
        )

        since_days = args.get("since_days", 7)
        memory_dir = get_auto_mem_path()

        # Scan de memórias existentes
        existing = scan_memory_files(memory_dir)
        existing_manifest = format_memory_manifest(existing)

        # Contagem de mensagens novas
        message_count = count_transcript_messages(since_days)

        if message_count == 0:
            return "Nenhuma mensagem nova nos últimos {} dias. O prompt de extração não será gerado.".format(since_days)

        # Build do prompt
        prompt_sections = build_extract_dream_prompt(
            new_message_count=message_count,
            existing_memories=existing_manifest,
            memory_dir=memory_dir,
        )
        full_prompt = "\n".join(prompt_sections)

        return f"""=== PROMPT DE EXTRAÇÃO ({message_count} mensagens, {since_days} dias) ===

{full_prompt}

---
INSTRUÇÃO CRÍTICA: Analise esta conversa usando o prompt acima.
Para CADA memória identificada, chame cerebro_capture_memory UMA vez:

    cerebro_capture_memory(memory_content="---\\nname: <nome>\\ndescription: <descrição>\\ntype: <user|feedback|project|reference>\\n---\\n\\n<conteúdo>")

NÃO use FileWrite. NÃO use FileEdit. APENAS cerebro_capture_memory.
Uma chamada por memória. O sistema salva e indexa automaticamente.
"""

    def _capture_memory(self, args: Dict[str, Any]) -> str:
        """Salva uma memória no diretório nativo do Claude Code e no OCerebro (dual-write)."""
        import re
        import yaml
        from datetime import datetime
        from src.core.paths import get_memory_index, get_auto_mem_path

        content = args.get("memory_content", "")
        if not content:
            return "Erro: 'memory_content' é obrigatório"

        name_match = re.search(r'name:\s*(.*)', content)
        if not name_match:
            return "Erro: frontmatter 'name' é obrigatório no memory_content"

        mem_name = name_match.group(1).strip().lower().replace(' ', '-')

        # Parse frontmatter uma única vez com yaml.safe_load
        frontmatter_match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
        frontmatter = {}
        body_content = ""
        if frontmatter_match:
            try:
                frontmatter = yaml.safe_load(frontmatter_match.group(1)) or {}
                body_content = frontmatter_match.group(2)
            except Exception:
                pass  # Fallback para regex se yaml falhar

        # Extrai variáveis do frontmatter parseado (fallback para regex se necessário)
        m_type = frontmatter.get('type', '')
        project = frontmatter.get('project', '')
        tags = frontmatter.get('tags', '')
        desc = frontmatter.get('description', '')

        # Fallback via regex se frontmatter parsing falhou
        if not m_type:
            type_match = re.search(r'type:\s*(.*)', content)
            m_type = type_match.group(1).strip() if type_match else "project"
        if not project:
            project_match = re.search(r'project:\s*(.*)', content)
            project = project_match.group(1).strip() if project_match else "unknown"
        if not tags:
            tags_match = re.search(r'tags:\s*(.*)', content)
            tags = tags_match.group(1).strip() if tags_match else ""
        if not desc:
            desc_match = re.search(r'description:\s*(.*)', content)
            desc = desc_match.group(1).strip() if desc_match else "sem descrição"

        ts = datetime.now().strftime("%Y-%m-%d")
        entry = f"- [{m_type}] {mem_name}.md ({ts}): {desc}\n"

        # =========================================================================
        # DUAL-WRITE: Salva em ambos os diretórios
        # =========================================================================

        # 1. Diretório nativo do Claude Code (~/.claude/projects/<slug>/memory/)
        #    → Claude Code carrega automaticamente na próxima sessão
        claude_mem_dir = get_auto_mem_path()
        claude_mem_dir.mkdir(parents=True, exist_ok=True)
        claude_file_path = claude_mem_dir / f"{mem_name}.md"
        claude_file_path.write_text(content, encoding="utf-8")

        # Atualiza MEMORY.md nativo
        claude_index_path = get_memory_index(claude_mem_dir)
        if claude_index_path.exists():
            existing = claude_index_path.read_text(encoding="utf-8")
            if mem_name not in existing:
                with open(claude_index_path, "a", encoding="utf-8") as f:
                    f.write(entry)
        else:
            claude_index_path.write_text(f"# Memórias do Projeto\n\n{entry}", encoding="utf-8")

        # 2. Diretório OCerebro (.ocerebro/official/<subdir>/)
        #    → OCerebro indexa e busca via cerebro_memory/cerebro_search
        # Mapeamento: Claude Code type → OCerebro subdir
        type_to_subdir = {
            "user": "decisions",      # user → decisions (global)
            "feedback": "preferences", # feedback → preferences
            "project": "decisions",    # project → decisions
            "reference": "state",      # reference → state
        }
        subdir = type_to_subdir.get(m_type, "decisions")  # default: decisions

        # Para tipo "user", salva em global/; para outros, usa project do frontmatter
        if m_type == "user":
            cerebro_project = "global"
        else:
            cerebro_project = project if project != "unknown" else "default"

        cerebro_dir = self.cerebro_path / "official" / cerebro_project / subdir
        cerebro_dir.mkdir(parents=True, exist_ok=True)
        cerebro_file_path = cerebro_dir / f"{mem_name}.md"
        cerebro_file_path.write_text(content, encoding="utf-8")

        # =========================================================================
        # Registrar entidades no grafo (frontmatter + conteúdo)
        # =========================================================================
        if self.entities_db and frontmatter_match:
            try:
                # 1. Extrai entidades do conteúdo (spaCy NER)
                self.entities_db.extract_from_content(
                    memory_id=mem_name,
                    content=body_content,
                    use_spacy=True
                )
                # 2. Extrai entidades do frontmatter - preservadas
                self.entities_db.extract_from_frontmatter(
                    memory_id=mem_name,
                    frontmatter=frontmatter,
                    project=cerebro_project
                )
            except Exception:
                pass  # Falha silenciosa se frontmatter inválido

        # Indexar no metadata_db para aparecer no dashboard
        if self.metadata_db:
            tags_str = tags if isinstance(tags, str) else ",".join(tags) if isinstance(tags, list) else ""
            self.metadata_db.insert({
                "id": mem_name,
                "type": m_type,
                "project": cerebro_project,
                "title": frontmatter.get("title", mem_name) if frontmatter else mem_name,
                "content": body_content,
                "tags": tags_str,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "layer": "auto",
                "path": str(cerebro_file_path),
            })

        return f"✅ Memória '{mem_name}' salva (dual-write: Claude + OCerebro)"

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
        report = gc.generate_gc_report(results)

        # Adiciona aviso de arquivamento se houver memórias arquivadas
        if results.get("archived"):
            report += "\n\n---\n"
            report += "⚠️ Memórias arquivadas não são deletadas — acesse em .ocerebro/arquivo/\n"
            report += "Para restaurar: mova o arquivo de volta para ~/.claude/memory/\n"

        return report

    def _cerebro_graph(self, args: Dict[str, Any]) -> str:
        """Explora grafo de entidades"""
        entity = args.get("entity")
        if not entity:
            return "Erro: 'entity' é obrigatório para cerebro_graph"

        depth = args.get("depth", 2)
        entity_types = args.get("types", ["ORG", "TECH", "PERSON", "PROJECT"])

        # Limita profundidade máxima para evitar traversal muito grande
        depth = min(depth, 3)

        nodes, edges = self.entities_db.traverse(
            start_entity=entity,
            depth=depth,
            entity_types=entity_types,
            max_nodes=50
        )

        if not nodes:
            return f"Nenhuma entidade encontrada para '{entity}'"

        # Formata grafo como árvore
        return self._format_graph(nodes, edges, entity)

    def _format_graph(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        root_entity: str
    ) -> str:
        """Formata grafo como árvore visual"""
        lines = [f"## Grafo de '{root_entity}'\n"]
        lines.append(f"**{len(nodes)}** entidades encontradas, **{len(edges)}** conexões\n")

        # Constroi adjacency list
        adj: Dict[str, List[Dict[str, Any]]] = {}
        for edge in edges:
            source = edge["source"].lower()
            if source not in adj:
                adj[source] = []
            adj[source].append(edge)

        # BFS para imprimir árvore
        visited = set()
        queue = [(root_entity.lower(), 0)]

        while queue:
            entity_name, depth = queue.pop(0)

            if entity_name in visited:
                continue
            visited.add(entity_name)

            # Encontra nó correspondente
            node = next((n for n in nodes if n["name"].lower() == entity_name), None)
            if not node:
                continue

            # Imprime nó
            prefix = "  " * depth
            connector = "├─ " if depth > 0 else ""
            lines.append(f"{prefix}{connector}{node['name']} ({node['type']})")

            # Adiciona filhos na fila
            if depth < 3:
                children = adj.get(entity_name, [])
                for child in children:
                    child_name = child["target"].lower()
                    if child_name not in visited:
                        queue.append((child_name, depth + 1))

        # Lista todas as arestas
        if edges:
            lines.append("\n## Conexões")
            for edge in edges:
                lines.append(f"- {edge['source']} → {edge['target']} ({edge['type']})")

        return "\n".join(lines)

    def _cerebro_dashboard(self, args: Dict[str, Any]) -> str:
        """Abre o dashboard visual do OCerebro no browser"""
        try:
            import subprocess
            import sys

            port = args.get("port", 7999)

            # SEMPRE mata o processo antigo e reinicia - garante cerebro_path correto
            pid_file = Path.home() / ".ocerebro_dashboard.pid"
            if pid_file.exists():
                try:
                    old_pid = int(pid_file.read_text(encoding="utf-8").strip())
                    import os
                    # WINDOWS FIX: usa taskkill no Windows
                    if sys.platform == "win32":
                        subprocess.call(["taskkill", "/F", "/PID", str(old_pid)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        os.kill(old_pid, 9)  # SIGKILL
                    pid_file.unlink()  # Remove o arquivo PID
                except Exception:
                    pass  # Processo já morreu ou erro ao matar

            # Aguarda porta liberar (até 2s)
            import time
            for _ in range(20):
                time.sleep(0.1)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                if result != 0:
                    break

            # Inicia como processo separado (persiste após o MCP terminar)
            server_script = Path(__file__).parent.parent / "dashboard" / "standalone_server.py"
            if not server_script.exists():
                return "⚠️ Erro: standalone_server.py não encontrado."

            # Inicia processo em background
            subprocess.Popen(
                [sys.executable, str(server_script), str(port), str(self.cerebro_path.absolute())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # Desacoplado do processo pai
            )

            # Aguarda servidor estar pronto (até 5s)
            for _ in range(50):
                time.sleep(0.1)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                if result == 0:
                    break
            else:
                return "⚠️ Servidor não iniciou em 5 segundos."

            # Abre browser
            import webbrowser
            webbrowser.open(f"http://localhost:{port}")

            return f"✅ Dashboard aberto em http://localhost:{port}"
        except ImportError as e:
            return f"Erro: Não foi possível importar o dashboard. Verifique se fastapi e uvicorn estão instalados. ({e})"
        except Exception as e:
            return f"Erro ao abrir dashboard: {e}"


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

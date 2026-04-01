"""CLI do Cerebro: comandos manuais"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.core.jsonl_storage import JSONLStorage
from src.core.session_manager import SessionManager
from src.working.yaml_storage import YAMLStorage
from src.working.memory_view import MemoryView
from src.official.markdown_storage import MarkdownStorage
from src.consolidation.checkpoints import CheckpointManager, CheckpointTrigger
from src.consolidation.extractor import Extractor
from src.consolidation.promoter import Promoter
from src.index.metadata_db import MetadataDB
from src.index.embeddings_db import EmbeddingsDB
from src.index.queries import QueryEngine


class CerebroCLI:
    """
    Interface de linha de comando do Cerebro.

    Comandos disponíveis:
    - checkpoint: Trigger manual de checkpoint
    - memory: Visualizar memória ativa
    - search: Buscar memórias
    - promote: Promover draft para official
    - gc: Garbage collection manual
    - status: Status do sistema
    """

    def __init__(self, cerebro_path: Path):
        """
        Inicializa a CLI.

        Args:
            cerebro_path: Diretório base do Cerebro
        """
        self.cerebro_path = cerebro_path
        self.cerebro_path.mkdir(parents=True, exist_ok=True)

        # Inicializa storages
        self.raw_storage = JSONLStorage(cerebro_path / "raw")
        self.working_storage = YAMLStorage(cerebro_path / "working")
        self.official_storage = MarkdownStorage(cerebro_path / "official")
        self.session_manager = SessionManager(cerebro_path)

        # Inicializa índice
        self.metadata_db = MetadataDB(cerebro_path / "index" / "metadata.db")
        self.embeddings_db = EmbeddingsDB(cerebro_path / "index" / "embeddings.db")
        self.query_engine = QueryEngine(self.metadata_db, self.embeddings_db)

        # Inicializa consolidação
        self.checkpoint_manager = CheckpointManager(cerebro_path / "config")
        self.extractor = Extractor(self.raw_storage, self.working_storage)
        self.promoter = Promoter(self.working_storage, self.official_storage)

        # Inicializa memory view
        self.memory_view = MemoryView(cerebro_path, self.official_storage, self.working_storage)

    def checkpoint(self, project: str, session_id: Optional[str] = None, reason: str = "manual") -> str:
        """
        Trigger manual de checkpoint.

        Args:
            project: Nome do projeto
            session_id: ID da sessão (usa atual se None)
            reason: Motivo do checkpoint

        Returns:
            Mensagem de resultado
        """
        if session_id is None:
            session_id = self.session_manager.get_session_id()

        # Extrai sessão
        try:
            result = self.extractor.extract_session(project, session_id)
        except Exception as e:
            return f"Erro ao extrair sessão: {e}"

        if not result.events:
            return f"Nenhum evento encontrado para sessão {session_id}"

        # Cria draft
        draft = self.extractor.create_draft(result, "session")
        draft["checkpoint_reason"] = reason

        # Escreve draft
        draft_name = self.extractor.write_draft(project, draft, "session")

        # Registra evento de checkpoint
        from src.core.event_schema import Event, EventType, EventOrigin
        checkpoint_event = Event(
            project=project,
            origin=EventOrigin.USER,
            event_type=EventType.CHECKPOINT_CREATED,
            subtype="manual",
            payload={
                "session_id": session_id,
                "draft_name": draft_name,
                "reason": reason,
                "events_count": len(result.events)
            }
        )
        self.raw_storage.append(checkpoint_event)

        return f"Checkpoint criado: {draft_name} ({len(result.events)} eventos)"

    def memory(self, project: str, output: Optional[Path] = None) -> str:
        """
        Gera visualização da memória ativa.

        Args:
            project: Nome do projeto
            output: Arquivo de saída (opcional)

        Returns:
            Conteúdo do MEMORY.md
        """
        content = self.memory_view.generate(project)

        if output:
            output.write_text(content, encoding="utf-8")
            return f"MEMORY.md gerado em: {output}"

        return content

    def search(
        self,
        query: str,
        project: Optional[str] = None,
        mem_type: Optional[str] = None,
        limit: int = 10,
        use_semantic: bool = True
    ) -> str:
        """
        Busca memórias.

        Args:
            query: Texto de busca
            project: Filtrar por projeto
            mem_type: Filtrar por tipo
            limit: Limite de resultados
            use_semantic: Usar busca semântica

        Returns:
            Resultados formatados
        """
        results = self.query_engine.search(
            query=query,
            project=project,
            mem_type=mem_type,
            limit=limit,
            use_semantic=use_semantic
        )

        if not results:
            return "Nenhum resultado encontrado."

        lines = [f"Resultados para '{query}':\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. [{r.type}] {r.title}")
            lines.append(f"   Projeto: {r.project} | Score: {r.score:.3f} | Fonte: {r.source}")
            if r.metadata:
                if r.metadata.get("tags"):
                    lines.append(f"   Tags: {r.metadata['tags']}")

        return "\n".join(lines)

    def promote(
        self,
        project: str,
        draft_id: str,
        draft_type: str = "session",
        promote_to: str = "decision"
    ) -> str:
        """
        Promove draft para official.

        Args:
            project: Nome do projeto
            draft_id: ID do draft
            draft_type: Tipo do draft
            promote_to: Tipo de promoção

        Returns:
            Mensagem de resultado
        """
        if draft_type == "session":
            result = self.promoter.promote_session(project, draft_id, promote_to)
        elif draft_type == "feature":
            result = self.promoter.promote_feature(project, draft_id, promote_to)
        else:
            return f"Tipo de draft desconhecido: {draft_type}"

        if result is None:
            return "Draft não encontrado ou não pôde ser promovido."

        if result.success:
            # Marca como promovido
            self.promoter.mark_promoted(project, draft_id, draft_type, result)

            # Registra evento
            from src.core.event_schema import Event, EventType, EventOrigin
            promotion_event = Event(
                project=project,
                origin=EventOrigin.USER,
                event_type=EventType.PROMOTION_PERFORMED,
                subtype="manual",
                payload={
                    "draft_id": draft_id,
                    "draft_type": draft_type,
                    "target_type": result.target_type,
                    "target_path": result.target_path
                }
            )
            self.raw_storage.append(promotion_event)

            return f"Promovido para: {result.target_path}"
        else:
            return f"Promoção falhou: {result.metadata.get('reason', 'desconhecido')}"

    def gc(self, project: Optional[str] = None, dry_run: bool = True) -> str:
        """
        Garbage collection manual.

        Args:
            project: Nome do projeto (None para todos)
            dry_run: Apenas simular

        Returns:
            Relatório de GC
        """
        from src.forgetting.guard_rails import GuardRails
        from src.forgetting.gc import GarbageCollector

        guard_rails = GuardRails(self.cerebro_path / "config" / "cerebro.yaml")
        gc = GarbageCollector(self.cerebro_path / "config")

        # Lista memórias do índice
        memories = self.metadata_db.search(project)

        # Encontra candidatos para archive
        archive_candidates = gc.find_candidates_for_archive(
            memories,
            guard_rails.get_archive_threshold("raw")
        )

        # Filtra por guard rails
        delete_candidates = [
            m for m in archive_candidates
            if guard_rails.can_delete(m)
        ]

        lines = ["Relatório de Garbage Collection:\n"]
        lines.append(f"Total de memórias: {len(memories)}")
        lines.append(f"Candidatas para archive: {len(archive_candidates)}")
        lines.append(f"Candidatas para delete: {len(delete_candidates)}")

        if dry_run:
            lines.append("\n[DRY RUN] Nenhuma ação foi tomada.\n")

        if delete_candidates:
            lines.append("\nCandidatas para delete:")
            for m in delete_candidates[:10]:
                lines.append(f"  - [{m['type']}] {m.get('title', m['id'])} (score: {m.get('total_score', 0):.3f})")

        return "\n".join(lines)

    def status(self) -> str:
        """
        Status do sistema.

        Returns:
            Relatório de status
        """
        lines = ["Status do Cerebro:\n"]

        # Session atual
        session_id = self.session_manager.get_session_id()
        lines.append(f"Session ID: {session_id}")

        # Stats do raw
        lines.append(f"\nRaw storage: {self.cerebro_path / 'raw'}")

        # Stats do working
        lines.append(f"Working storage: {self.cerebro_path / 'working'}")

        # Stats do official
        lines.append(f"Official storage: {self.cerebro_path / 'official'}")

        # Stats do índice
        try:
            stats = self.metadata_db.search()
            lines.append(f"\nÍndice: {len(stats)} memórias")
        except Exception:
            lines.append("\nÍndice: não disponível")

        return "\n".join(lines)


def main():
    """Entry point da CLI"""
    parser = argparse.ArgumentParser(
        prog="cerebro",
        description="Cerebro - Sistema de Memória para Agentes de Código"
    )

    parser.add_argument(
        "--cerebro-path",
        type=Path,
        default=Path(".cerebro"),
        help="Diretório base do Cerebro"
    )

    subparsers = parser.add_subparsers(dest="command", help="Comandos")

    # Comando: checkpoint
    checkpoint_parser = subparsers.add_parser("checkpoint", help="Trigger manual de checkpoint")
    checkpoint_parser.add_argument("project", help="Nome do projeto")
    checkpoint_parser.add_argument("--session", help="ID da sessão")
    checkpoint_parser.add_argument("--reason", default="manual", help="Motivo do checkpoint")

    # Comando: memory
    memory_parser = subparsers.add_parser("memory", help="Visualizar memória ativa")
    memory_parser.add_argument("project", help="Nome do projeto")
    memory_parser.add_argument("--output", type=Path, help="Arquivo de saída")

    # Comando: search
    search_parser = subparsers.add_parser("search", help="Buscar memórias")
    search_parser.add_argument("query", help="Texto de busca")
    search_parser.add_argument("--project", help="Filtrar por projeto")
    search_parser.add_argument("--type", dest="mem_type", help="Filtrar por tipo")
    search_parser.add_argument("--limit", type=int, default=10, help="Limite de resultados")
    search_parser.add_argument("--no-semantic", action="store_true", help="Desativar busca semântica")

    # Comando: promote
    promote_parser = subparsers.add_parser("promote", help="Promover draft para official")
    promote_parser.add_argument("project", help="Nome do projeto")
    promote_parser.add_argument("draft_id", help="ID do draft")
    promote_parser.add_argument("--type", default="session", help="Tipo do draft")
    promote_parser.add_argument("--to", dest="promote_to", default="decision", help="Tipo de promoção")

    # Comando: gc
    gc_parser = subparsers.add_parser("gc", help="Garbage collection")
    gc_parser.add_argument("--project", help="Nome do projeto")
    gc_parser.add_argument("--dry-run", action="store_true", default=True, help="Apenas simular")
    gc_parser.add_argument("--apply", action="store_false", dest="dry_run", help="Aplicar GC")

    # Comando: setup
    setup_parser = subparsers.add_parser("setup", help="Configurar MCP Server e projeto automaticamente")
    setup_parser.add_argument("subcommand", nargs="?", choices=["claude", "hooks", "init"], default="all",
                              help="O que configurar: claude (MCP), hooks (hooks.yaml), init (tudo)")
    setup_parser.add_argument("--project", type=Path, help="Diretório do projeto (padrão: atual)")

    # Comando: status
    subparsers.add_parser("status", help="Status do sistema")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Comando setup nao precisa de CLI
    if args.command == "setup":
        from cerebro.cerebro_setup import setup_claude_desktop, setup_hooks, setup_cerebro_dir

        if args.subcommand == "claude":
            success = setup_claude_desktop()
            sys.exit(0 if success else 1)
        elif args.subcommand == "hooks":
            success = setup_hooks(args.project)
            sys.exit(0 if success else 1)
        elif args.subcommand == "init":
            setup_cerebro_dir(args.project)
            setup_hooks(args.project)
            print("\nSetup completo! Agora execute:")
            print("  cerebro setup claude")
            sys.exit(0)
        else:
            # Setup completo
            setup_cerebro_dir(args.project)
            setup_hooks(args.project)
            setup_claude_desktop()
            sys.exit(0)

    # Inicializa CLI
    cli = CerebroCLI(args.cerebro_path)

    # Executa comando
    if args.command == "checkpoint":
        result = cli.checkpoint(args.project, args.session, args.reason)
    elif args.command == "memory":
        result = cli.memory(args.project, args.output)
    elif args.command == "search":
        result = cli.search(
            args.query,
            args.project,
            args.mem_type,
            args.limit,
            not args.no_semantic
        )
    elif args.command == "promote":
        result = cli.promote(args.project, args.draft_id, args.type, args.promote_to)
    elif args.command == "gc":
        result = cli.gc(args.project, args.dry_run)
    elif args.command == "status":
        result = cli.status()
    else:
        parser.print_help()
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()

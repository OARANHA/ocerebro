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
from src.diff.memory_diff import MemoryDiff, MemoryDiffResult
from src.consolidation.dream import run_dream, generate_dream_report
from src.consolidation.remember import run_remember, generate_remember_report
from src.forgetting.gc import GarbageCollector


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
        self.cerebro_path = cerebro_path
        self.cerebro_path.mkdir(parents=True, exist_ok=True)

        self.raw_storage = JSONLStorage(cerebro_path / "raw")
        self.working_storage = YAMLStorage(cerebro_path / "working")
        self.official_storage = MarkdownStorage(cerebro_path / "official")
        self.session_manager = SessionManager(cerebro_path)

        self.metadata_db = MetadataDB(cerebro_path / "index" / "metadata.db")
        self.embeddings_db = EmbeddingsDB(cerebro_path / "index" / "embeddings.db")
        self.query_engine = QueryEngine(self.metadata_db, self.embeddings_db)

        self.checkpoint_manager = CheckpointManager(cerebro_path / "config")
        self.extractor = Extractor(self.raw_storage, self.working_storage)
        self.promoter = Promoter(self.working_storage, self.official_storage)

        self.memory_view = MemoryView(cerebro_path, self.official_storage, self.working_storage)

        self.memory_diff = MemoryDiff(
            self.official_storage,
            self.working_storage,
            self.raw_storage
        )

    def checkpoint(self, project: str, session_id: Optional[str] = None, reason: str = "manual") -> str:
        if session_id is None:
            session_id = self.session_manager.get_session_id()

        try:
            result = self.extractor.extract_session(project, session_id)
        except Exception as e:
            return f"Erro ao extrair sessão: {e}"

        if not result.events:
            return f"Nenhum evento encontrado para sessão {session_id}"

        draft = self.extractor.create_draft(result, "session")
        draft["checkpoint_reason"] = reason
        draft_name = self.extractor.write_draft(project, draft, "session")

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
        if draft_type == "session":
            result = self.promoter.promote_session(project, draft_id, promote_to)
        elif draft_type == "feature":
            result = self.promoter.promote_feature(project, draft_id, promote_to)
        else:
            return f"Tipo de draft desconhecido: {draft_type}"

        if result is None:
            return "Draft não encontrado ou não pôde ser promovido."

        if result.success:
            self.promoter.mark_promoted(project, draft_id, draft_type, result)

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
        from src.forgetting.guard_rails import GuardRails
        from src.forgetting.gc import GarbageCollector

        guard_rails = GuardRails(self.cerebro_path / "config" / "cerebro.yaml")
        gc = GarbageCollector(self.cerebro_path / "config")
        memories = self.metadata_db.search(project)
        archive_candidates = gc.find_candidates_for_archive(
            memories,
            guard_rails.get_archive_threshold("raw")
        )
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
        lines = ["Status do Cerebro:\n"]
        session_id = self.session_manager.get_session_id()
        lines.append(f"Session ID: {session_id}")
        lines.append(f"\nRaw storage: {self.cerebro_path / 'raw'}")
        lines.append(f"Working storage: {self.cerebro_path / 'working'}")
        lines.append(f"Official storage: {self.cerebro_path / 'official'}")
        try:
            stats = self.metadata_db.search()
            lines.append(f"\nÍndice: {len(stats)} memórias")
        except Exception:
            lines.append("\nÍndice: não disponível")
        return "\n".join(lines)

    def diff(
        self,
        project: str,
        period_days: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        gc_threshold: float = 0.3,
        output: Optional[Path] = None,
        format: str = "markdown"
    ) -> str:
        result = self.memory_diff.analyze(
            project=project,
            period_days=period_days,
            start_date=start_date,
            end_date=end_date,
            gc_threshold=gc_threshold
        )
        report = self.memory_diff.generate_report(result, format=format)
        if output:
            output.write_text(report, encoding="utf-8")
            return f"Memory Diff report gerado em: {output}"
        return report

    def dream(self, since_days: int = 7, dry_run: bool = True) -> str:
        from src.core.paths import get_auto_mem_path
        from src.consolidation.dream import run_dream, generate_dream_report

        memory_dir = get_auto_mem_path()
        result = run_dream(memory_dir=memory_dir, since_days=since_days, dry_run=dry_run)
        return generate_dream_report(result)

    def remember(self, dry_run: bool = True) -> str:
        from src.consolidation.remember import run_remember, generate_remember_report

        report = run_remember(dry_run=dry_run)
        return generate_remember_report(report)

    def gc_cmd(self, threshold_days: int = 7, dry_run: bool = True) -> str:
        from src.core.paths import get_auto_mem_path
        from src.forgetting.gc import GarbageCollector

        memory_dir = get_auto_mem_path()
        gc = GarbageCollector(memory_dir)
        results = gc.run_gc(
            memory_dir=memory_dir,
            archive_threshold_days=threshold_days,
            deletion_threshold_days=threshold_days * 4,
            dry_run=dry_run
        )
        return gc.generate_gc_report(results)


def _run_init(project_path: Optional[Path] = None):
    """Lógica de init compartilhada entre 'init' e 'setup init'"""
    from cerebro.cerebro_setup import setup_ocerebro_dir, setup_hooks

    print("Como quer usar o OCerebro?")
    print("  1. Neste projeto (cria .ocerebro/ aqui)")
    print("  2. Global (usa ~/.ocerebro/ para todos os projetos)")
    choice = input("\nEscolha [1/2] (padrão: 1): ").strip() or "1"

    if choice == "2":
        base_path = Path.home() / ".ocerebro"
        print(f"\n✓ Modo global: {base_path}")
    else:
        base_path = (project_path or Path.cwd()) / ".ocerebro"
        print(f"\n✓ Modo projeto: {base_path}")

    config_file = Path.home() / ".ocerebro_config"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(f"base_path={base_path}\n", encoding="utf-8")
    print(f"✓ Configuração salva em {config_file}")

    setup_ocerebro_dir(base_path)
    setup_hooks(base_path)
    print("\nSetup completo! Agora execute:")
    print("  ocerebro setup claude")


def main():
    """Entry point da CLI"""
    parser = argparse.ArgumentParser(
        prog="ocerebro",
        description="OCerebro - Sistema de Memoria para Agentes (Claude Code/MCP)"
    )

    parser.add_argument(
        "--cerebro-path",
        type=Path,
        default=Path(".ocerebro"),
        help="Diretório base do OCerebro"
    )

    subparsers = parser.add_subparsers(dest="command", help="Comandos")

    # Comando: init (alias direto para setup init)
    init_parser = subparsers.add_parser("init", help="Inicializar OCerebro no projeto atual")
    init_parser.add_argument("--project", type=Path, help="Diretório do projeto (padrão: atual)")

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

    # Comando: setup
    setup_parser = subparsers.add_parser("setup", help="Configurar MCP Server e projeto automaticamente")
    setup_parser.add_argument("subcommand", nargs="?", choices=["claude", "hooks", "init"], default="all",
                              help="O que configurar: claude (MCP), hooks (hooks.yaml), init (tudo)")
    setup_parser.add_argument("--project", type=Path, help="Diretório do projeto (padrão: atual)")

    # Comando: status
    subparsers.add_parser("status", help="Status do sistema")

    # Comando: diff
    diff_parser = subparsers.add_parser("diff", help="Análise diferencial de memória")
    diff_parser.add_argument("project", help="Nome do projeto")
    diff_parser.add_argument("--period", type=int, default=7, help="Dias do período (padrão: 7)")
    diff_parser.add_argument("--start", dest="start_date", help="Data de início (ISO format)")
    diff_parser.add_argument("--end", dest="end_date", help="Data de fim (ISO format)")
    diff_parser.add_argument("--gc-threshold", type=float, default=0.3, help="Threshold para GC risk")
    diff_parser.add_argument("--output", type=Path, help="Arquivo de saída")
    diff_parser.add_argument("--format", choices=["markdown", "json"], default="markdown")

    # Comando: dream
    dream_parser = subparsers.add_parser("dream", help="Extração automática de memórias")
    dream_parser.add_argument("--since", type=int, default=7, dest="since_days")
    dream_parser.add_argument("--apply", action="store_true", dest="apply")

    # Comando: remember
    remember_parser = subparsers.add_parser("remember", help="Revisão e promoção de memórias")
    remember_parser.add_argument("--apply", action="store_true", dest="apply")

    # Comando: gc
    gc_parser = subparsers.add_parser("gc", help="Garbage collection de memórias")
    gc_parser.add_argument("--threshold", type=int, default=7, dest="threshold_days")
    gc_parser.add_argument("--apply", action="store_true", dest="apply")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Comando: init (alias direto)
    if args.command == "init":
        _run_init(getattr(args, 'project', None))
        sys.exit(0)

    # Comando setup
    if args.command == "setup":
        from cerebro.cerebro_setup import setup_claude_desktop, setup_hooks, setup_ocerebro_dir

        if args.subcommand == "claude":
            success = setup_claude_desktop()
            sys.exit(0 if success else 1)
        elif args.subcommand == "hooks":
            success = setup_hooks(args.project)
            sys.exit(0 if success else 1)
        elif args.subcommand == "init":
            _run_init(getattr(args, 'project', None))
            sys.exit(0)
        else:
            setup_ocerebro_dir(args.project)
            setup_hooks(args.project)
            setup_claude_desktop()
            sys.exit(0)

    # Inicializa CLI
    cli = CerebroCLI(args.cerebro_path)

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
    elif args.command == "status":
        result = cli.status()
    elif args.command == "diff":
        result = cli.diff(
            args.project,
            period_days=args.period if not args.start_date else None,
            start_date=args.start_date,
            end_date=args.end_date,
            gc_threshold=args.gc_threshold,
            output=args.output,
            format=args.format
        )
    elif args.command == "dream":
        result = cli.dream(since_days=args.since_days, dry_run=not args.apply)
    elif args.command == "remember":
        result = cli.remember(dry_run=not args.apply)
    elif args.command == "gc":
        result = cli.gc_cmd(threshold_days=args.threshold_days, dry_run=not args.apply)
    else:
        parser.print_help()
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()

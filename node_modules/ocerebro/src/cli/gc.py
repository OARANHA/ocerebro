"""Comando cerebro gc - Garbage collection de memórias.

Replica a lógica de garbage collection do Claude Code baseada em mtime.

Uso:
    cerebro gc                      # Lista candidatas (dry-run)
    cerebro gc --threshold 14       # Threshold de 14 dias
    cerebro gc --apply              # Aplica GC diretamente
"""

import argparse
from pathlib import Path
from typing import Optional

from src.core.paths import get_auto_mem_path
from src.forgetting.gc import GarbageCollector


def cmd_gc(
    project_root: Optional[Path] = None,
    threshold_days: int = 7,
    dry_run: bool = True
) -> str:
    """
    Executa garbage collection de memórias.

    Args:
        project_root: Raiz do projeto (default: git root)
        threshold_days: Dias para considerar memória stale (default: 7)
        dry_run: Se True, apenas lista candidatas, não remove

    Returns:
        Relatório do GC
    """
    # Resolve memory_dir
    memory_dir = get_auto_mem_path(project_root)

    # Executa GC
    gc = GarbageCollector(memory_dir)
    results = gc.run_gc(
        memory_dir=memory_dir,
        archive_threshold_days=threshold_days,
        deletion_threshold_days=threshold_days * 4,  # 4x para deleção
        dry_run=dry_run
    )

    # Gera relatório
    return gc.generate_gc_report(results)


def main():
    """Entry point do comando gc"""
    parser = argparse.ArgumentParser(
        prog="cerebro gc",
        description="Garbage collection de memórias"
    )

    parser.add_argument(
        "--threshold",
        type=int,
        default=7,
        dest="threshold_days",
        help="Dias para considerar memória stale (padrão: 7)"
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        dest="apply",
        help="Aplicar GC (padrão: dry-run)"
    )

    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        dest="project_root",
        help="Raiz do projeto (padrão: git root)"
    )

    args = parser.parse_args()

    result = cmd_gc(
        project_root=args.project_root,
        threshold_days=args.threshold_days,
        dry_run=not args.apply
    )

    print(result)


if __name__ == "__main__":
    main()

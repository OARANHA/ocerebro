"""Comando cerebro dream - Extração automática de memórias.

Replica o comando extractMemories do Claude Code (bloqueado por tengu_passport_quail=false).

Uso:
    cerebro dream                 # Extrai memórias dos últimos 7 dias (dry-run)
    cerebro dream --since 14      # Extrai memórias dos últimos 14 dias
    cerebro dream --apply         # Aplica extração diretamente
"""

import argparse
from pathlib import Path
from typing import Optional

from src.core.paths import get_auto_mem_path
from src.consolidation.dream import run_dream, generate_dream_report


def cmd_dream(
    project_root: Optional[Path] = None,
    since_days: int = 7,
    dry_run: bool = True
) -> str:
    """
    Executa extração automática de memórias (dream).

    Args:
        project_root: Raiz do projeto (default: git root)
        since_days: Dias para analisar (default: 7)
        dry_run: Se True, apenas simula, não modifica nada

    Returns:
        Relatório da extração
    """
    # Resolve memory_dir
    memory_dir = get_auto_mem_path(project_root)

    # Executa dream
    result = run_dream(
        memory_dir=memory_dir,
        since_days=since_days,
        dry_run=dry_run
    )

    # Gera relatório
    return generate_dream_report(result)


def main():
    """Entry point do comando dream"""
    parser = argparse.ArgumentParser(
        prog="cerebro dream",
        description="Extração automática de memórias (replica extractMemories do Claude Code)"
    )

    parser.add_argument(
        "--since",
        type=int,
        default=7,
        dest="since_days",
        help="Dias para analisar (padrão: 7)"
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        dest="apply",
        help="Aplicar extração (padrão: dry-run)"
    )

    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        dest="project_root",
        help="Raiz do projeto (padrão: git root)"
    )

    args = parser.parse_args()

    result = cmd_dream(
        project_root=args.project_root,
        since_days=args.since_days,
        dry_run=not args.apply
    )

    print(result)


if __name__ == "__main__":
    main()

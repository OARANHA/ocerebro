"""Comando cerebro remember - Revisão e promoção de memórias.

Replica o comando /remember do Claude Code (bloqueado por USER_TYPE === 'ant').

Uso:
    cerebro remember                 # Revisão (dry-run)
    cerebro remember --apply         # Aplica promoções automaticamente
"""

import argparse
from pathlib import Path
from typing import Optional

from src.consolidation.remember import run_remember, generate_remember_report


def cmd_remember(
    project_root: Optional[Path] = None,
    dry_run: bool = True
) -> str:
    """
    Executa fluxo de revisão e promoção de memórias (remember).

    Args:
        project_root: Raiz do projeto (default: git root)
        dry_run: Se True, apenas gera relatório, não aplica

    Returns:
        Relatório do remember
    """
    # Executa remember
    report = run_remember(
        project_root=project_root,
        dry_run=dry_run
    )

    # Gera relatório
    return generate_remember_report(report)


def main():
    """Entry point do comando remember"""
    parser = argparse.ArgumentParser(
        prog="cerebro remember",
        description="Revisão e promoção de memórias (replica /remember do Claude Code)"
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        dest="apply",
        help="Aplicar promoções (padrão: dry-run)"
    )

    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        dest="project_root",
        help="Raiz do projeto (padrão: git root)"
    )

    args = parser.parse_args()

    result = cmd_remember(
        project_root=args.project_root,
        dry_run=not args.apply
    )

    print(result)


if __name__ == "__main__":
    main()

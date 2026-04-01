"""Permite executar como: python -m cerebro setup

Comandos:
    python -m cerebro setup          - Setup completo
    python -m cerebro setup claude   - Configura Claude Desktop
    python -m cerebro setup init     - Cria .cerebro/ e hooks.yaml
"""

import sys
from pathlib import Path

# Adiciona parent ao path para imports
parent_path = Path(__file__).parent.parent
sys.path.insert(0, str(parent_path))

from cerebro.cerebro_setup import main

if __name__ == "__main__":
    main()

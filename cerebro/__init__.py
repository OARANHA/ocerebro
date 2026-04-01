"""Cerebro - Sistema de Memória para Agentes de Código

Usage:
    cerebro setup          - Configurar MCP Server automaticamente
    cerebro memory <proj>  - Ver memória do projeto
    cerebro search <query> - Buscar memórias
    cerebro checkpoint <proj> - Criar checkpoint
    cerebro status         - Status do sistema
"""

import sys
from pathlib import Path

# Adiciona src ao path para imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from cerebro_setup import main as setup_main


def main():
    """Entry point principal do cerebro"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "setup":
        setup_main()
    elif command == "memory":
        from cli.main import CerebroCLI
        cli = CerebroCLI(Path(".cerebro"))
        if len(sys.argv) < 3:
            print("Erro: projeto é obrigatório")
            print("Uso: cerebro memory <nome-do-projeto>")
            sys.exit(1)
        print(cli.memory(sys.argv[2]))
    elif command == "search":
        from cli.main import CerebroCLI
        cli = CerebroCLI(Path(".cerebro"))
        if len(sys.argv) < 3:
            print("Erro: query é obrigatória")
            print("Uso: cerebro search <termo-de-busca>")
            sys.exit(1)
        query = sys.argv[2]
        project = sys.argv[3] if len(sys.argv) > 3 else None
        print(cli.search(query, project=project))
    elif command == "checkpoint":
        from cli.main import CerebroCLI
        cli = CerebroCLI(Path(".cerebro"))
        if len(sys.argv) < 3:
            print("Erro: projeto é obrigatório")
            print("Uso: cerebro checkpoint <nome-do-projeto>")
            sys.exit(1)
        print(cli.checkpoint(sys.argv[2]))
    elif command == "status":
        from cli.main import CerebroCLI
        cli = CerebroCLI(Path(".cerebro"))
        print(cli.status())
    elif command == "promote":
        from cli.main import CerebroCLI
        cli = CerebroCLI(Path(".cerebro"))
        if len(sys.argv) < 4:
            print("Erro: projeto e draft_id são obrigatórios")
            print("Uso: cerebro promote <projeto> <draft_id>")
            sys.exit(1)
        print(cli.promote(sys.argv[2], sys.argv[3]))
    elif command == "gc":
        from cli.main import CerebroCLI
        cli = CerebroCLI(Path(".cerebro"))
        print(cli.gc())
    else:
        print(f"Comando desconhecido: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

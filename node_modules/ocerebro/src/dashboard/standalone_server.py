"""Servidor standalone do Dashboard do OCerebro - roda como processo separado"""

import os
import sys
from pathlib import Path

# Adiciona project root ao path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.dashboard.server import DashboardServer
from src.mcp.server import CerebroMCP

def main():
    """Inicia o servidor standalone"""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7999
    cerebro_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    # Inicializa componentes com o path correto
    mcp = CerebroMCP(cerebro_path=cerebro_path)

    dashboard = DashboardServer(
        cerebro_path=mcp.cerebro_path,
        metadata_db=mcp.metadata_db,
        embeddings_db=mcp.embeddings_db,
        entities_db=mcp.entities_db
    )

    if dashboard.start(port):
        # Salva PID para poder ser morto quando precisar trocar de contexto
        pid_file = Path.home() / ".ocerebro_dashboard.pid"
        pid_file.write_text(str(os.getpid()), encoding="utf-8")

        print(f"Dashboard rodando em http://localhost:{port}")
        print(f"Cerebro path: {mcp.cerebro_path}")
        print(f"PID: {os.getpid()}")

        # Mantém vivo
        import time
        while True:
            time.sleep(3600)  # Dorme por 1 hora, loop infinito
    else:
        print(f"Falha ao iniciar dashboard na porta {port}")
        sys.exit(1)

if __name__ == "__main__":
    main()

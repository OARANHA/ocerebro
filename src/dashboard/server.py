"""Servidor web do Dashboard do OCerebro"""

import socket
import threading
import webbrowser
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn


class DashboardServer:
    """
    Servidor FastAPI para o dashboard do OCerebro.

    Responsabilidades:
    - Montar app FastAPI com static files e API
    - Iniciar servidor uvicorn em thread daemon
    - Verificar se já está rodando
    - Abrir browser automaticamente
    """

    def __init__(
        self,
        cerebro_path: Path,
        metadata_db,
        embeddings_db,
        entities_db
    ):
        """
        Inicializa o servidor do dashboard.

        Args:
            cerebro_path: Path para o diretório .cerebro
            metadata_db: Instância do MetadataDB
            embeddings_db: Instância do EmbeddingsDB
            entities_db: Instância do EntitiesDB
        """
        self.cerebro_path = cerebro_path
        self.metadata_db = metadata_db
        self.embeddings_db = embeddings_db
        self.entities_db = entities_db

        self.app = self._create_app()
        self._server_thread: Optional[threading.Thread] = None
        self._port: Optional[int] = None

    def _create_app(self) -> FastAPI:
        """Cria e configura o app FastAPI"""
        app = FastAPI(
            title="OCerebro Dashboard",
            description="Dashboard visual para memória do OCerebro",
            version="0.3.0"
        )

        # CORS para permitir requests do browser local
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Monta static files
        static_path = Path(__file__).parent / "static"
        if static_path.exists():
            app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

        # Monta API router
        from src.dashboard.api import create_router
        router = create_router(
            self.metadata_db,
            self.embeddings_db,
            self.entities_db,
            self.cerebro_path
        )
        app.include_router(router)

        # Página principal
        @app.get("/")
        async def root():
            from fastapi.responses import FileResponse
            index_path = static_path / "index.html"
            if index_path.exists():
                return FileResponse(str(index_path))
            return {"error": "index.html not found"}

        return app

    def is_running(self, port: int = 7999) -> bool:
        """
        Verifica se o servidor já está rodando na porta.

        Args:
            port: Porta para verificar

        Returns:
            True se já estiver rodando
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def start(self, port: int = 7999) -> bool:
        """
        Inicia o servidor em thread daemon.

        Args:
            port: Porta para escutar

        Returns:
            True se iniciado com sucesso
        """
        if self.is_running(port):
            return True

        try:
            self._port = port

            def run_server():
                uvicorn.run(
                    self.app,
                    host="127.0.0.1",
                    port=port,
                    log_level="error",
                    access_log=False
                )

            self._server_thread = threading.Thread(
                target=run_server,
                daemon=True,
                name="dashboard-server"
            )
            self._server_thread.start()

            # Aguarda servidor estar pronto
            import time
            for _ in range(50):  # 5 segundos max
                time.sleep(0.1)
                if self.is_running(port):
                    return True

            return False
        except Exception:
            return False

    def open_browser(self, port: int = 7999) -> bool:
        """
        Abre o dashboard no browser padrão.

        Args:
            port: Porta do servidor

        Returns:
            True se abriu com sucesso
        """
        try:
            url = f"http://localhost:{port}"
            webbrowser.open(url)
            return True
        except Exception:
            return False

    def get_status(self) -> dict:
        """Retorna status do servidor"""
        return {
            "running": self.is_running(self._port) if self._port else False,
            "port": self._port,
            "thread_alive": self._server_thread.is_alive() if self._server_thread else False
        }

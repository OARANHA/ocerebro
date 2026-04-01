"""Gerenciamento de sessão e detecção de projeto"""

import uuid
import yaml
from pathlib import Path
from typing import Optional


class SessionManager:
    """
    Gerencia session ID e detecção de projeto.

    Session ID é persistido em .cerebro_session para reutilização
    entre reinícios da sessão.

    Detecção de projeto usa cerebro-project.yaml ou fallback para
    nome do diretório.
    """

    def __init__(self, cerebro_path: Path):
        """
        Inicializa o SessionManager.

        Args:
            cerebro_path: Diretório base do Cerebro
        """
        self.cerebro_path = cerebro_path
        self._session_file = cerebro_path / ".cerebro_session"

    def get_session_id(self) -> str:
        """
        Obtém ou cria um session ID.

        Reusa session ID existente se disponível, caso contrário
        cria um novo e persiste em .cerebro_session.

        Returns:
            Session ID no formato sess_XXXXXXXX
        """
        if self._session_file.exists():
            return self._session_file.read_text().strip()

        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        self._session_file.write_text(session_id)
        return session_id

    def detect_project(self, project_dir: Path) -> str:
        """
        Detecta o ID do projeto a partir do diretório.

        Prioridade:
        1. project_id em .claude/cerebro-project.yaml
        2. Nome do diretório do projeto

        Args:
            project_dir: Diretório do projeto

        Returns:
            ID do projeto
        """
        cerebro_yaml = project_dir / ".claude" / "cerebro-project.yaml"

        if cerebro_yaml.exists():
            config = yaml.safe_load(cerebro_yaml.read_text())
            return config.get("project_id", project_dir.name)

        return project_dir.name

    def clear_session(self) -> None:
        """
        Limpa o session ID (fim de sessão).

        Remove o arquivo .cerebro_session.
        """
        if self._session_file.exists():
            self._session_file.unlink()

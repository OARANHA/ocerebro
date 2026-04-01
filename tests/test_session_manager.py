"""Testes para SessionManager"""

import pytest
from pathlib import Path
from src.core.session_manager import SessionManager


class TestSessionManager:

    def test_get_session_id_new(self, tmp_path):
        """Cria novo session ID se não existe"""
        manager = SessionManager(tmp_path)
        session_id = manager.get_session_id()

        assert session_id.startswith("sess_")
        assert (tmp_path / ".cerebro_session").exists()

    def test_get_session_id_existing(self, tmp_path):
        """Reusa session ID existente"""
        manager = SessionManager(tmp_path)
        session_id1 = manager.get_session_id()
        session_id2 = manager.get_session_id()

        assert session_id1 == session_id2

    def test_detect_project_from_cerebro_yaml(self, tmp_path):
        """Detecta projeto de cerebro-project.yaml"""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "cerebro-project.yaml").write_text(
            "project_id: my-project\nproject_name: My Project\n"
        )

        manager = SessionManager(tmp_path)
        project = manager.detect_project(project_dir)

        assert project == "my-project"

    def test_detect_project_fallback_to_dirname(self, tmp_path):
        """Fallback para nome do diretório"""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        manager = SessionManager(tmp_path)
        project = manager.detect_project(project_dir)

        assert project == "my-project"

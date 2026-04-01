"""Testes para YAMLStorage"""

import pytest
from pathlib import Path
from src.working.yaml_storage import YAMLStorage


class TestYAMLStorage:

    def test_write_session(self, tmp_cerebro_dir):
        """Escreve sessão em YAML"""
        storage = YAMLStorage(tmp_cerebro_dir / "working")

        storage.write_session("test-project", "sess_abc123", {
            "status": "in_progress",
            "todo": ["finalizar testes"],
            "last_changes": ["auth-module refactor"]
        })

        yaml_file = tmp_cerebro_dir / "working" / "test-project" / "sessions" / "sess_abc123.yaml"
        assert yaml_file.exists()
        content = yaml_file.read_text()
        assert "in_progress" in content

    def test_read_session(self, tmp_cerebro_dir):
        """Lê sessão de YAML"""
        storage = YAMLStorage(tmp_cerebro_dir / "working")

        storage.write_session("test-project", "sess_abc123", {
            "status": "in_progress",
            "todo": ["teste"]
        })

        session = storage.read_session("test-project", "sess_abc123")
        assert session["status"] == "in_progress"

    def test_write_feature(self, tmp_cerebro_dir):
        """Escreve feature em YAML"""
        storage = YAMLStorage(tmp_cerebro_dir / "working")

        storage.write_feature("test-project", "feat-auth", {
            "status": "in_progress",
            "events_range": {"from": "evt_001", "to": "evt_010"}
        })

        yaml_file = tmp_cerebro_dir / "working" / "test-project" / "features" / "feat-auth.yaml"
        assert yaml_file.exists()

    def test_list_sessions(self, tmp_cerebro_dir):
        """Lista sessões de um projeto"""
        storage = YAMLStorage(tmp_cerebro_dir / "working")

        storage.write_session("test-project", "sess_001", {"status": "active"})
        storage.write_session("test-project", "sess_002", {"status": "active"})

        sessions = storage.list_sessions("test-project")
        assert len(sessions) == 2

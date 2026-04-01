"""Testes para CheckpointManager"""

import pytest
from src.consolidation.checkpoints import CheckpointManager, CheckpointTrigger


class TestCheckpointManager:

    def test_detect_feature_done(self, tmp_path):
        """Detecta fim de feature por testes passando"""
        manager = CheckpointManager(tmp_path)

        # Simula testes passando após mudanças
        trigger = manager.check_triggers({
            "tests_passed": True,
            "files_changed": ["src/auth.py"]
        })

        assert CheckpointTrigger.FEATURE_DONE in trigger

    def test_detect_session_end(self, tmp_path):
        """Detecta fim de sessão"""
        manager = CheckpointManager(tmp_path)

        trigger = manager.check_triggers({
            "session_ending": True
        })

        assert CheckpointTrigger.SESSION_END in trigger

    def test_detect_error_critical(self, tmp_path):
        """Detecta erro crítico"""
        manager = CheckpointManager(tmp_path)

        trigger = manager.check_triggers({
            "error_severity": "critical"
        })

        assert CheckpointTrigger.ERROR_CRITICAL in trigger

    def test_no_trigger(self, tmp_path):
        """Nenhum trigger ativado"""
        manager = CheckpointManager(tmp_path)

        trigger = manager.check_triggers({
            "random_event": True
        })

        assert len(trigger) == 0

    def test_should_checkpoint(self, tmp_path):
        """Verifica se deve fazer checkpoint"""
        manager = CheckpointManager(tmp_path)

        assert manager.should_checkpoint({"tests_passed": True, "files_changed": ["src/auth.py"]})
        assert not manager.should_checkpoint({"random": True})

    def test_get_trigger_reason(self, tmp_path):
        """Obtém motivo do trigger"""
        manager = CheckpointManager(tmp_path)

        reason = manager.get_trigger_reason({
            "tests_passed": True,
            "files_changed": ["src/auth.py"]
        })

        assert "Feature concluída" in reason

"""Testes para GuardRails"""

import pytest
from datetime import datetime, timedelta, timezone
from src.forgetting.guard_rails import GuardRails


class TestGuardRails:

    def test_never_delete_critical_decision(self, tmp_path):
        """Não deleta decisão crítica"""
        rails = GuardRails(tmp_path / "config.yaml")

        can_delete = rails.can_delete({
            "type": "decision",
            "tags": ["critical"]
        })

        assert can_delete is False

    def test_never_delete_high_severity_error(self, tmp_path):
        """Não deleta erro de alta severidade"""
        rails = GuardRails(tmp_path / "config.yaml")

        can_delete = rails.can_delete({
            "type": "error",
            "severity": "high"
        })

        assert can_delete is False

    def test_can_delete_normal_memory(self, tmp_path):
        """Pode deletar memória normal"""
        rails = GuardRails(tmp_path / "config.yaml")

        can_delete = rails.can_delete({
            "type": "session",
            "status": "completed"
        })

        assert can_delete is True

    def test_should_archive_old_memory(self, tmp_path):
        """Deve arquivar memória antiga"""
        rails = GuardRails(tmp_path / "config.yaml")

        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat().replace("+00:00", "Z")

        should_archive = rails.should_archive({
            "layer": "raw",
            "created_at": old_date
        }, days_threshold=30)

        assert should_archive is True

    def test_should_not_archive_recent_memory(self, tmp_path):
        """Não deve arquivar memória recente"""
        rails = GuardRails(tmp_path / "config.yaml")

        recent_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat().replace("+00:00", "Z")

        should_archive = rails.should_archive({
            "layer": "raw",
            "created_at": recent_date
        }, days_threshold=30)

        assert should_archive is False

    def test_is_protected(self, tmp_path):
        """Verifica se memória está protegida"""
        rails = GuardRails(tmp_path / "config.yaml")

        assert rails.is_protected({"type": "error", "severity": "high"})
        assert not rails.is_protected({"type": "session"})

    def test_get_archive_threshold(self, tmp_path):
        """Obtém threshold de arquivamento por camada"""
        rails = GuardRails(tmp_path / "config.yaml")

        # Thresholds default quando não há config
        assert rails.get_archive_threshold("raw") == 30
        assert rails.get_archive_threshold("working") == 90
        assert rails.get_archive_threshold("unknown") == 90

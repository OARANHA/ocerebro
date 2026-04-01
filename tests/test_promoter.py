"""Testes para Promoter"""

import pytest
from src.consolidation.promoter import Promoter, PromotionResult
from src.working.yaml_storage import YAMLStorage
from src.official.markdown_storage import MarkdownStorage


class TestPromoter:

    def test_promote_session_to_decision(self, tmp_cerebro_dir):
        """Promove sessão para decisão"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        # Cria draft de sessão
        working.write_session("test-project", "sess_abc", {
            "id": "sess_abc",
            "type": "session",
            "session_id": "sess_abc",
            "summary": {
                "total_events": 10,
                "files_changed": ["src/auth.py", "tests/test_auth.py"],
                "tests_passed": 5,
                "tests_failed": 0
            },
            "events_range": {"from": "evt_001", "to": "evt_010"},
            "status": "draft"
        })

        result = promoter.promote_session("test-project", "sess_abc", "decision")

        assert result is not None
        assert result.success is True
        assert result.source_id == "sess_abc"
        assert result.target_type == "decision"

        # Verifica que foi criado em official
        frontmatter, content = official.read_decision("test-project", "sess_abc")
        assert frontmatter is not None
        assert "auth.py" in content

    def test_promote_feature_to_decision(self, tmp_cerebro_dir):
        """Promove feature para decisão"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        working.write_feature("test-project", "feat-auth", {
            "id": "feat-auth",
            "type": "feature",
            "summary": {
                "total_events": 20,
                "files_changed": ["src/auth.py"]
            },
            "status": "draft"
        })

        result = promoter.promote_feature("test-project", "feat-auth", "decision")

        assert result is not None
        assert result.success is True

    def test_promote_session_to_error(self, tmp_cerebro_dir):
        """Promove sessão com erro para official"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        working.write_session("test-project", "sess_error", {
            "id": "sess_error",
            "type": "session",
            "critical_errors": [
                {"type": "deadlock", "context": {"message": "Pool exhausted"}}
            ],
            "status": "draft"
        })

        result = promoter.promote_session("test-project", "sess_error", "error")

        assert result is not None
        assert result.success is True
        assert result.target_type == "error"

        # Verifica que foi criado em official
        frontmatter, content = official.read_error("test-project", "sess_error")
        assert frontmatter is not None
        assert frontmatter["type"] == "error"

    def test_promote_error_without_errors(self, tmp_cerebro_dir):
        """Tenta promover como erro sem erros críticos"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        working.write_session("test-project", "sess_no_error", {
            "id": "sess_no_error",
            "type": "session",
            "critical_errors": [],
            "status": "draft"
        })

        result = promoter.promote_session("test-project", "sess_no_error", "error")

        assert result is not None
        assert result.success is False
        assert result.metadata["reason"] == "no_critical_errors"

    def test_promote_nonexistent_session(self, tmp_cerebro_dir):
        """Tenta promover sessão inexistente"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        result = promoter.promote_session("test-project", "nonexistent", "decision")

        assert result is None

    def test_promote_with_review_approve(self, tmp_cerebro_dir):
        """Promove com revisão aprovada"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        working.write_session("test-project", "sess_review", {
            "id": "sess_review",
            "type": "session",
            "summary": {"total_events": 5},
            "status": "draft"
        })

        def approve_callback(draft):
            return "approve"

        result = promoter.promote_with_review(
            "test-project",
            "sess_review",
            "session",
            "decision",
            review_callback=approve_callback
        )

        assert result is not None
        assert result.success is True

    def test_promote_with_review_skip(self, tmp_cerebro_dir):
        """Promove com revisão skipada"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        working.write_session("test-project", "sess_skip", {
            "id": "sess_skip",
            "type": "session",
            "status": "draft"
        })

        def skip_callback(draft):
            return "skip"

        result = promoter.promote_with_review(
            "test-project",
            "sess_skip",
            "session",
            "decision",
            review_callback=skip_callback
        )

        assert result is None

    def test_promote_with_review_reject(self, tmp_cerebro_dir):
        """Promove com revisão rejeitada"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        working.write_session("test-project", "sess_reject", {
            "id": "sess_reject",
            "type": "session",
            "status": "draft"
        })

        def reject_callback(draft):
            return "reject"

        result = promoter.promote_with_review(
            "test-project",
            "sess_reject",
            "session",
            "decision",
            review_callback=reject_callback
        )

        assert result is None

        # Verifica que status foi atualizado para rejected
        session = working.read_session("test-project", "sess_reject")
        assert session["status"] == "rejected"

    def test_list_pending_promotions(self, tmp_cerebro_dir):
        """Lista promoções pendentes"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        # Cria drafts pendentes
        working.write_session("test-project", "sess_pending", {
            "id": "sess_pending",
            "status": "draft"
        })
        working.write_session("test-project", "sess_done", {
            "id": "sess_done",
            "status": "completed"
        })
        working.write_feature("test-project", "feat_pending", {
            "id": "feat_pending",
            "status": "needs_review",
            "needs_review": True
        })

        pending = promoter.list_pending_promotions("test-project")

        assert len(pending) == 2
        pending_ids = [p["id"] for p in pending]
        assert "sess_pending" in pending_ids
        assert "feat_pending" in pending_ids
        assert "sess_done" not in pending_ids

    def test_mark_promoted(self, tmp_cerebro_dir):
        """Marca draft como promovido"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        working.write_session("test-project", "sess_mark", {
            "id": "sess_mark",
            "type": "session",
            "status": "draft"
        })

        result = PromotionResult(
            success=True,
            source_type="session",
            source_id="sess_mark",
            target_type="decision",
            target_path="official/test-project/decisions/sess_mark.md",
            promoted_at="2026-03-31T00:00:00Z"
        )

        promoter.mark_promoted("test-project", "sess_mark", "session", result)

        session = working.read_session("test-project", "sess_mark")
        assert session["status"] == "promoted"
        assert session["promoted_to"] == "decision"

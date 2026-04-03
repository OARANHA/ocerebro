"""Testes de integracao do Scorer RFM com o pipeline de consolidacao"""

import pytest
from pathlib import Path
from datetime import datetime, timezone

from src.consolidation.promoter import Promoter
from src.consolidation.scorer import Scorer, ScoringConfig
from src.working.yaml_storage import YAMLStorage
from src.official.markdown_storage import MarkdownStorage


class TestScorerIntegration:
    """Testa integracao do Scorer no fluxo de Promoter"""

    def test_promote_decision_includes_rfms_scores(self, tmp_cerebro_dir):
        """Promocao para decision deve incluir 5 campos de score no frontmatter"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        # Cria draft de sessao
        working.write_session("test-project", "sess_rfms", {
            "id": "sess_rfms",
            "type": "session",
            "session_id": "sess_rfms",
            "summary": {
                "total_events": 10,
                "files_changed": ["src/auth.py"],
                "tests_passed": 5,
                "tests_failed": 0
            },
            "events_range": {"from": "evt_001", "to": "evt_010"},
            "status": "draft"
        })

        # Promove para decisao
        result = promoter.promote_session("test-project", "sess_rfms", "decision")

        assert result is not None
        assert result.success is True

        # Le frontmatter gerado
        frontmatter, content = official.read_decision("test-project", "sess_rfms")

        # Verifica os 5 campos de score
        assert "importance_score" in frontmatter
        assert "recency_score" in frontmatter
        assert "frequency_score" in frontmatter
        assert "links_score" in frontmatter
        assert "total_score" in frontmatter

        # Verifica que scores estao entre 0.0 e 1.0
        assert 0.0 <= frontmatter["importance_score"] <= 1.0
        assert 0.0 <= frontmatter["recency_score"] <= 1.0
        assert 0.0 <= frontmatter["frequency_score"] <= 1.0
        assert 0.0 <= frontmatter["links_score"] <= 1.0
        assert 0.0 <= frontmatter["total_score"] <= 1.0

        # Verifica que o total_score e a media ponderada correta
        config = ScoringConfig()
        expected_total = (
            config.recency_weight * frontmatter["recency_score"] +
            config.frequency_weight * frontmatter["frequency_score"] +
            config.importance_weight * frontmatter["importance_score"] +
            config.links_weight * frontmatter["links_score"]
        )
        assert abs(frontmatter["total_score"] - expected_total) < 0.01

    def test_promote_error_includes_rfms_scores(self, tmp_cerebro_dir):
        """Promocao para error deve incluir 5 campos de score no frontmatter"""
        working = YAMLStorage(tmp_cerebro_dir / "working")
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        promoter = Promoter(working, official)

        # Cria draft com erro critico
        working.write_session("test-project", "sess_error_rfms", {
            "id": "sess_error_rfms",
            "type": "session",
            "critical_errors": [
                {
                    "type": "deadlock",
                    "severity": "critical",
                    "context": {"message": "Pool exhausted"}
                }
            ],
            "status": "draft"
        })

        # Promove para erro
        result = promoter.promote_session("test-project", "sess_error_rfms", "error")

        assert result is not None
        assert result.success is True

        # Le frontmatter gerado
        frontmatter, content = official.read_error("test-project", "sess_error_rfms")

        # Verifica os 5 campos de score
        assert "importance_score" in frontmatter
        assert "recency_score" in frontmatter
        assert "frequency_score" in frontmatter
        assert "links_score" in frontmatter
        assert "total_score" in frontmatter

        # Verifica que scores estao entre 0.0 e 1.0
        assert 0.0 <= frontmatter["importance_score"] <= 1.0
        assert 0.0 <= frontmatter["recency_score"] <= 1.0
        assert 0.0 <= frontmatter["frequency_score"] <= 1.0
        assert 0.0 <= frontmatter["links_score"] <= 1.0
        assert 0.0 <= frontmatter["total_score"] <= 1.0

        # Erro com severity=critical deve ter importance_score = 1.0
        assert frontmatter["importance_score"] == 1.0

    def test_scorer_config_defaults(self):
        """Verifica pesos default do ScoringConfig"""
        config = ScoringConfig()

        assert config.recency_weight == 0.3
        assert config.frequency_weight == 0.2
        assert config.importance_weight == 0.3
        assert config.links_weight == 0.2

        # Soma dos pesos deve ser 1.0
        total = (
            config.recency_weight +
            config.frequency_weight +
            config.importance_weight +
            config.links_weight
        )
        assert total == 1.0

    def test_scorer_calculate_all_scores(self):
        """Testa metodo calculate_all_scores diretamente"""
        scorer = Scorer(ScoringConfig())

        memory = {
            "type": "decision",
            "last_accessed": datetime.now(timezone.utc),
            "access_count": 5,
            "status": "approved",
            "related_to": ["mem_1", "mem_2"]
        }

        scores = scorer.calculate_all_scores(memory)

        # Verifica chaves retornadas
        assert "recency_score" in scores
        assert "frequency_score" in scores
        assert "importance_score" in scores
        assert "links_score" in scores
        assert "total_score" in scores

        # Verifica ranges
        assert 0.0 <= scores["recency_score"] <= 1.0
        assert 0.0 <= scores["frequency_score"] <= 1.0
        assert 0.0 <= scores["importance_score"] <= 1.0
        assert 0.0 <= scores["links_score"] <= 1.0
        assert 0.0 <= scores["total_score"] <= 1.0

        # access_count=5 deve dar frequency_score > 0
        assert scores["frequency_score"] > 0.0

        # 2 related_to deve dar links_score = 0.5 (2 * 0.25)
        assert scores["links_score"] == 0.5

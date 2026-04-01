"""Testes para Scorer RFM"""

import pytest
from datetime import datetime, timedelta
from src.consolidation.scorer import Scorer, ScoringConfig


class TestScorer:

    def test_calculate_recency_score(self):
        """Calcula score de recência"""
        config = ScoringConfig()
        scorer = Scorer(config)

        recent = datetime.utcnow()
        old = datetime.utcnow() - timedelta(days=30)

        recent_score = scorer._recency_score(recent)
        old_score = scorer._recency_score(old)

        assert recent_score > old_score

    def test_calculate_total_score(self):
        """Calcula score total RFM"""
        config = ScoringConfig(
            recency_weight=0.3,
            frequency_weight=0.2,
            importance_weight=0.3,
            links_weight=0.2
        )
        scorer = Scorer(config)

        score = scorer.calculate({
            "last_accessed": datetime.utcnow(),
            "access_count": 10,
            "severity": "high",
            "related_to": ["err_001", "err_002"]
        })

        assert 0 <= score <= 1

    def test_decay_applied(self):
        """Decay reduz score com tempo"""
        config = ScoringConfig()
        scorer = Scorer(config)

        base_score = 0.8
        decayed = scorer.apply_decay(base_score, days=30, decay_rate=0.01)

        assert decayed < base_score

    def test_frequency_score_saturation(self):
        """Score de frequência satura em 1.0"""
        config = ScoringConfig()
        scorer = Scorer(config)

        # Muitos acessos
        score = scorer._frequency_score(100)
        assert score < 1.0
        assert score > 0.99

    def test_links_score_max(self):
        """Score de links tem máximo em 1.0"""
        config = ScoringConfig()
        scorer = Scorer(config)

        # Muitos links
        score = scorer._links_score(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"])
        assert score == 1.0

    def test_calculate_all_scores(self):
        """Calcula todos os scores individuais"""
        config = ScoringConfig()
        scorer = Scorer(config)

        scores = scorer.calculate_all_scores({
            "last_accessed": datetime.utcnow(),
            "access_count": 5,
            "severity": "high",
            "related_to": ["err_001"]
        })

        assert "recency_score" in scores
        assert "frequency_score" in scores
        assert "importance_score" in scores
        assert "links_score" in scores
        assert "total_score" in scores

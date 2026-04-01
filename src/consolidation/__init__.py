"""Consolidação do Cerebro: extração, scoring, promoção"""
from .checkpoints import CheckpointManager, CheckpointTrigger
from .scorer import Scorer, ScoringConfig
from .extractor import Extractor, ExtractionResult


class Promoter:
    """
    Promovedor de working para official.

    Stub - será implementado futuramente.
    """
    pass


__all__ = ["CheckpointManager", "CheckpointTrigger", "Extractor", "ExtractionResult", "Scorer", "ScoringConfig", "Promoter"]

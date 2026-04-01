"""Consolidação do Cerebro: extração, scoring, promoção"""
from .checkpoints import CheckpointManager, CheckpointTrigger
from .scorer import Scorer, ScoringConfig


class Extractor:
    """
    Extrator de eventos brutos para working.

    Stub - será implementado futuramente.
    """
    pass


class Promoter:
    """
    Promovedor de working para official.

    Stub - será implementado futuramente.
    """
    pass


__all__ = ["CheckpointManager", "CheckpointTrigger", "Extractor", "Scorer", "ScoringConfig", "Promoter"]

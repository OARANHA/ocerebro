"""Consolidação do Cerebro: extração, scoring, promoção"""
from .checkpoints import CheckpointManager, CheckpointTrigger


class Extractor:
    """
    Extrator de eventos brutos para working.

    Stub - será implementado futuramente.
    """
    pass


class Scorer:
    """
    Scorer RFM para eventos.

    Stub - será implementado no Task 11.
    """
    pass


class Promoter:
    """
    Promovedor de working para official.

    Stub - será implementado futuramente.
    """
    pass


__all__ = ["CheckpointManager", "CheckpointTrigger", "Extractor", "Scorer", "Promoter"]

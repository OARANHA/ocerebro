"""Consolidação do Cerebro: extração, scoring, promoção"""
from .checkpoints import CheckpointManager, CheckpointTrigger
from .scorer import Scorer, ScoringConfig
from .extractor import Extractor, ExtractionResult
from .promoter import Promoter, PromotionResult


__all__ = ["CheckpointManager", "CheckpointTrigger", "Extractor", "ExtractionResult", "Scorer", "ScoringConfig", "Promoter", "PromotionResult"]

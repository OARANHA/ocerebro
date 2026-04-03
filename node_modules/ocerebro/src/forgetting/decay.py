"""Gerenciamento de decay temporal para memórias"""

import math
from datetime import datetime, timezone
from typing import Dict, Any


class DecayManager:
    """
    Gerencia decay temporal de scores de memórias.

    Aplica decaimento exponencial baseado na idade da memória
    e configuração de decay rate.
    """

    def __init__(self, default_decay_rate: float = 0.01):
        """
        Inicializa o DecayManager.

        Args:
            default_decay_rate: Taxa de decaimento padrão
        """
        self.default_decay_rate = default_decay_rate

    def apply_decay(self, score: float, days: int, decay_rate: float = None) -> float:
        """
        Aplica decay temporal ao score.

        Args:
            score: Score base
            days: Dias de decaimento
            decay_rate: Taxa de decaimento (opcional, usa default se None)

        Returns:
            Score com decay aplicado
        """
        rate = decay_rate or self.default_decay_rate
        return score * math.exp(-rate * days)

    def calculate_age_days(self, created_at: str) -> int:
        """
        Calcula idade em dias a partir de timestamp ISO.

        Args:
            created_at: Timestamp ISO da criação

        Returns:
            Idade em dias
        """
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - created_dt).days

    def decay_for_memory(self, memory: Dict[str, Any], base_score: float) -> float:
        """
        Aplica decay para uma memória específica.

        Args:
            memory: Dados da memória
            base_score: Score base antes do decay

        Returns:
            Score com decay aplicado
        """
        created_at = memory.get("created_at")
        if not created_at:
            return base_score

        days = self.calculate_age_days(created_at)
        decay_rate = memory.get("decay_rate", self.default_decay_rate)

        return self.apply_decay(base_score, days, decay_rate)

    def get_decay_factor(self, days: int, decay_rate: float = None) -> float:
        """
        Obtém fator de decay (multiplicador).

        Args:
            days: Dias de decaimento
            decay_rate: Taxa de decaimento

        Returns:
            Fator de decay entre 0 e 1
        """
        rate = decay_rate or self.default_decay_rate
        return math.exp(-rate * days)

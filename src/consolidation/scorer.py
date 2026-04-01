"""Scorer RFM para memórias do Cerebro"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict
import math


@dataclass
class ScoringConfig:
    """Configuração de pesos do scoring RFM"""
    recency_weight: float = 0.3
    frequency_weight: float = 0.2
    importance_weight: float = 0.3
    links_weight: float = 0.2


class Scorer:
    """
    Calcula scores RFM (Recency, Frequency, Importance) para memórias.

    O score total é uma combinação ponderada de:
    - Recência: quão recente foi o último acesso
    - Frequência: quantas vezes foi acessada
    - Importância: baseada em severity/impact
    - Links: quantas conexões com outras memórias
    """

    def __init__(self, config: ScoringConfig):
        """
        Inicializa o Scorer.

        Args:
            config: Configuração de pesos
        """
        self.config = config

    def calculate(self, memory: Dict[str, Any]) -> float:
        """
        Calcula score total RFM.

        Args:
            memory: Dados da memória

        Returns:
            Score entre 0.0 e 1.0
        """
        r = self._recency_score(memory.get("last_accessed"))
        f = self._frequency_score(memory.get("access_count", 0))
        i = self._importance_score(memory)
        l = self._links_score(memory.get("related_to", []))

        total = (
            self.config.recency_weight * r +
            self.config.frequency_weight * f +
            self.config.importance_weight * i +
            self.config.links_weight * l
        )

        return min(1.0, max(0.0, total))

    def _recency_score(self, last_accessed: datetime) -> float:
        """
        Score de recência (0-1).

        Usa decaimento exponencial baseado em dias desde último acesso.

        Args:
            last_accessed: Data do último acesso

        Returns:
            Score de recência
        """
        if not last_accessed:
            return 0.0

        # BUG-01 FIX: Usa timezone-aware datetime
        now = datetime.now(timezone.utc)
        # Normaliza para timezone-aware se last_accessed for naive (fallback de segurança)
        if last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=timezone.utc)
        days_ago = (now - last_accessed).days
        return math.exp(-0.05 * days_ago)

    def _frequency_score(self, access_count: int) -> float:
        """
        Score de frequência (0-1).

        Args:
            access_count: Número de acessos

        Returns:
            Score de frequência
        """
        return 1.0 - math.exp(-0.1 * access_count)

    def _importance_score(self, memory: Dict[str, Any]) -> float:
        """
        Score de importância baseado em severity/impact.

        WARN-03 FIX: Considera tanto errors (severity) quanto decisions (status)

        Args:
            memory: Dados da memória

        Returns:
            Score de importância
        """
        # WARN-03 FIX: Erros usam severity, decisions usam status
        mem_type = memory.get("type", "")

        if mem_type == "error":
            severity_map = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2}
            return severity_map.get(memory.get("severity", "low"), 0.2)

        if mem_type == "decision":
            # Decisões approved têm alta importância
            status_map = {
                "approved": 0.8,
                "superseded": 0.4,
                "deprecated": 0.1,
                "draft": 0.3
            }
            return status_map.get(memory.get("status", "draft"), 0.3)

        return 0.2

    def _links_score(self, related_to: list) -> float:
        """
        Score de links (0-1).

        Args:
            related_to: Lista de IDs relacionados

        Returns:
            Score de links
        """
        if not related_to:
            return 0.0
        return min(1.0, len(related_to) * 0.25)

    def apply_decay(self, score: float, days: int, decay_rate: float) -> float:
        """
        Aplica decay temporal ao score.

        Args:
            score: Score base
            days: Dias de decaimento
            decay_rate: Taxa de decaimento

        Returns:
            Score com decay aplicado
        """
        return score * math.exp(-decay_rate * days)

    def calculate_all_scores(self, memory: Dict[str, Any]) -> Dict[str, float]:
        """
        Calcula todos os scores individuais e total.

        Args:
            memory: Dados da memória

        Returns:
            Dicionário com todos os scores
        """
        # BUG-01 FIX: Usa timezone-aware datetime
        now = datetime.now(timezone.utc)
        last_accessed = memory.get("last_accessed")
        # Normaliza se for naive
        if last_accessed and isinstance(last_accessed, datetime) and last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=timezone.utc)

        r = self._recency_score(last_accessed)
        f = self._frequency_score(memory.get("access_count", 0))
        i = self._importance_score(memory)
        l = self._links_score(memory.get("related_to", []))

        total = (
            self.config.recency_weight * r +
            self.config.frequency_weight * f +
            self.config.importance_weight * i +
            self.config.links_weight * l
        )

        return {
            "recency_score": min(1.0, max(0.0, r)),
            "frequency_score": min(1.0, max(0.0, f)),
            "importance_score": min(1.0, max(0.0, i)),
            "links_score": min(1.0, max(0.0, l)),
            "total_score": min(1.0, max(0.0, total))
        }

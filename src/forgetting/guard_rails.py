"""Guard rails para forgetting do Cerebro"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import yaml


class GuardRails:
    """
    Guard rails para políticas de forgetting.

    Implementa regras de:
    - never_delete: memórias que nunca podem ser deletadas
    - always_archive: memórias que devem ser arquivadas após período
    """

    def __init__(self, config_path: Path):
        """
        Inicializa o GuardRails.

        Args:
            config_path: Path para arquivo de configuração YAML
        """
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """
        Carrega configuração.

        Returns:
            Dicionário de configuração
        """
        if not self.config_path.exists():
            return {
                "never_delete": ["decisions.critical", "errors.severity=high"],
                "always_archive": {"raw": 30, "working": 90}
            }

        return yaml.safe_load(self.config_path.read_text())

    def can_delete(self, memory: Dict[str, Any]) -> bool:
        """
        Verifica se pode deletar uma memória.

        Args:
            memory: Dados da memória

        Returns:
            True se pode deletar, False se está protegida
        """
        rules = self.config.get("never_delete", [])

        for rule in rules:
            if self._matches_rule(memory, rule):
                return False

        return True

    def _matches_rule(self, memory: Dict[str, Any], rule: str) -> bool:
        """
        Verifica se memória corresponde à regra.

        Args:
            memory: Dados da memória
            rule: Regra a verificar

        Returns:
            True se corresponde à regra
        """
        if rule == "decisions.critical":
            return memory.get("type") == "decision" and "critical" in memory.get("tags", [])

        if rule == "errors.severity=high":
            return memory.get("type") == "error" and memory.get("severity") in ["high", "critical"]

        if rule == "errors.impact=critical":
            return memory.get("type") == "error" and memory.get("impact") == "critical"

        return False

    def should_archive(self, memory: Dict[str, Any], days_threshold: int) -> bool:
        """
        Verifica se deve arquivar uma memória.

        Args:
            memory: Dados da memória
            days_threshold: Dias mínimos para arquivar

        Returns:
            True se deve arquivar
        """
        created = memory.get("created_at")
        if not created:
            return False

        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        days_old = (datetime.now(timezone.utc) - created_dt).days

        return days_old > days_threshold

    def get_archive_threshold(self, layer: str) -> int:
        """
        Obtém threshold de arquivamento por camada.

        Args:
            layer: Nome da camada (raw, working, official)

        Returns:
            Dias threshold para arquivamento
        """
        thresholds = self.config.get("always_archive", {})
        return thresholds.get(layer, 90)

    def is_protected(self, memory: Dict[str, Any]) -> bool:
        """
        Verifica se memória está protegida contra deleção.

        Args:
            memory: Dados da memória

        Returns:
            True se está protegida
        """
        return not self.can_delete(memory)

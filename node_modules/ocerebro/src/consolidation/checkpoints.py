"""Gerenciamento de triggers de checkpoint"""

from enum import Enum
from typing import Dict, List


class CheckpointTrigger(Enum):
    """Tipos de triggers de checkpoint"""
    FEATURE_DONE = "feature_done"
    SESSION_END = "session_end"
    ERROR_CRITICAL = "error_critical"
    MANUAL = "manual"


class CheckpointManager:
    """
    Gerencia triggers de checkpoint.

    Triggers disponíveis:
    - feature_done: Feature implementada com testes passando
    - session_end: Fim de sessão do desenvolvedor
    - error_critical: Erro crítico que deve ser documentado
    - manual: Trigger manual solicitada pelo usuário
    """

    def __init__(self, config_path):
        """
        Inicializa o CheckpointManager.

        Args:
            config_path: Path para configuração
        """
        self.config_path = config_path

    def check_triggers(self, context: Dict) -> List[CheckpointTrigger]:
        """
        Verifica triggers baseado no contexto.

        Args:
            context: Dicionário com dados do contexto

        Returns:
            Lista de triggers ativados
        """
        triggers = []

        if context.get("tests_passed") and context.get("files_changed"):
            triggers.append(CheckpointTrigger.FEATURE_DONE)

        if context.get("session_ending"):
            triggers.append(CheckpointTrigger.SESSION_END)

        if context.get("error_severity") in ["critical", "high"]:
            triggers.append(CheckpointTrigger.ERROR_CRITICAL)

        return triggers

    def should_checkpoint(self, context: Dict) -> bool:
        """
        Decide se deve fazer checkpoint.

        Args:
            context: Dicionário com dados do contexto

        Returns:
            True se deve fazer checkpoint, False caso contrário
        """
        return len(self.check_triggers(context)) > 0

    def get_trigger_reason(self, context: Dict) -> str:
        """
        Obtém descrição do motivo do checkpoint.

        Args:
            context: Dicionário com dados do contexto

        Returns:
            String descrevendo o motivo
        """
        triggers = self.check_triggers(context)

        if not triggers:
            return "Nenhum trigger ativado"

        reasons = []
        for trigger in triggers:
            if trigger == CheckpointTrigger.FEATURE_DONE:
                reasons.append("Feature concluída com testes passando")
            elif trigger == CheckpointTrigger.SESSION_END:
                reasons.append("Fim de sessão")
            elif trigger == CheckpointTrigger.ERROR_CRITICAL:
                reasons.append("Erro crítico detectado")
            elif trigger == CheckpointTrigger.MANUAL:
                reasons.append("Solicitação manual")

        return "; ".join(reasons)

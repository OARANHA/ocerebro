"""Captura de eventos core do Cerebro"""

from typing import Any, Dict, Optional
from pathlib import Path
from src.core.jsonl_storage import JSONLStorage
from src.core.event_schema import Event, EventType, EventOrigin
from src.hooks.custom_loader import HooksLoader, HookRunner


class CoreCaptures:
    """
    Captura de eventos core do Cerebro.

    Fornece métodos para capturar:
    - Tool calls (chamadas de ferramentas)
    - Git events (eventos do git)
    - Test results (resultados de testes)
    - Errors (erros críticos)

    Hooks customizados são executados automaticamente após cada captura.
    """

    def __init__(
        self,
        storage: JSONLStorage,
        project: str,
        session_id: str,
        hooks_config_path: Optional[Path] = None
    ):
        """
        Inicializa o CoreCaptures.

        Args:
            storage: Instância do JSONLStorage
            project: Nome do projeto
            session_id: ID da sessão
            hooks_config_path: Path para hooks.yaml (opcional)
        """
        self.storage = storage
        self.project = project
        self.session_id = session_id

        # Inicializa hooks loader e runner
        if hooks_config_path is None:
            hooks_config_path = Path("hooks.yaml")

        self.hooks_loader = HooksLoader(hooks_config_path)
        self.hooks_runner = HookRunner(self.hooks_loader, context={
            "project": project,
            "session_id": session_id
        })

    def _create_event(
        self,
        event_type: EventType,
        subtype: str,
        payload: Dict[str, Any],
        tags: list = None
    ) -> Event:
        """
        Cria e persiste evento, executando hooks customizados.

        Args:
            event_type: Tipo do evento
            subtype: Subtipo do evento
            payload: Dados do evento
            tags: Tags opcionais

        Returns:
            Evento criado
        """
        event = Event(
            project=self.project,
            origin=EventOrigin.CLAUDE_CODE,
            event_type=event_type,
            subtype=subtype,
            payload=payload,
            tags=tags or [],
            session_id=self.session_id
        )
        self.storage.append(event)

        # Executa hooks customizados para este evento
        self.hooks_runner.execute(event)

        return event

    def tool_call(self, tool: str, call_data: Dict[str, Any], result: Dict[str, Any]) -> Event:
        """
        Captura tool call.

        Args:
            tool: Nome da ferramenta
            call_data: Dados da chamada
            result: Resultado da execução

        Returns:
            Evento capturado
        """
        return self._create_event(
            EventType.TOOL_CALL,
            tool,
            {
                "call": call_data,
                "result": result
            }
        )

    def git_event(self, action: str, data: Dict[str, Any]) -> Event:
        """
        Captura git event.

        Args:
            action: Ação do git (commit, branch, merge, etc)
            data: Dados do evento

        Returns:
            Evento capturado
        """
        return self._create_event(
            EventType.GIT_EVENT,
            action,
            data
        )

    def test_result(self, test_type: str, test_name: str, status: str, duration: float, error: str = None) -> Event:
        """
        Captura test result.

        Args:
            test_type: Tipo de teste (unit, integration, e2e)
            test_name: Nome do teste
            status: Status (pass, fail, skip)
            duration: Duração em segundos
            error: Mensagem de erro (opcional)

        Returns:
            Evento capturado
        """
        payload = {
            "test_name": test_name,
            "status": status,
            "duration": duration
        }
        if error:
            payload["error"] = error

        return self._create_event(
            EventType.TEST_RESULT,
            test_type,
            payload
        )

    def error(self, error_type: str, context: Dict[str, Any]) -> Event:
        """
        Captura erro.

        Args:
            error_type: Tipo do erro
            context: Contexto do erro

        Returns:
            Evento capturado
        """
        return self._create_event(
            EventType.ERROR,
            error_type,
            context,
            tags=["error", "critical"]
        )

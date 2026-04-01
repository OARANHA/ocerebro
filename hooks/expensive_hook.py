"""Hook para log de operações custosas"""

import time
from src.core.event_schema import Event


def on_expensive_operation(event: Event, context: dict, config: dict) -> dict:
    """
    Log de operações custosas.

    Args:
        event: Evento de tool_call bash
        context: Contexto global
        config: Configuração do hook

    Returns:
        Informações da operação
    """
    log_threshold = config.get("log_threshold_seconds", 5)
    alert_threshold = config.get("alert_threshold_seconds", 30)

    payload = event.payload
    command = payload.get("command", "unknown")
    duration = payload.get("duration", 0)

    result = {
        "command": command,
        "duration": duration,
        "logged": False,
        "alerted": False
    }

    if duration >= log_threshold:
        result["logged"] = True
        result["log_message"] = f"Operação lenta: {command} ({duration:.2f}s)"

        if duration >= alert_threshold:
            result["alerted"] = True
            result["alert_message"] = f"ALERT: {command} levou {duration:.2f}s"

    return result

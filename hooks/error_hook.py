"""Hook para notificação de erros"""

from src.core.event_schema import Event


def on_error(event: Event, context: dict, config: dict) -> dict:
    """
    Notifica erros críticos.

    Args:
        event: Evento de erro
        context: Contexto global
        config: Configuração do hook

    Returns:
        Resultado da notificação
    """
    notify_severity = config.get("notify_severity", ["critical", "high"])
    channel = config.get("channel", "slack")
    include_stacktrace = config.get("include_stacktrace", True)

    payload = event.payload
    severity = payload.get("severity", "medium")
    error_type = payload.get("error_type", "Unknown")
    message = payload.get("message", "")

    result = {
        "severity": severity,
        "error_type": error_type,
        "message": message,
        "should_notify": severity in notify_severity
    }

    if result["should_notify"]:
        notification = {
            "channel": channel,
            "title": f"Erro {severity.upper()}: {error_type}",
            "text": message
        }

        if include_stacktrace and payload.get("stacktrace"):
            notification["stacktrace"] = payload["stacktrace"]

        result["notification"] = notification
        # Aqui integraria com Slack/Teams/etc
        # send_to_slack(notification)

    return result

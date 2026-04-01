"""Hook para log global de eventos"""

from src.core.event_schema import Event


def on_any_event(event: Event, context: dict, config: dict) -> dict:
    """
    Log genérico para todos os eventos.

    Args:
        event: Qualquer evento
        context: Contexto global
        config: Configuração do hook

    Returns:
        Informações do log
    """
    log_level = config.get("log_level", "info")
    exclude_subtypes = config.get("exclude_subtypes", [])

    # Pula subtipos excluídos
    if event.subtype in exclude_subtypes:
        return {"skipped": True, "reason": f"subtype {event.subtype} excluído"}

    return {
        "logged": True,
        "log_level": log_level,
        "event_type": event.event_type.value,
        "subtype": event.subtype,
        "project": event.project,
        "session_id": event.session_id
    }

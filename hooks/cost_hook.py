"""Hook para tracker de custo de LLM"""

from src.core.event_schema import Event


def on_llm_call(event: Event, context: dict, config: dict) -> dict:
    """
    Trackea custo de chamadas LLM.

    Args:
        event: Evento de tool_call LLM
        context: Contexto global
        config: Configuração do hook

    Returns:
        Informações de custo
    """
    log_cost = config.get("log_cost", True)
    monthly_budget = config.get("monthly_budget", 100.0)
    alert_percentage = config.get("alert_at_percentage", 80)

    payload = event.payload
    model = payload.get("model", "unknown")
    tokens = payload.get("tokens", {"input": 0, "output": 0})
    cost = payload.get("cost", 0.0)

    # Atualiza custo acumulado no contexto
    accumulated = context.get("llm_cost_accumulated", 0.0)
    context["llm_cost_accumulated"] = accumulated + cost

    result = {
        "model": model,
        "tokens": tokens,
        "current_cost": cost,
        "accumulated_cost": accumulated + cost,
        "budget": monthly_budget,
        "budget_remaining": monthly_budget - (accumulated + cost),
        "budget_used_percentage": ((accumulated + cost) / monthly_budget) * 100
    }

    # Alerta se aproximando do limite
    if result["budget_used_percentage"] >= alert_percentage:
        result["alert"] = f"Usou {result['budget_used_percentage']:.1f}% do budget mensal"

    return result

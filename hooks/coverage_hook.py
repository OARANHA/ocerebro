"""Hook para verificar cobertura de testes"""

from src.core.event_schema import Event


def on_test_result(event: Event, context: dict, config: dict) -> dict:
    """
    Verifica cobertura de testes após execução.

    Args:
        event: Evento de resultado de teste
        context: Contexto global
        config: Configuração do hook

    Returns:
        Resultado da verificação
    """
    min_coverage = config.get("min_coverage", 80)
    fail_below = config.get("fail_below_threshold", False)

    payload = event.payload
    coverage = payload.get("coverage", 0)

    result = {
        "min_coverage": min_coverage,
        "actual_coverage": coverage,
        "passed": coverage >= min_coverage
    }

    if coverage < min_coverage:
        msg = f"Cobertura {coverage}% abaixo do mínimo {min_coverage}%"
        if fail_below:
            result["action"] = "fail_build"
            result["message"] = msg
        else:
            result["action"] = "warn"
            result["message"] = msg

    return result

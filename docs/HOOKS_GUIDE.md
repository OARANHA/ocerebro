# Guia de Uso: Hooks Customizados do Cerebro

## Visão Geral

O sistema de hooks do Cerebro permite executar código customizado em resposta a eventos do sistema. Isso possibilita:

- Notificações externas (Slack, Teams, email)
- Validações e verificações automáticas
- Tracking de custos e métricas
- Integração com ferramentas externas
- Logs customizados

## Arquitetura

```
Evento → CoreCaptures → HooksLoader → HookRunner → Seu Hook
```

1. **Evento** é capturado (tool_call, test_result, error, etc.)
2. **CoreCaptures** persiste o evento e dispara hooks
3. **HooksLoader** carrega configuração do `hooks.yaml`
4. **HookRunner** executa os hooks匹配ndo o evento
5. **Seu Hook** processa o evento e retorna resultado

## Configuração

### 1. Criar `hooks.yaml`

Na raiz do projeto, crie `hooks.yaml`:

```yaml
hooks:
  - name: meu_hook_personalizado
    event_type: tool_call
    event_subtype: bash
    module_path: hooks/meu_hook.py
    function: on_bash_command
    config:
      log_threshold_seconds: 5
```

### 2. Estrutura do Hook

Cada hook é um módulo Python com uma função que recebe 3 parâmetros:

```python
# hooks/meu_hook.py
from src.core.event_schema import Event

def on_bash_command(event: Event, context: dict, config: dict) -> dict:
    """
    Hook para comandos bash.

    Args:
        event: Evento capturado
        context: Contexto global (project, session_id, etc.)
        config: Configuração do hook (do hooks.yaml)

    Returns:
        Dicionário com resultado do processamento
    """
    # Seu código aqui
    return {"processed": True}
```

## Tipos de Eventos

| Event Type | Subtypes | Descrição |
|------------|----------|-----------|
| `tool_call` | `bash`, `llm`, `glob`, `grep`, etc. | Chamada de ferramenta |
| `test_result` | `unit`, `integration`, `e2e` | Resultado de teste |
| `git_event` | `commit`, `branch`, `merge`, `push` | Evento do git |
| `error` | `command_failure`, `validation`, etc. | Erro crítico |
| `checkpoint_created` | `manual`, `auto` | Checkpoint criado |
| `promotion_performed` | `manual`, `auto` | Promoção realizada |
| `*` | Qualquer | Todos os eventos |

## Exemplos de Hooks

### 1. Notificação de Erros Críticos

```yaml
# hooks.yaml
hooks:
  - name: error_notifier
    event_type: error
    module_path: hooks/error_hook.py
    function: on_error
    config:
      notify_severity: ["critical", "high"]
      channel: slack
```

```python
# hooks/error_hook.py
from src.core.event_schema import Event

def on_error(event: Event, context: dict, config: dict) -> dict:
    severity = event.payload.get("severity", "medium")
    notify_severity = config.get("notify_severity", [])

    if severity not in notify_severity:
        return {"skipped": True, "reason": f"severity {severity} não configurada"}

    # Enviar notificação
    message = {
        "channel": config.get("channel", "slack"),
        "title": f"Erro {severity}: {event.payload.get('error_type')}",
        "text": event.payload.get("message")
    }
    # send_to_slack(message)

    return {"notified": True, "message": message}
```

### 2. Tracker de Custo LLM

```yaml
hooks:
  - name: llm_cost_tracker
    event_type: tool_call
    event_subtype: llm
    module_path: hooks/cost_hook.py
    function: on_llm_call
    config:
      monthly_budget: 100.0
      alert_at_percentage: 80
```

```python
# hooks/cost_hook.py
from src.core.event_schema import Event

def on_llm_call(event: Event, context: dict, config: dict) -> dict:
    budget = config.get("monthly_budget", 100.0)
    alert_pct = config.get("alert_at_percentage", 80)

    # Acumula custo no contexto
    accumulated = context.get("llm_cost_accumulated", 0.0)
    current_cost = event.payload.get("cost", 0.0)
    context["llm_cost_accumulated"] = accumulated + current_cost

    result = {
        "current_cost": current_cost,
        "accumulated": accumulated + current_cost,
        "budget_remaining": budget - (accumulated + current_cost),
        "budget_pct": ((accumulated + current_cost) / budget) * 100
    }

    if result["budget_pct"] >= alert_pct:
        result["alert"] = f"⚠️ {result['budget_pct']:.1f}% do budget usado"

    return result
```

### 3. Validação de Cobertura de Testes

```yaml
hooks:
  - name: coverage_validator
    event_type: test_result
    module_path: hooks/coverage_hook.py
    function: on_test_result
    config:
      min_coverage: 80
      fail_below: false
```

```python
# hooks/coverage_hook.py
from src.core.event_schema import Event

def on_test_result(event: Event, context: dict, config: dict) -> dict:
    min_cov = config.get("min_coverage", 80)
    fail_below = config.get("fail_below", False)

    coverage = event.payload.get("coverage", 0)
    passed = coverage >= min_cov

    result = {
        "min_coverage": min_cov,
        "actual": coverage,
        "passed": passed
    }

    if not passed:
        result["action"] = "fail" if fail_below else "warn"
        result["message"] = f"Cobertura {coverage}% abaixo de {min_cov}%"

    return result
```

### 4. Log de Operações Lentas

```yaml
hooks:
  - name: slow_operation_logger
    event_type: tool_call
    event_subtype: bash
    module_path: hooks/slow_hook.py
    function: on_slow_operation
    config:
      log_threshold: 5
      alert_threshold: 30
```

```python
# hooks/slow_hook.py
from src.core.event_schema import Event

def on_slow_operation(event: Event, context: dict, config: dict) -> dict:
    log_threshold = config.get("log_threshold", 5)
    alert_threshold = config.get("alert_threshold", 30)

    duration = event.payload.get("duration", 0)
    command = event.payload.get("command", "unknown")

    result = {"command": command, "duration": duration}

    if duration >= log_threshold:
        result["log"] = f"Operação lenta: {command} ({duration:.2f}s)"

        if duration >= alert_threshold:
            result["alert"] = f"⚠️ LENTO: {command} levou {duration:.2f}s"

    return result
```

## API Reference

### HookConfig

```python
@dataclass
class HookConfig:
    name: str           # Nome único do hook
    event_type: str     # Tipo de evento (* para todos)
    event_subtype: str  # Subtipo (None para qualquer)
    module_path: str    # Caminho do módulo Python
    function: str       # Nome da função
    config: dict        # Configuração específica
```

### Assinatura da Função

```python
def my_hook(event: Event, context: dict, config: dict) -> dict:
    """
    Args:
        event: Objeto Event com:
            - event_type: Tipo do evento
            - subtype: Subtipo
            - project: Nome do projeto
            - session_id: ID da sessão
            - payload: Dados do evento
            - tags: Tags associadas

        context: Dicionário compartilhado entre hooks
            - project: Nome do projeto
            - session_id: ID da sessão
            - llm_cost_accumulated: (exemplo) custo acumulado

        config: Configuração do hooks.yaml
            - Parâmetros específicos do hook

    Returns:
        dict: Resultado do processamento
    """
```

## Ferramenta MCP: cerebro_hooks

Se usando Claude Code com MCP Server, use a ferramenta `cerebro_hooks`:

### Listar Hooks

```
cerebro_hooks(action="list")
```

### Filtrar por Tipo de Evento

```
cerebro_hooks(action="list", event_type="tool_call")
```

### Ver Detalhes de um Hook

```
cerebro_hooks(action="info", hook_name="meu_hook")
```

### Testar Hooks

```
cerebro_hooks(action="test")
```

## Boas Práticas

1. **Hooks devem ser rápidos**: Executam sincronamente durante captura de eventos
2. **Trate erros gracefully**: Hooks não devem quebrar o fluxo principal
3. **Use contexto com cuidado**: Contexto é compartilhado entre execuções
4. **Logue appropriately**: Use níveis de log adequados (info, warn, error)
5. **Teste localmente**: Valide hooks antes de produção

## Troubleshooting

### Hook não está executando

1. Verifique se `hooks.yaml` está na raiz do projeto
2. Confirme que `event_type` e `event_subtype` estão corretos
3. Verifique se `module_path` está correto e arquivo existe
4. Confira se a função existe no módulo

### Erro ao carregar módulo

```
FileNotFoundError: Módulo não encontrado: hooks/meu_hook.py
```

- Use paths relativos à raiz do projeto
- Verifique se o arquivo existe
- Certifique-se de que há `__init__.py` no diretório `hooks/`

### Função não encontrada

```
AttributeError: Função my_func não encontrada em hooks/meu_hook.py
```

- Verifique o nome da função no `hooks.yaml`
- Confirme que a função está definida no módulo
- Atenção a typos e case sensitivity

## Próximos Passos

1. Crie seu primeiro hook simples (log)
2. Adicione configuração no `hooks.yaml`
3. Teste com `cerebro_hooks(action="test")`
4. Evolua para integrações externas

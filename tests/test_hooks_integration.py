"""Testes de integração para hooks customizados"""

import pytest
import yaml
from pathlib import Path
from src.hooks.custom_loader import HooksLoader, HookRunner
from src.core.event_schema import Event, EventType, EventOrigin


class TestHooksIntegration:
    """Testes de integração com hooks reais"""

    def test_load_sample_hooks_yaml(self):
        """Carrega hooks.yaml de exemplo"""
        hooks_file = Path("hooks.yaml")

        # Verifica se arquivo existe
        assert hooks_file.exists(), "hooks.yaml não encontrado"

        # Carrega e valida
        loader = HooksLoader(hooks_file)
        assert len(loader.hooks) > 0

    def test_coverage_hook_execution(self, tmp_path):
        """Executa hook de coverage"""
        # Cria hook mock no mesmo diretório que hooks.yaml
        hook_file = tmp_path / "coverage_hook.py"
        hook_file.write_text("""
def on_test_result(event, context, config):
    coverage = event.payload.get('coverage', 0)
    min_coverage = config.get('min_coverage', 80)
    if coverage < min_coverage:
        return {'passed': False, 'action': 'warn'}
    return {'passed': True, 'action': 'ok'}
""")

        # Configura hook
        hooks_yaml = tmp_path / "hooks.yaml"
        hooks_yaml.write_text(yaml.dump({
            "hooks": [{
                "name": "coverage_test",
                "event_type": "test_result",
                "module_path": str(hook_file),
                "function": "on_test_result",
                "config": {"min_coverage": 80}
            }]
        }))

        loader = HooksLoader(hooks_yaml)
        runner = HookRunner(loader)

        # Evento com cobertura baixa
        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TEST_RESULT,
            payload={"coverage": 65, "passed": True}
        )

        results = runner.execute(event)

        assert "coverage_test" in results
        assert results["coverage_test"]["success"] is True
        assert results["coverage_test"]["result"]["passed"] is False
        assert results["coverage_test"]["result"]["action"] == "warn"

    def test_cost_hook_execution(self, tmp_path):
        """Executa hook de custo LLM"""
        # Cria hook mock no mesmo diretório que hooks.yaml
        hook_file = tmp_path / "cost_hook.py"
        hook_file.write_text("""
def on_llm_call(event, context, config):
    accumulated = context.get('llm_cost_accumulated', 0)
    cost = event.payload.get('cost', 0)
    budget = config.get('monthly_budget', 100)
    alert_at = config.get('alert_at_percentage', 80)
    new_accumulated = accumulated + cost
    percentage = (new_accumulated / budget) * 100
    if percentage >= alert_at:
        return {'alert': True, 'percentage': percentage, 'accumulated_cost': new_accumulated}
    return {'alert': False, 'percentage': percentage, 'accumulated_cost': new_accumulated}
""")

        hooks_yaml = tmp_path / "hooks.yaml"
        hooks_yaml.write_text(yaml.dump({
            "hooks": [{
                "name": "cost_tracker",
                "event_type": "tool_call",
                "event_subtype": "llm",
                "module_path": str(hook_file),
                "function": "on_llm_call",
                "config": {"monthly_budget": 100.0, "alert_at_percentage": 80}
            }]
        }))

        loader = HooksLoader(hooks_yaml)
        runner = HookRunner(loader, context={"llm_cost_accumulated": 75.0})

        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="llm",
            payload={
                "model": "claude-sonnet-4",
                "tokens": {"input": 1000, "output": 500},
                "cost": 0.05
            }
        )

        results = runner.execute(event)

        assert "cost_tracker" in results
        assert results["cost_tracker"]["success"] is True
        # 75.05 / 100.0 = 75.05% - abaixo do alert threshold
        assert results["cost_tracker"]["result"]["accumulated_cost"] == 75.05

    def test_error_hook_execution(self, tmp_path):
        """Executa hook de erro"""
        # Cria hook mock
        hook_file = tmp_path / "error_hook.py"
        hook_file.write_text("""
def on_error(event, context, config):
    severity = event.payload.get('severity', 'low')
    notify_severity = config.get('notify_severity', [])
    channel = config.get('channel', 'email')
    if severity in notify_severity:
        return {'notified': True, 'should_notify': True, 'notification': f'Sending to {channel}'}
    return {'notified': False, 'should_notify': False}
""")

        hooks_yaml = tmp_path / "hooks.yaml"
        hooks_yaml.write_text(yaml.dump({
            "hooks": [{
                "name": "error_notifier",
                "event_type": "error",
                "module_path": str(hook_file),
                "function": "on_error",
                "config": {
                    "notify_severity": ["critical", "high"],
                    "channel": "slack"
                }
            }]
        }))

        loader = HooksLoader(hooks_yaml)
        runner = HookRunner(loader)

        # Erro crítico
        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.ERROR,
            payload={
                "severity": "critical",
                "error_type": "DatabaseConnectionError",
                "message": "Falha ao conectar ao banco",
                "stacktrace": "Traceback..."
            }
        )

        results = runner.execute(event)

        assert "error_notifier" in results
        assert results["error_notifier"]["success"] is True
        assert results["error_notifier"]["result"]["should_notify"] is True
        assert "notification" in results["error_notifier"]["result"]

    def test_global_logger_hook(self, tmp_path):
        """Executa hook global logger"""
        # Cria hook mock
        hook_file = tmp_path / "global_logger.py"
        hook_file.write_text("""
def on_any_event(event, context, config):
    exclude_subtypes = config.get('exclude_subtypes', [])
    if event.subtype in exclude_subtypes:
        return {'logged': False, 'skipped': True}
    return {'logged': True, 'skipped': False}
""")

        hooks_yaml = tmp_path / "hooks.yaml"
        hooks_yaml.write_text(yaml.dump({
            "hooks": [{
                "name": "global_logger",
                "event_type": "*",
                "module_path": str(hook_file),
                "function": "on_any_event",
                "config": {"exclude_subtypes": ["heartbeat"]}
            }]
        }))

        loader = HooksLoader(hooks_yaml)
        runner = HookRunner(loader)

        # Evento normal
        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={}
        )

        results = runner.execute(event)

        assert "global_logger" in results
        assert results["global_logger"]["success"] is True
        assert results["global_logger"]["result"]["logged"] is True

        # Evento heartbeat (deve ser excluído)
        heartbeat_event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="heartbeat",
            payload={}
        )

        results = runner.execute(heartbeat_event)

        assert "global_logger" in results
        assert results["global_logger"]["result"]["skipped"] is True

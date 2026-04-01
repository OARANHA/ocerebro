"""Testes para Hooks Loader e Runner do Cerebro"""

import pytest
import yaml
from pathlib import Path
from src.hooks.custom_loader import HooksLoader, HookRunner, HookConfig, create_sample_hooks_config
from src.core.event_schema import Event, EventType, EventOrigin


@pytest.fixture
def sample_hooks_yaml(tmp_path):
    """Cria arquivo hooks.yaml de exemplo"""
    hooks_file = tmp_path / "hooks.yaml"
    config = {
        "hooks": [
            {
                "name": "test_coverage",
                "event_type": "test_result",
                "module_path": "hooks/coverage_hook.py",
                "function": "on_test_result",
                "config": {"min_coverage": 80}
            },
            {
                "name": "llm_cost_tracker",
                "event_type": "tool_call",
                "event_subtype": "llm",
                "module_path": "hooks/cost_hook.py",
                "function": "on_llm_call"
            },
            {
                "name": "catch_all",
                "event_type": "*",
                "module_path": "hooks/global_hook.py",
                "function": "on_any_event"
            }
        ]
    }
    hooks_file.write_text(yaml.dump(config))
    return hooks_file


@pytest.fixture
def sample_hook_module(tmp_path):
    """Cria módulo de hook de exemplo"""
    hook_file = tmp_path / "test_hook.py"
    hook_code = '''
def execute(event, context, config):
    """Hook de teste"""
    return {"event_type": event.event_type.value, "processed": True}
'''
    hook_file.write_text(hook_code)
    return str(hook_file)


class TestHookConfig:
    """Testes para HookConfig dataclass"""

    def test_create_hook_config(self):
        """Cria configuração de hook"""
        config = HookConfig(
            name="test_hook",
            event_type="test_result",
            event_subtype=None,
            module_path="hooks/test.py",
            function="execute"
        )

        assert config.name == "test_hook"
        assert config.event_type == "test_result"
        assert config.module_path == "hooks/test.py"
        assert config.function == "execute"
        assert config.config is None

    def test_hook_config_with_config(self):
        """Hook com configuração"""
        config = HookConfig(
            name="coverage_hook",
            event_type="test_result",
            event_subtype=None,
            module_path="hooks/coverage.py",
            function="check_coverage",
            config={"min_coverage": 80, "fail_below": True}
        )

        assert config.config["min_coverage"] == 80
        assert config.config["fail_below"] is True


class TestHooksLoader:
    """Testes para HooksLoader"""

    def test_init_with_existing_config(self, sample_hooks_yaml):
        """Inicializa com configuração existente"""
        loader = HooksLoader(sample_hooks_yaml)

        assert len(loader.hooks) == 3
        assert loader.hooks[0].name == "test_coverage"
        assert loader.hooks[1].name == "llm_cost_tracker"
        assert loader.hooks[2].name == "catch_all"

    def test_init_with_missing_config(self, tmp_path):
        """Inicializa com configuração ausente"""
        missing_file = tmp_path / "nonexistent.yaml"
        loader = HooksLoader(missing_file)

        assert len(loader.hooks) == 0
        assert loader._loaded_modules == {}

    def test_load_module(self, sample_hook_module):
        """Carrega módulo dinamicamente"""
        loader = HooksLoader(Path("nonexistent.yaml"))
        module = loader._load_module(sample_hook_module)

        assert module is not None
        assert hasattr(module, "execute")

    def test_load_module_cached(self, sample_hook_module):
        """Carregamento em cache"""
        loader = HooksLoader(Path("nonexistent.yaml"))

        module1 = loader._load_module(sample_hook_module)
        module2 = loader._load_module(sample_hook_module)

        assert module1 is module2

    def test_load_module_not_found(self, tmp_path):
        """Módulo não encontrado"""
        loader = HooksLoader(Path("nonexistent.yaml"))
        result = loader._load_module(str(tmp_path / "nonexistent.py"))

        assert result is None

    def test_get_hooks_for_event_type(self, sample_hooks_yaml):
        """Filtra hooks por tipo de evento"""
        loader = HooksLoader(sample_hooks_yaml)

        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TEST_RESULT,
            payload={}
        )

        hooks = loader.get_hooks_for_event(event)

        assert len(hooks) == 2
        assert hooks[0].name == "test_coverage"
        assert hooks[1].name == "catch_all"

    def test_get_hooks_for_event_subtype(self, sample_hooks_yaml):
        """Filtra hooks por subtipo"""
        loader = HooksLoader(sample_hooks_yaml)

        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="llm",
            payload={}
        )

        hooks = loader.get_hooks_for_event(event)

        assert len(hooks) == 2
        assert hooks[0].name == "llm_cost_tracker"
        assert hooks[1].name == "catch_all"

    def test_get_hooks_for_event_no_match(self, sample_hooks_yaml):
        """Sem hooks para evento"""
        loader = HooksLoader(sample_hooks_yaml)

        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.ERROR,
            payload={}
        )

        hooks = loader.get_hooks_for_event(event)

        assert len(hooks) == 1
        assert hooks[0].name == "catch_all"


class TestHookRunner:
    """Testes para HookRunner"""

    def test_init(self, sample_hooks_yaml):
        """Inicializa HookRunner"""
        loader = HooksLoader(sample_hooks_yaml)
        runner = HookRunner(loader, {"global": "context"})

        assert runner.loader is loader
        assert runner.context["global"] == "context"

    def test_execute_success(self, sample_hook_module, tmp_path):
        """Executa hook com sucesso"""
        hooks_yaml = tmp_path / "hooks.yaml"
        hooks_yaml.write_text(yaml.dump({
            "hooks": [{
                "name": "test_hook",
                "event_type": "test_result",
                "module_path": sample_hook_module,
                "function": "execute"
            }]
        }))

        loader = HooksLoader(hooks_yaml)
        runner = HookRunner(loader)

        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TEST_RESULT,
            payload={}
        )

        results = runner.execute(event)

        assert "test_hook" in results
        assert results["test_hook"]["success"] is True
        assert results["test_hook"]["result"]["event_type"] == "test_result"
        assert results["test_hook"]["result"]["processed"] is True

    def test_execute_module_not_found(self, tmp_path):
        """Hook com módulo ausente"""
        hooks_yaml = tmp_path / "hooks.yaml"
        hooks_yaml.write_text(yaml.dump({
            "hooks": [{
                "name": "missing_hook",
                "event_type": "test_result",
                "module_path": "nonexistent.py",
                "function": "execute"
            }]
        }))

        loader = HooksLoader(hooks_yaml)
        runner = HookRunner(loader)

        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TEST_RESULT,
            payload={}
        )

        results = runner.execute(event)

        assert "missing_hook" in results
        assert results["missing_hook"]["success"] is False
        assert "Módulo não encontrado" in results["missing_hook"]["error"]

    def test_execute_function_not_found(self, sample_hook_module, tmp_path):
        """Hook com função ausente"""
        hooks_yaml = tmp_path / "hooks.yaml"
        hooks_yaml.write_text(yaml.dump({
            "hooks": [{
                "name": "wrong_func_hook",
                "event_type": "test_result",
                "module_path": sample_hook_module,
                "function": "nonexistent_function"
            }]
        }))

        loader = HooksLoader(hooks_yaml)
        runner = HookRunner(loader)

        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TEST_RESULT,
            payload={}
        )

        results = runner.execute(event)

        assert "wrong_func_hook" in results
        assert results["wrong_func_hook"]["success"] is False
        assert "não encontrada" in results["wrong_func_hook"]["error"]

    def test_register_callback(self, tmp_path):
        """Registra callback inline"""
        loader = HooksLoader(tmp_path / "empty.yaml")
        runner = HookRunner(loader)

        def callback(event):
            return {"callback_result": True}

        runner.register_callback("test_result", callback)

        assert "test_result:*" in runner._callbacks

    def test_execute_callbacks(self, tmp_path):
        """Executa callbacks registrados"""
        loader = HooksLoader(tmp_path / "empty.yaml")
        runner = HookRunner(loader)

        executed = []

        def callback(event):
            executed.append(event.event_type.value)
            return {"executed": True}

        runner.register_callback("test_result", callback)

        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TEST_RESULT,
            payload={}
        )

        results = runner.execute_callbacks(event)

        assert len(executed) == 1
        assert executed[0] == "test_result"
        assert "test_result:*" in results
        assert results["test_result:*"]["success"] is True

    def test_execute_callbacks_subtype(self, tmp_path):
        """Executa callbacks com subtipo"""
        loader = HooksLoader(tmp_path / "empty.yaml")
        runner = HookRunner(loader)

        def callback(event):
            return {"subtype_match": event.subtype}

        runner.register_callback("tool_call", callback, subtype="bash")

        event = Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={}
        )

        results = runner.execute_callbacks(event)

        assert "tool_call:bash" in results
        assert results["tool_call:bash"]["result"]["subtype_match"] == "bash"


class TestCreateSampleHooksConfig:
    """Testes para create_sample_hooks_config"""

    def test_create_sample_config(self, tmp_path):
        """Cria configuração de exemplo"""
        output_path = tmp_path / "sample_hooks.yaml"

        create_sample_hooks_config(output_path)

        assert output_path.exists()

        content = yaml.safe_load(output_path.read_text())
        assert "hooks" in content
        assert len(content["hooks"]) == 3

        hook_names = [h["name"] for h in content["hooks"]]
        assert "test_coverage_check" in hook_names
        assert "expensive_operation_log" in hook_names
        assert "error_notification" in hook_names

    def test_create_sample_config_creates_parent_dirs(self, tmp_path):
        """Cria diretórios pais se necessário"""
        output_path = tmp_path / "subdir" / "hooks.yaml"

        create_sample_hooks_config(output_path)

        assert output_path.exists()

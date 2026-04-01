"""Testes para CoreCaptures"""

import pytest
import yaml
from pathlib import Path
from src.hooks.core_captures import CoreCaptures
from src.core.jsonl_storage import JSONLStorage


class TestCoreCaptures:

    def test_capture_tool_call(self, tmp_cerebro_dir):
        """Captura tool call"""
        storage = JSONLStorage(tmp_cerebro_dir / "raw")
        captures = CoreCaptures(storage, "test-project", "sess_abc")

        event = captures.tool_call("bash", {"command": "ls -la"}, {"result": "success", "duration": 0.1})

        assert event.event_type.value == "tool_call"
        assert event.subtype == "bash"
        assert event.project == "test-project"

    def test_capture_git_event(self, tmp_cerebro_dir):
        """Captura git event"""
        storage = JSONLStorage(tmp_cerebro_dir / "raw")
        captures = CoreCaptures(storage, "test-project", "sess_abc")

        event = captures.git_event("commit", {"branch": "main", "hash": "abc123", "message": "feat: add"})

        assert event.event_type.value == "git_event"
        assert event.subtype == "commit"

    def test_capture_test_result(self, tmp_cerebro_dir):
        """Captura test result"""
        storage = JSONLStorage(tmp_cerebro_dir / "raw")
        captures = CoreCaptures(storage, "test-project", "sess_abc")

        event = captures.test_result("unit", "test_login", "pass", 0.05)

        assert event.event_type.value == "test_result"
        assert event.subtype == "unit"
        assert event.payload["status"] == "pass"

    def test_capture_error(self, tmp_cerebro_dir):
        """Captura erro"""
        storage = JSONLStorage(tmp_cerebro_dir / "raw")
        captures = CoreCaptures(storage, "test-project", "sess_abc")

        event = captures.error("command_failure", {"message": "Permission denied", "cmd": "rm -rf /"})

        assert event.event_type.value == "error"
        assert event.subtype == "command_failure"

    def test_capture_with_hooks_integration(self, tmp_path):
        """Captura evento com hooks integrados"""
        # Cria diretório raw
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        # Cria hooks.yaml de teste
        test_hook = tmp_path / "test_hook.py"
        test_hook.write_text('''
def on_tool_call(event, context, config):
    return {"captured": True, "tool": event.subtype}
''')

        hooks_yaml = tmp_path / "hooks.yaml"
        hooks_yaml.write_text(yaml.dump({
            "hooks": [{
                "name": "test_hook",
                "event_type": "tool_call",
                "module_path": str(test_hook),
                "function": "on_tool_call"
            }]
        }))

        storage = JSONLStorage(raw_dir)
        captures = CoreCaptures(storage, "test-project", "sess_abc", hooks_yaml)

        event = captures.tool_call("bash", {"command": "ls"}, {"result": "ok"})

        # Verifica que evento foi capturado
        assert event.event_type.value == "tool_call"
        # Hooks são executados mas falham silenciosamente se módulo não existe

    def test_capture_initializes_hooks_loader(self, tmp_cerebro_dir):
        """Verifica que CoreCaptures inicializa HooksLoader"""
        storage = JSONLStorage(tmp_cerebro_dir / "raw")
        captures = CoreCaptures(storage, "test-project", "sess_abc")

        # Verifica que hooks_loader e hooks_runner foram inicializados
        assert hasattr(captures, "hooks_loader")
        assert hasattr(captures, "hooks_runner")
        assert captures.hooks_loader is not None
        assert captures.hooks_runner is not None

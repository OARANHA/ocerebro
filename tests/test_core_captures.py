"""Testes para CoreCaptures"""

import pytest
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

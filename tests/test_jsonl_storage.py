"""Testes para JSONLStorage"""

import pytest
from pathlib import Path
from src.core.jsonl_storage import JSONLStorage
from src.core.event_schema import Event, EventType, EventOrigin


class TestJSONLStorage:

    def test_append_event(self, tmp_cerebro_dir):
        """Append de evento cria arquivo JSONL"""
        storage = JSONLStorage(tmp_cerebro_dir / "raw")
        event = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={"cmd": "ls"}
        )

        storage.append(event)

        jsonl_file = tmp_cerebro_dir / "raw" / "test-project" / f"events-{event.ts[:7]}.jsonl"
        assert jsonl_file.exists()
        content = jsonl_file.read_text()
        assert event.event_id in content

    def test_append_multiple_events(self, tmp_cerebro_dir):
        """Múltiplos eventos no mesmo arquivo"""
        storage = JSONLStorage(tmp_cerebro_dir / "raw")

        for i in range(3):
            event = Event(
                project="test-project",
                origin=EventOrigin.CLAUDE_CODE,
                event_type=EventType.TOOL_CALL,
                subtype="bash",
                payload={"i": i}
            )
            storage.append(event)

        jsonl_file = tmp_cerebro_dir / "raw" / "test-project" / f"events-{event.ts[:7]}.jsonl"
        lines = jsonl_file.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_read_events(self, tmp_cerebro_dir):
        """Lê eventos do arquivo"""
        storage = JSONLStorage(tmp_cerebro_dir / "raw")
        event1 = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={"cmd": "ls"}
        )
        storage.append(event1)

        events = storage.read("test-project")
        assert len(events) == 1
        assert events[0].event_id == event1.event_id

    def test_read_events_range(self, tmp_cerebro_dir):
        """Lê eventos em um range de IDs"""
        storage = JSONLStorage(tmp_cerebro_dir / "raw")

        event1 = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={"idx": 1}
        )
        event2 = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={"idx": 2}
        )
        event3 = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={"idx": 3}
        )

        storage.append(event1)
        storage.append(event2)
        storage.append(event3)

        events = storage.read_range("test-project", event1.event_id, event3.event_id)
        assert len(events) == 3
        assert events[0].event_id == event1.event_id
        assert events[-1].event_id == event3.event_id

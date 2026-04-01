"""Testes para Extractor"""

import pytest
from src.consolidation.extractor import Extractor, ExtractionResult
from src.core.jsonl_storage import JSONLStorage
from src.core.event_schema import Event, EventType, EventOrigin
from src.working.yaml_storage import YAMLStorage


class TestExtractor:

    def test_extract_session(self, tmp_cerebro_dir):
        """Extrai eventos de uma sessão"""
        raw_storage = JSONLStorage(tmp_cerebro_dir / "raw")
        working_storage = YAMLStorage(tmp_cerebro_dir / "working")
        extractor = Extractor(raw_storage, working_storage)

        # Cria eventos de teste
        event1 = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={"command": "ls"},
            session_id="sess_abc123"
        )
        event2 = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TEST_RESULT,
            subtype="unit",
            payload={"test_name": "test_login", "status": "pass"},
            session_id="sess_abc123"
        )

        raw_storage.append(event1)
        raw_storage.append(event2)

        result = extractor.extract_session("test-project", "sess_abc123")

        assert result.session_id == "sess_abc123"
        assert len(result.events) == 2
        assert result.summary["total_events"] == 2
        assert result.start_event_id == event1.event_id
        assert result.end_event_id == event2.event_id

    def test_extract_session_no_events(self, tmp_cerebro_dir):
        """Extrai sessão vazia"""
        raw_storage = JSONLStorage(tmp_cerebro_dir / "raw")
        working_storage = YAMLStorage(tmp_cerebro_dir / "working")
        extractor = Extractor(raw_storage, working_storage)

        result = extractor.extract_session("test-project", "sess_nonexistent")

        assert result.events == []
        assert result.summary["status"] == "no_events"

    def test_extract_range(self, tmp_cerebro_dir):
        """Extrai eventos em um range"""
        raw_storage = JSONLStorage(tmp_cerebro_dir / "raw")
        working_storage = YAMLStorage(tmp_cerebro_dir / "working")
        extractor = Extractor(raw_storage, working_storage)

        event1 = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={},
            session_id="sess_001"
        )
        event2 = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.GIT_EVENT,
            subtype="commit",
            payload={"hash": "abc123"},
            session_id="sess_001"
        )

        raw_storage.append(event1)
        raw_storage.append(event2)

        result = extractor.extract_range(
            "test-project",
            event1.event_id,
            event2.event_id
        )

        assert len(result.events) == 2
        assert result.summary["git_events"] == 1

    def test_create_draft(self, tmp_cerebro_dir):
        """Cria draft a partir de extração"""
        raw_storage = JSONLStorage(tmp_cerebro_dir / "raw")
        working_storage = YAMLStorage(tmp_cerebro_dir / "working")
        extractor = Extractor(raw_storage, working_storage)

        event = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="Edit",
            payload={"call": {"file_path": "src/auth.py"}},
            session_id="sess_abc"
        )
        raw_storage.append(event)

        result = extractor.extract_session("test-project", "sess_abc")
        draft = extractor.create_draft(result, "session")

        assert draft["type"] == "session"
        assert draft["project"] == "test-project"
        assert "events_range" in draft
        assert draft["status"] == "draft"
        assert "src/auth.py" in draft["summary"]["files_changed"]

    def test_write_draft(self, tmp_cerebro_dir):
        """Escreve draft em working"""
        raw_storage = JSONLStorage(tmp_cerebro_dir / "raw")
        working_storage = YAMLStorage(tmp_cerebro_dir / "working")
        extractor = Extractor(raw_storage, working_storage)

        draft = {
            "id": "sess_test",
            "type": "session",
            "project": "test-project",
            "session_id": "sess_abc",
            "status": "draft"
        }

        draft_name = extractor.write_draft("test-project", draft, "session")

        assert draft_name == "sess_test"

        # Verifica que foi escrito
        sessions = working_storage.list_sessions("test-project")
        assert len(sessions) == 1
        assert sessions[0]["id"] == "sess_test"

    def test_extract_and_write(self, tmp_cerebro_dir):
        """Extrai e escreve draft"""
        raw_storage = JSONLStorage(tmp_cerebro_dir / "raw")
        working_storage = YAMLStorage(tmp_cerebro_dir / "working")
        extractor = Extractor(raw_storage, working_storage)

        event = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={},
            session_id="sess_xyz"
        )
        raw_storage.append(event)

        draft_name = extractor.extract_and_write("test-project", "sess_xyz")

        assert draft_name.startswith("session_sess_xyz")

    def test_find_incomplete_sessions(self, tmp_cerebro_dir):
        """Encontra sessões sem checkpoint"""
        raw_storage = JSONLStorage(tmp_cerebro_dir / "raw")
        working_storage = YAMLStorage(tmp_cerebro_dir / "working")
        extractor = Extractor(raw_storage, working_storage)

        # Sessão sem checkpoint
        event1 = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={},
            session_id="sess_incomplete"
        )
        raw_storage.append(event1)

        # Sessão com checkpoint
        event2 = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.CHECKPOINT_CREATED,
            subtype="",
            payload={},
            session_id="sess_complete"
        )
        raw_storage.append(event2)

        incomplete = extractor.find_incomplete_sessions("test-project")

        assert "sess_incomplete" in incomplete
        assert "sess_complete" not in incomplete

    def test_summary_with_tests(self, tmp_cerebro_dir):
        """Resumo com testes passing/failing"""
        raw_storage = JSONLStorage(tmp_cerebro_dir / "raw")
        working_storage = YAMLStorage(tmp_cerebro_dir / "working")
        extractor = Extractor(raw_storage, working_storage)

        # Testes passing
        for i in range(3):
            event = Event(
                project="test-project",
                origin=EventOrigin.CLAUDE_CODE,
                event_type=EventType.TEST_RESULT,
                subtype="unit",
                payload={"test_name": f"test_{i}", "status": "pass"},
                session_id="sess_test"
            )
            raw_storage.append(event)

        # Teste failing
        fail_event = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TEST_RESULT,
            subtype="unit",
            payload={"test_name": "test_fail", "status": "fail"},
            session_id="sess_test"
        )
        raw_storage.append(fail_event)

        result = extractor.extract_session("test-project", "sess_test")

        assert result.summary["tests_passed"] == 3
        assert result.summary["tests_failed"] == 1

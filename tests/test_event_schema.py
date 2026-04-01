import pytest
from datetime import datetime
from src.core.event_schema import Event, EventType, EventOrigin

def test_event_creation():
    """Evento válido com todos os campos"""
    event = Event(
        project="test-project",
        origin=EventOrigin.CLAUDE_CODE,
        event_type=EventType.TOOL_CALL,
        subtype="bash",
        payload={"command": "ls", "result": "success"},
        tags=["setup"]
    )

    assert event.event_id.startswith("evt_")
    assert event.session_id.startswith("sess_")
    assert event.ts.endswith("Z")
    assert event.project == "test-project"

def test_event_missing_required():
    """Falha sem campos obrigatórios"""
    with pytest.raises(ValueError):
        Event(
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={}
        )

def test_event_invalid_type():
    """Falha com type inválido"""
    with pytest.raises(ValueError):
        Event(
            project="test",
            origin=EventOrigin.CLAUDE_CODE,
            event_type="invalid_type",
            subtype="bash",
            payload={}
        )

def test_checkpoint_event():
    """Evento especial checkpoint.created"""
    event = Event(
        project="test-project",
        origin=EventOrigin.USER,
        event_type=EventType.CHECKPOINT_CREATED,
        subtype="",
        payload={
            "range": {
                "from_event_id": "evt_001",
                "to_event_id": "evt_002"
            },
            "reason": "feature_done",
            "label": "feat-auth"
        }
    )

    assert event.event_type == EventType.CHECKPOINT_CREATED
    assert "range" in event.payload
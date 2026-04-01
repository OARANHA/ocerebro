import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    TOOL_CALL = "tool_call"
    GIT_EVENT = "git_event"
    TEST_RESULT = "test_result"
    ERROR = "error"
    CHECKPOINT_CREATED = "checkpoint.created"
    PROMOTION_PERFORMED = "promotion.performed"
    MEMORY_GC = "memory.gc"


class EventOrigin(str, Enum):
    CLAUDE_CODE = "claude-code"
    USER = "user"
    CI = "ci"
    HOOK = "hook"


class Event(BaseModel):
    """Evento bruto do Cerebro"""

    project: str = Field(..., min_length=1)
    origin: EventOrigin
    event_type: EventType
    subtype: str = Field(default="")
    payload: Dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    # Campos gerados automaticamente
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    session_id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:8]}")
    ts: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        return [tag.lower().replace(" ", "-") for tag in v]

    def to_json_line(self) -> str:
        """Serializa para JSON line"""
        import json
        return self.model_dump_json()

    @classmethod
    def from_json_line(cls, line: str) -> "Event":
        """Deserializa de JSON line"""
        import json
        data = json.loads(line)
        return cls(**data)
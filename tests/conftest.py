import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

@pytest.fixture
def tmp_cerebro_dir():
    """Cria diretório temporário com estrutura cerebro"""
    tmpdir = Path(tempfile.mkdtemp())
    (tmpdir / "raw" / "test-project").mkdir(parents=True)
    (tmpdir / "working" / "test-project").mkdir(parents=True)
    (tmpdir / "official" / "test-project").mkdir(parents=True)
    (tmpdir / "index").mkdir()
    (tmpdir / "config").mkdir()
    yield tmpdir
    shutil.rmtree(tmpdir)

@pytest.fixture
def sample_event():
    """Evento de exemplo para testes"""
    return {
        "event_id": "evt_abc123",
        "ts": datetime.utcnow().isoformat() + "Z",
        "project": "test-project",
        "session_id": "sess_xyz789",
        "origin": "claude-code",
        "type": "tool_call",
        "subtype": "bash",
        "payload": {"command": "ls -la", "result": "success"},
        "tags": ["setup"]
    }
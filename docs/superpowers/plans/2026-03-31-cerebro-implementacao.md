# Cerebro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar sistema de memória em camadas para agentes de código com captura de eventos, consolidação, índice híbrido e forgetting.

**Architecture:** 4 fases sequenciais: (1) Core + MEMORY.md, (2) Pipeline de consolidação, (3) Índice SQLite + embeddings, (4) Forgetting/scoring. Cada fase produz software funcional e testável independentemente.

**Tech Stack:** Python 3.10+, SQLite3, PyYAML, sentence-transformers, pytest

---

## Estrutura de Arquivos

```
cerebro/
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── event_schema.py       # Schema de eventos, validação, UUID generation
│   │   ├── jsonl_storage.py      # Camada bruta: append-only, rotação mensal
│   │   └── session_manager.py    # Session ID, project detection
│   │
│   ├── working/
│   │   ├── __init__.py
│   │   ├── yaml_storage.py       # Camada working: sessions, features, drafts
│   │   └── memory_view.py        # Geração de MEMORY.md
│   │
│   ├── official/
│   │   ├── __init__.py
│   │   ├── markdown_storage.py   # Camada official: decisions, errors, preferences
│   │   └── templates.py          # Templates de post-mortem, decisões
│   │
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── core_captures.py      # Tool calls, git events, test results, errors
│   │   ├── custom_loader.py      # Carrega hooks.yaml
│   │   └── runner.py             # Executa handlers de hooks
│   │
│   ├── index/
│   │   ├── __init__.py
│   │   ├── metadata_db.py        # SQLite schema + operações
│   │   ├── embeddings_db.py      # Embeddings storage
│   │   └── queries.py            # FTS, semantic search, metadata filters
│   │
│   ├── consolidation/
│   │   ├── __init__.py
│   │   ├── extractor.py          # Raw → Working: filtra eventos, gera drafts
│   │   ├── scorer.py             # RFM scoring + decay
│   │   ├── promoter.py           # Working → Official: promoção com LLM
│   │   └── checkpoints.py        # Triggers de checkpoint
│   │
│   ├── forgetting/
│   │   ├── __init__.py
│   │   ├── decay.py              # Decay diferencial por tipo
│   │   ├── guard_rails.py        # never_delete, always_archive
│   │   └── gc.py                 # Archive/merge + log memory.gc
│   │
│   └── cli/
│       ├── __init__.py
│       └── main.py               # CLI entry point, /checkpoint command
│
├── config/
│   └── cerebro.yaml              # Configuração global
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Fixtures: tmp dirs, sample events
│   ├── test_event_schema.py
│   ├── test_jsonl_storage.py
│   ├── test_yaml_storage.py
│   ├── test_markdown_storage.py
│   ├── test_memory_view.py
│   ├── test_core_captures.py
│   ├── test_metadata_db.py
│   ├── test_embeddings_db.py
│   ├── test_extractor.py
│   ├── test_scorer.py
│   ├── test_promoter.py
│   ├── test_decay.py
│   └── test_guard_rails.py
│
├── raw/                          # Git-ignored
├── working/                      # Git-tracked
├── official/                     # Git-tracked
├── index/                        # Git-ignored (reconstruível)
└── hooks/
    └── hooks.yaml                # Hooks customizados
```

---

## FASE 1: Core + MEMORY.md

**Objetivo:** Capturar eventos core (tool calls, git, tests, errors) em JSONL e gerar MEMORY.md a partir de working/official.

**Componentes:**
- `src/core/event_schema.py` - Schema, validação Pydantic, UUID
- `src/core/jsonl_storage.py` - Append-only, rotação mensal
- `src/core/session_manager.py` - Session ID, project detection
- `src/working/yaml_storage.py` - Leitura/escrita YAML
- `src/official/markdown_storage.py` - Leitura/escrita Markdown + frontmatter
- `src/working/memory_view.py` - Gera MEMORY.md
- `src/hooks/core_captures.py` - Captura tool calls, git, tests, errors

**Dependências:** Nenhuma (fase inicial)

**Entregáveis:**
- Eventos JSONL em `raw/{project}/events-YYYY-MM.jsonl`
- MEMORY.md gerado em `.claude/` do projeto
- Hooks core funcionando

**Riscos:**
- Detecção de projeto pode falhar em monorepos → usar cerebro-project.yaml
- Performance de append em JSONL → buffer + flush periódico

**Critérios de Aceite:**
- [ ] Tool call registrada em <10ms
- [ ] MEMORY.md reflete mudanças em working/official em <5s
- [ ] Rotação mensal de JSONL funciona
- [ ] Git hooks capturam commit/branch

---

## FASE 2: Pipeline de Consolidação

**Objetivo:** Implementar extração raw→working, consolidação com scoring, promoção para official.

**Componentes:**
- `src/consolidation/checkpoints.py` - Triggers: feature_done, session_end, /checkpoint
- `src/consolidation/extractor.py` - Filtra eventos, gera drafts YAML
- `src/consolidation/scorer.py` - Calcula scores RFM
- `src/consolidation/promoter.py` - Promoção com LLM para casos ambíguos
- `src/cli/main.py` - Comando /checkpoint manual

**Dependências:** Fase 1 completa

**Entregáveis:**
- Checkpoint automático em testes passando
- Drafts em working/ gerados a partir de raw
- Promoção para official com supervisão humana opcional

**Riscos:**
- LLM pode alucinar na consolidação → sempre incluir events_range no draft
- Checkpoint duplicado → usar evento checkpoint.created para marcar ranges

**Critérios de Aceite:**
- [ ] Checkpoint trigger em fim de teste passando
- [ ] Draft YAML inclui events_range
- [ ] Promoção cria arquivo em official/{type}/{project}/
- [ ] Evento promotion.performed registrado no raw

---

## FASE 3: Índice Híbrido

**Objetivo:** SQLite + FTS + embeddings para consultas rápidas e semânticas.

**Componentes:**
- `src/index/metadata_db.py` - Schema, CRUD, FTS
- `src/index/embeddings_db.py` - Storage de vetores
- `src/index/queries.py` - Queries por metadata, FTS, semantic
- `src/core/session_manager.py` - Atualiza last_accessed, access_count

**Dependências:** Fase 1 (working/official já existem)

**Entregáveis:**
- metadata.db com FTS
- embeddings.db com vetores
- Queries funcionando (metadata, textual, semântica)

**Riscos:**
- Embeddings podem divergir se modelo mudar → incluir model no schema
- SQLite lock em concorrência → WAL mode

**Critérios de Aceite:**
- [ ] Query metadata <50ms
- [ ] Query FTS <100ms
- [ ] Query semântica <200ms
- [ ] content_hash evita recomputar embedding

---

## FASE 4: Forgetting/Scoring/Guard Rails

**Objetivo:** Decay diferencial, scoring RFM, guard rails, log de poda.

**Componentes:**
- `src/forgetting/decay.py` - Decay por tipo (decisões lento, sessões rápido)
- `src/forgetting/guard_rails.py` - never_delete, always_archive
- `src/forgetting/gc.py` - Archive/merge, evento memory.gc
- `src/consolidation/scorer.py` - Atualiza com pesos de cerebro.yaml

**Dependências:** Fase 3 (índice com scores)

**Entregáveis:**
- Scoring RFM rodando
- Decay aplicado periodicamente
- Guard rails evitando deletar críticos
- memory.gc no raw

**Riscos:**
- Decay agressivo remove importante → guard rails + LLM para ambíguos
- Performance: scoring em todos itens → batch + incremental

**Critérios de Aceite:**
- [ ] Score calculado por RFM
- [ ] Decay diferencial por tipo
- [ ] never_delete respeitado
- [ ] memory.gc registrado

---

# Tarefas de Implementação

## FASE 1: Core + MEMORY.md

### Task 1: Setup do Projeto

**Files:**
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pyproject.toml`
- Create: `.gitignore`

- [ ] **Step 1: Criar src/__init__.py**

```python
"""Cerebro - Sistema de Memória para Agentes de Código"""
__version__ = "0.1.0"
```

- [ ] **Step 2: Criar tests/__init__.py**

```python
"""Testes do Cerebro"""
```

- [ ] **Step 3: Criar tests/conftest.py**

```python
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
```

- [ ] **Step 4: Criar pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "cerebro"
version = "0.1.0"
description = "Sistema de Memória para Agentes de Código"
requires-python = ">=3.10"
dependencies = [
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "sentence-transformers>=2.2.0",
    "numpy>=1.24.0",
]

[project.optional-dependencies]
test = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]

[project.scripts]
cerebro = "src.cli.main:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
```

- [ ] **Step 5: Criar .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
ENV/

# Cerebro
index/*.db
raw/**/*.jsonl
*.log

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 6: Instalar dependências**

Run: `pip install -e ".[test]"`

Expected: Dependencies installed successfully

- [ ] **Step 7: Commit**

```bash
git add src/__init__.py tests/__init__.py tests/conftest.py pyproject.toml .gitignore
git commit -m "feat: setup inicial do projeto cerebro"
```

---

### Task 2: Schema de Eventos

**Files:**
- Create: `src/core/__init__.py`
- Create: `src/core/event_schema.py`
- Test: `tests/test_event_schema.py`

- [ ] **Step 1: Criar src/core/__init__.py**

```python
"""Core do Cerebro: schema, storage bruto, session manager"""
from .event_schema import Event, EventType, EventOrigin
from .jsonl_storage import JSONLStorage
from .session_manager import SessionManager

__all__ = ["Event", "EventType", "EventOrigin", "JSONLStorage", "SessionManager"]
```

- [ ] **Step 2: Escrever teste para validação de evento**

```python
# tests/test_event_schema.py
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
```

- [ ] **Step 3: Implementar event_schema.py**

```python
# src/core/event_schema.py
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
```

- [ ] **Step 4: Rodar testes**

Run: `pytest tests/test_event_schema.py -v`

Expected: 4 testes passando

- [ ] **Step 5: Commit**

```bash
git add src/core/__init__.py src/core/event_schema.py tests/test_event_schema.py
git commit -m "feat: schema de eventos com validação Pydantic"
```

---

### Task 3: Armazenamento JSONL

**Files:**
- Create: `src/core/jsonl_storage.py`
- Test: `tests/test_jsonl_storage.py`

- [ ] **Step 1: Escrever teste para append de evento**

```python
# tests/test_jsonl_storage.py
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
```

- [ ] **Step 2: Implementar jsonl_storage.py**

```python
# src/core/jsonl_storage.py
import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from .event_schema import Event


class JSONLStorage:
    """Armazenamento append-only para eventos brutos"""

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def _get_jsonl_path(self, project: str, ts: Optional[str] = None) -> Path:
        """Retorna caminho do arquivo JSONL para um projeto"""
        if ts:
            month = ts[:7]  # YYYY-MM
        else:
            month = datetime.utcnow().strftime("%Y-%m")

        dir_path = self.base_path / project
        dir_path.mkdir(parents=True, exist_ok=True)

        return dir_path / f"events-{month}.jsonl"

    def append(self, event: Event) -> None:
        """Append de evento no arquivo JSONL"""
        jsonl_path = self._get_jsonl_path(event.project, event.ts)

        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(event.to_json_line() + "\n")

    def read(self, project: str, month: Optional[str] = None) -> List[Event]:
        """Lê todos os eventos de um projeto"""
        if month is None:
            month = datetime.utcnow().strftime("%Y-%m")

        jsonl_path = self._get_jsonl_path(project, month)

        if not jsonl_path.exists():
            return []

        events = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(Event.from_json_line(line))

        return events

    def read_range(self, project: str, from_event_id: str, to_event_id: str) -> List[Event]:
        """Lê eventos em um range de IDs"""
        all_events = self.read(project)

        # Ordena por timestamp
        all_events.sort(key=lambda e: e.ts)

        # Encontra indices
        start_idx = None
        end_idx = None

        for i, event in enumerate(all_events):
            if event.event_id == from_event_id and start_idx is None:
                start_idx = i
            if event.event_id == to_event_id:
                end_idx = i + 1

        if start_idx is None or end_idx is None:
            return []

        return all_events[start_idx:end_idx]

    def get_latest_event_id(self, project: str) -> Optional[str]:
        """Retorna ID do último evento"""
        events = self.read(project)
        if not events:
            return None

        events.sort(key=lambda e: e.ts)
        return events[-1].event_id
```

- [ ] **Step 3: Rodar testes**

Run: `pytest tests/test_jsonl_storage.py -v`

Expected: 4 testes passando

- [ ] **Step 4: Commit**

```bash
git add src/core/jsonl_storage.py tests/test_jsonl_storage.py
git commit -m "feat: armazenamento JSONL append-only com rotação mensal"
```

---

### Task 4: Session Manager

**Files:**
- Create: `src/core/session_manager.py`
- Test: `tests/test_session_manager.py`

- [ ] **Step 1: Escrever teste para session manager**

```python
# tests/test_session_manager.py
import pytest
from pathlib import Path
from src.core.session_manager import SessionManager


class TestSessionManager:

    def test_get_session_id_new(self, tmp_path):
        """Cria novo session ID se não existe"""
        manager = SessionManager(tmp_path)
        session_id = manager.get_session_id()

        assert session_id.startswith("sess_")
        assert (tmp_path / ".cerebro_session").exists()

    def test_get_session_id_existing(self, tmp_path):
        """Reusa session ID existente"""
        manager = SessionManager(tmp_path)
        session_id1 = manager.get_session_id()
        session_id2 = manager.get_session_id()

        assert session_id1 == session_id2

    def test_detect_project_from_cerebro_yaml(self, tmp_path):
        """Detecta projeto de cerebro-project.yaml"""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        (project_dir / ".claude" / "cerebro-project.yaml").write_text(
            "project_id: my-project\nproject_name: My Project\n"
        )

        manager = SessionManager(tmp_path)
        project = manager.detect_project(project_dir)

        assert project == "my-project"

    def test_detect_project_fallback_to_dirname(self, tmp_path):
        """Fallback para nome do diretório"""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        manager = SessionManager(tmp_path)
        project = manager.detect_project(project_dir)

        assert project == "my-project"
```

- [ ] **Step 2: Implementar session_manager.py**

```python
# src/core/session_manager.py
import uuid
import yaml
from pathlib import Path
from typing import Optional


class SessionManager:
    """Gerencia session ID e detecção de projeto"""

    def __init__(self, cerebro_path: Path):
        self.cerebro_path = cerebro_path
        self._session_file = cerebro_path / ".cerebro_session"

    def get_session_id(self) -> str:
        """Obtém ou cria session ID"""
        if self._session_file.exists():
            return self._session_file.read_text().strip()

        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        self._session_file.write_text(session_id)
        return session_id

    def detect_project(self, project_dir: Path) -> str:
        """Detecta project ID a partir do diretório"""
        cerebro_yaml = project_dir / ".claude" / "cerebro-project.yaml"

        if cerebro_yaml.exists():
            config = yaml.safe_load(cerebro_yaml.read_text())
            return config.get("project_id", project_dir.name)

        return project_dir.name

    def clear_session(self) -> None:
        """Limpa session ID (fim de sessão)"""
        if self._session_file.exists():
            self._session_file.unlink()
```

- [ ] **Step 3: Rodar testes**

Run: `pytest tests/test_session_manager.py -v`

Expected: 4 testes passando

- [ ] **Step 4: Commit**

```bash
git add src/core/session_manager.py tests/test_session_manager.py
git commit -m "feat: session manager com detecção de projeto"
```

---

### Task 5: Armazenamento YAML (Working)

**Files:**
- Create: `src/working/__init__.py`
- Create: `src/working/yaml_storage.py`
- Test: `tests/test_yaml_storage.py`

- [ ] **Step 1: Criar src/working/__init__.py**

```python
"""Camada Working do Cerebro: YAML estruturado, editável"""
from .yaml_storage import YAMLStorage
from .memory_view import MemoryView

__all__ = ["YAMLStorage", "MemoryView"]
```

- [ ] **Step 2: Escrever teste para YAML storage**

```python
# tests/test_yaml_storage.py
import pytest
from pathlib import Path
from src.working.yaml_storage import YAMLStorage


class TestYAMLStorage:

    def test_write_session(self, tmp_cerebro_dir):
        """Escreve sessão em YAML"""
        storage = YAMLStorage(tmp_cerebro_dir / "working")

        storage.write_session("test-project", "sess_abc123", {
            "status": "in_progress",
            "todo": ["finalizar testes"],
            "last_changes": ["auth-module refactor"]
        })

        yaml_file = tmp_cerebro_dir / "working" / "test-project" / "sessions" / "sess_abc123.yaml"
        assert yaml_file.exists()
        content = yaml_file.read_text()
        assert "in_progress" in content

    def test_read_session(self, tmp_cerebro_dir):
        """Lê sessão de YAML"""
        storage = YAMLStorage(tmp_cerebro_dir / "working")

        storage.write_session("test-project", "sess_abc123", {
            "status": "in_progress",
            "todo": ["teste"]
        })

        session = storage.read_session("test-project", "sess_abc123")
        assert session["status"] == "in_progress"

    def test_write_feature(self, tmp_cerebro_dir):
        """Escreve feature em YAML"""
        storage = YAMLStorage(tmp_cerebro_dir / "working")

        storage.write_feature("test-project", "feat-auth", {
            "status": "in_progress",
            "events_range": {"from": "evt_001", "to": "evt_010"}
        })

        yaml_file = tmp_cerebro_dir / "working" / "test-project" / "features" / "feat-auth.yaml"
        assert yaml_file.exists()

    def test_list_sessions(self, tmp_cerebro_dir):
        """Lista sessões de um projeto"""
        storage = YAMLStorage(tmp_cerebro_dir / "working")

        storage.write_session("test-project", "sess_001", {"status": "active"})
        storage.write_session("test-project", "sess_002", {"status": "active"})

        sessions = storage.list_sessions("test-project")
        assert len(sessions) == 2
```

- [ ] **Step 3: Implementar yaml_storage.py**

```python
# src/working/yaml_storage.py
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


class YAMLStorage:
    """Armazenamento YAML para camada Working"""

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def _ensure_project_dir(self, project: str, subdir: str) -> Path:
        """Garante que diretório do projeto existe"""
        dir_path = self.base_path / project / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def write_session(self, project: str, session_id: str, data: Dict[str, Any]) -> None:
        """Escreve sessão em YAML"""
        dir_path = self._ensure_project_dir(project, "sessions")
        yaml_path = dir_path / f"{session_id}.yaml"

        content = {
            "id": session_id,
            "type": "session",
            **data
        }

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(content, f, allow_unicode=True, default_flow_style=False)

    def read_session(self, project: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Lê sessão de YAML"""
        yaml_path = self.base_path / project / "sessions" / f"{session_id}.yaml"

        if not yaml_path.exists():
            return None

        return yaml.safe_load(yaml_path.read_text())

    def list_sessions(self, project: str) -> List[Dict[str, Any]]:
        """Lista todas as sessões de um projeto"""
        dir_path = self.base_path / project / "sessions"

        if not dir_path.exists():
            return []

        sessions = []
        for yaml_file in dir_path.glob("*.yaml"):
            sessions.append(yaml.safe_load(yaml_file.read_text()))

        return sessions

    def write_feature(self, project: str, feature_name: str, data: Dict[str, Any]) -> None:
        """Escreve feature em YAML"""
        dir_path = self._ensure_project_dir(project, "features")
        yaml_path = dir_path / f"{feature_name}.yaml"

        content = {
            "id": feature_name,
            "type": "feature",
            **data
        }

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(content, f, allow_unicode=True, default_flow_style=False)

    def read_feature(self, project: str, feature_name: str) -> Optional[Dict[str, Any]]:
        """Lê feature de YAML"""
        yaml_path = self.base_path / project / "features" / f"{feature_name}.yaml"

        if not yaml_path.exists():
            return None

        return yaml.safe_load(yaml_path.read_text())

    def list_features(self, project: str) -> List[Dict[str, Any]]:
        """Lista todas as features de um projeto"""
        dir_path = self.base_path / project / "features"

        if not dir_path.exists():
            return []

        features = []
        for yaml_file in dir_path.glob("*.yaml"):
            features.append(yaml.safe_load(yaml_file.read_text()))

        return features
```

- [ ] **Step 4: Rodar testes**

Run: `pytest tests/test_yaml_storage.py -v`

Expected: 5 testes passando

- [ ] **Step 5: Commit**

```bash
git add src/working/__init__.py src/working/yaml_storage.py tests/test_yaml_storage.py
git commit -m "feat: armazenamento YAML para working layer"
```

---

### Task 6: Armazenamento Markdown (Official)

**Files:**
- Create: `src/official/__init__.py`
- Create: `src/official/markdown_storage.py`
- Create: `src/official/templates.py`
- Test: `tests/test_markdown_storage.py`

- [ ] **Step 1: Criar src/official/__init__.py**

```python
"""Camada Official do Cerebro: Markdown durável, versionável"""
from .markdown_storage import MarkdownStorage
from .templates import ErrorTemplate, DecisionTemplate

__all__ = ["MarkdownStorage", "ErrorTemplate", "DecisionTemplate"]
```

- [ ] **Step 2: Escrever teste para Markdown storage**

```python
# tests/test_markdown_storage.py
import pytest
from pathlib import Path
from src.official.markdown_storage import MarkdownStorage


class TestMarkdownStorage:

    def test_write_decision(self, tmp_cerebro_dir):
        """Escreve decisão em Markdown com frontmatter"""
        storage = MarkdownStorage(tmp_cerebro_dir / "official")

        storage.write_decision("test-project", "db-choice", {
            "title": "PostgreSQL vs MongoDB",
            "status": "approved",
            "date": "2026-03-31"
        }, """
        ## Contexto

        Precisávamos escolher um banco de dados.

        ## Decisão

        PostgreSQL foi escolhido.
        """)

        md_file = tmp_cerebro_dir / "official" / "test-project" / "decisions" / "db-choice.md"
        assert md_file.exists()
        content = md_file.read_text()
        assert "---" in content
        assert "PostgreSQL" in content

    def test_read_decision(self, tmp_cerebro_dir):
        """Lê decisão de Markdown"""
        storage = MarkdownStorage(tmp_cerebro_dir / "official")

        storage.write_decision("test-project", "db-choice", {
            "title": "DB Choice",
            "status": "approved"
        }, "## Decisão\n\nPostgreSQL.")

        frontmatter, content = storage.read_decision("test-project", "db-choice")
        assert frontmatter["title"] == "DB Choice"
        assert "PostgreSQL" in content

    def test_write_error(self, tmp_cerebro_dir):
        """Escreve erro em Markdown"""
        storage = MarkdownStorage(tmp_cerebro_dir / "official")

        storage.write_error("test-project", "deadlock-pool", {
            "severity": "high",
            "status": "resolved"
        }, """
        # Erro Original

        Deadlock no connection pool.
        """)

        md_file = tmp_cerebro_dir / "official" / "test-project" / "errors" / "deadlock-pool.md"
        assert md_file.exists()
```

- [ ] **Step 3: Implementar markdown_storage.py**

```python
# src/official/markdown_storage.py
import yaml
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class MarkdownStorage:
    """Armazenamento Markdown para camada Official"""

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def _ensure_project_dir(self, project: str, subdir: str) -> Path:
        """Garante que diretório do projeto existe"""
        dir_path = self.base_path / project / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _parse_frontmatter(self, content: str) -> Tuple[Dict[str, Any], str]:
        """Extrai frontmatter YAML do conteúdo Markdown"""
        match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)

        if not match:
            return {}, content

        frontmatter = yaml.safe_load(match.group(1))
        body = match.group(2)

        return frontmatter, body

    def _format_frontmatter(self, frontmatter: Dict[str, Any]) -> str:
        """Formata frontmatter YAML"""
        return f"---\n{yaml.dump(frontmatter, allow_unicode=True)}---\n"

    def write_decision(self, project: str, name: str, frontmatter: Dict[str, Any], content: str) -> None:
        """Escreve decisão em Markdown"""
        dir_path = self._ensure_project_dir(project, "decisions")
        md_path = dir_path / f"{name}.md"

        frontmatter["type"] = "decision"
        full_content = self._format_frontmatter(frontmatter) + content

        md_path.write_text(full_content, encoding="utf-8")

    def read_decision(self, project: str, name: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Lê decisão de Markdown"""
        md_path = self.base_path / project / "decisions" / f"{name}.md"

        if not md_path.exists():
            return None, None

        content = md_path.read_text(encoding="utf-8")
        return self._parse_frontmatter(content)

    def write_error(self, project: str, name: str, frontmatter: Dict[str, Any], content: str) -> None:
        """Escreve erro em Markdown"""
        dir_path = self._ensure_project_dir(project, "errors")
        md_path = dir_path / f"{name}.md"

        frontmatter["type"] = "error"
        full_content = self._format_frontmatter(frontmatter) + content

        md_path.write_text(full_content, encoding="utf-8")

    def read_error(self, project: str, name: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Lê erro de Markdown"""
        md_path = self.base_path / project / "errors" / f"{name}.md"

        if not md_path.exists():
            return None, None

        content = md_path.read_text(encoding="utf-8")
        return self._parse_frontmatter(content)

    def list_official(self, project: str, subdir: str) -> List[Dict[str, Any]]:
        """Lista itens de um subdiretório official"""
        dir_path = self.base_path / project / subdir

        if not dir_path.exists():
            return []

        items = []
        for md_file in dir_path.glob("*.md"):
            frontmatter, _ = self._parse_frontmatter(md_file.read_text(encoding="utf-8"))
            if frontmatter:
                frontmatter["_file"] = md_file.name
                items.append(frontmatter)

        return items
```

- [ ] **Step 4: Implementar templates.py**

```python
# src/official/templates.py
from typing import Any, Dict


class ErrorTemplate:
    """Template para post-mortem de erro"""

    @staticmethod
    def frontmatter(
        error_id: str,
        severity: str,
        status: str,
        category: str,
        area: str,
        project: str,
        tags: list = None,
        related_to: list = None,
        similar_to: list = None
    ) -> Dict[str, Any]:
        return {
            "id": error_id,
            "type": "error",
            "status": status,
            "severity": severity,
            "impact": severity,
            "category": category,
            "area": area,
            "project": project,
            "tags": tags or [],
            "related_to": related_to or [],
            "similar_to": similar_to or []
        }

    @staticmethod
    def body(
        error_original: str,
        causa_raiz: str,
        solucao_aplicada: str,
        prevencao_futura: str = None
    ) -> str:
        sections = [
            "# Erro Original",
            "",
            error_original,
            "",
            "# Causa Raiz",
            "",
            causa_raiz,
            "",
            "# Solução Aplicada",
            "",
            solucao_aplicada
        ]

        if prevencao_futura:
            sections.extend([
                "",
                "# Prevenção Futura",
                "",
                prevencao_futura
            ])

        return "\n".join(sections)


class DecisionTemplate:
    """Template para decisão arquitetural"""

    @staticmethod
    def frontmatter(
        title: str,
        status: str,
        date: str,
        tags: list = None
    ) -> Dict[str, Any]:
        return {
            "title": title,
            "type": "decision",
            "status": status,
            "date": date,
            "tags": tags or []
        }

    @staticmethod
    def body(
        contexto: str,
        decisao: str,
        alternativas: str = None,
        consequencias: str = None
    ) -> str:
        sections = [
            "# Contexto",
            "",
            contexto,
            "",
            "# Decisão",
            "",
            decisao
        ]

        if alternativas:
            sections.extend([
                "",
                "# Alternativas Consideradas",
                "",
                alternativas
            ])

        if consequencias:
            sections.extend([
                "",
                "# Consequências",
                "",
                consequencias
            ])

        return "\n".join(sections)
```

- [ ] **Step 5: Rodar testes**

Run: `pytest tests/test_markdown_storage.py -v`

Expected: 3 testes passando

- [ ] **Step 6: Commit**

```bash
git add src/official/__init__.py src/official/markdown_storage.py src/official/templates.py tests/test_markdown_storage.py
git commit -m "feat: armazenamento Markdown para official layer com templates"
```

---

### Task 7: Geração de MEMORY.md

**Files:**
- Create: `src/working/memory_view.py`
- Test: `tests/test_memory_view.py`

- [ ] **Step 1: Escrever teste para MEMORY.md**

```python
# tests/test_memory_view.py
import pytest
from pathlib import Path
from src.working.memory_view import MemoryView
from src.working.yaml_storage import YAMLStorage
from src.official.markdown_storage import MarkdownStorage


class TestMemoryView:

    def test_generate_memory_md(self, tmp_cerebro_dir):
        """Gera MEMORY.md a partir de official + working"""
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        working = YAMLStorage(tmp_cerebro_dir / "working")
        view = MemoryView(tmp_cerebro_dir, official, working)

        # Cria dados de teste
        official.write_decision("test-project", "db-choice", {
            "title": "PostgreSQL vs MongoDB",
            "status": "approved"
        }, "## Decisão\n\nPostgreSQL.")

        working.write_session("test-project", "sess_abc", {
            "status": "in_progress",
            "todo": ["finalizar testes"]
        })

        content = view.generate("test-project")

        assert "# Cerebro - Memória Ativa" in content
        assert "PostgreSQL" in content
        assert "finalizar testes" in content

    def test_generate_with_global_memories(self, tmp_cerebro_dir):
        """Inclui memórias globais"""
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        working = YAMLStorage(tmp_cerebro_dir / "working")
        view = MemoryView(tmp_cerebro_dir, official, working)

        official.write_decision("global", "code-style", {
            "title": "Convenções de código",
            "status": "approved"
        }, "## Estilo\n\nSnake case.")

        content = view.generate("test-project")

        assert "## Official Global" in content
        assert "Convenções de código" in content
```

- [ ] **Step 2: Implementar memory_view.py**

```python
# src/working/memory_view.py
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .yaml_storage import YAMLStorage
    from .official.markdown_storage import MarkdownStorage


class MemoryView:
    """Gera MEMORY.md como view de official + working"""

    def __init__(self, cerebro_path: Path, official: "MarkdownStorage", working: "YAMLStorage"):
        self.cerebro_path = cerebro_path
        self.official = official
        self.working = working

    def generate(self, project: str) -> str:
        """Gera conteúdo do MEMORY.md"""
        sections = ["# Cerebro - Memória Ativa", ""]

        # Official Global
        sections.append("## Official Global")
        sections.append("")
        global_items = self._list_global()
        if global_items:
            for item in global_items:
                sections.append(f"- [{item['title']}](global/{item['_type']}/{item['_file']})")
        else:
            sections.append("_Nenhuma memória global_")
        sections.append("")

        # Official do Projeto
        sections.append(f"## Official {project}")
        sections.append("")
        project_items = self._list_project(project)
        if project_items:
            for item in project_items:
                sections.append(f"- [{item.get('title', item['_file'])}]({project}/{item['_type']}/{item['_file']})")
        else:
            sections.append("_Nenhuma memória oficial_")
        sections.append("")

        # Working atual
        sections.append("## Working atual")
        sections.append("")
        working_items = self._list_working(project)
        if working_items:
            for item in working_items:
                todo = item.get("todo", [])
                sections.append(f"- {item.get('id', 'unknown')}: {item.get('status', 'unknown')}")
                if todo:
                    sections.append(f"  - TODO: {', '.join(todo[:3])}")
        else:
            sections.append("_Nenhuma sessão em progresso_")
        sections.append("")

        sections.append("---")
        sections.append("Outras memórias disponíveis via Cerebro (decisions, errors, preferences, state).")

        return "\n".join(sections)

    def _list_global(self) -> list:
        """Lista memórias globais"""
        items = []
        for subdir in ["decisions", "preferences", "policies"]:
            for item in self.official.list_official("global", subdir):
                item["_type"] = subdir
                items.append(item)
        return items

    def _list_project(self, project: str) -> list:
        """Lista memórias do projeto"""
        items = []
        for subdir in ["decisions", "errors", "preferences", "state"]:
            for item in self.official.list_official(project, subdir):
                item["_type"] = subdir
                items.append(item)
        return items

    def _list_working(self, project: str) -> list:
        """Lista working do projeto"""
        items = []
        for session in self.working.list_sessions(project):
            items.append(session)
        for feature in self.working.list_features(project):
            items.append(feature)
        return items

    def write_to_project(self, project: str, project_dir: Path) -> None:
        """Escreve MEMORY.md no diretório do projeto"""
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)

        content = self.generate(project)
        (claude_dir / "MEMORY.md").write_text(content, encoding="utf-8")
```

- [ ] **Step 3: Rodar testes**

Run: `pytest tests/test_memory_view.py -v`

Expected: 2 testes passando

- [ ] **Step 4: Commit**

```bash
git add src/working/memory_view.py tests/test_memory_view.py
git commit -m "feat: geração de MEMORY.md como view de official + working"
```

---

### Task 8: Core Captures (Hooks)

**Files:**
- Create: `src/hooks/__init__.py`
- Create: `src/hooks/core_captures.py`
- Test: `tests/test_core_captures.py`

- [ ] **Step 1: Criar src/hooks/__init__.py**

```python
"""Hooks do Cerebro: captura de eventos"""
from .core_captures import CoreCaptures
from .custom_loader import HooksLoader
from .runner import HookRunner

__all__ = ["CoreCaptures", "HooksLoader", "HookRunner"]
```

- [ ] **Step 2: Escrever teste para core captures**

```python
# tests/test_core_captures.py
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
```

- [ ] **Step 3: Implementar core_captures.py**

```python
# src/hooks/core_captures.py
from typing import Any, Dict
from src.core.jsonl_storage import JSONLStorage
from src.core.event_schema import Event, EventType, EventOrigin


class CoreCaptures:
    """Captura de eventos core do Cerebro"""

    def __init__(self, storage: JSONLStorage, project: str, session_id: str):
        self.storage = storage
        self.project = project
        self.session_id = session_id

    def _create_event(
        self,
        event_type: EventType,
        subtype: str,
        payload: Dict[str, Any],
        tags: list = None
    ) -> Event:
        """Cria e persiste evento"""
        event = Event(
            project=self.project,
            origin=EventOrigin.CLAUDE_CODE,
            event_type=event_type,
            subtype=subtype,
            payload=payload,
            tags=tags or [],
            session_id=self.session_id
        )
        self.storage.append(event)
        return event

    def tool_call(self, tool: str, call_data: Dict[str, Any], result: Dict[str, Any]) -> Event:
        """Captura tool call"""
        return self._create_event(
            EventType.TOOL_CALL,
            tool,
            {
                "call": call_data,
                "result": result
            }
        )

    def git_event(self, action: str, data: Dict[str, Any]) -> Event:
        """Captura git event"""
        return self._create_event(
            EventType.GIT_EVENT,
            action,
            data
        )

    def test_result(self, test_type: str, test_name: str, status: str, duration: float, error: str = None) -> Event:
        """Captura test result"""
        payload = {
            "test_name": test_name,
            "status": status,
            "duration": duration
        }
        if error:
            payload["error"] = error

        return self._create_event(
            EventType.TEST_RESULT,
            test_type,
            payload
        )

    def error(self, error_type: str, context: Dict[str, Any]) -> Event:
        """Captura erro"""
        return self._create_event(
            EventType.ERROR,
            error_type,
            context,
            tags=["error"]
        )
```

- [ ] **Step 4: Rodar testes**

Run: `pytest tests/test_core_captures.py -v`

Expected: 4 testes passando

- [ ] **Step 5: Commit**

```bash
git add src/hooks/__init__.py src/hooks/core_captures.py tests/test_core_captures.py
git commit -m "feat: captura de eventos core (tool calls, git, tests, errors)"
```

---

## FASE 2: Pipeline de Consolidação

### Task 9: Checkpoint Triggers

**Files:**
- Create: `src/consolidation/__init__.py`
- Create: `src/consolidation/checkpoints.py`
- Test: `tests/test_checkpoints.py`

- [ ] **Step 1: Criar src/consolidation/__init__.py**

```python
"""Consolidação do Cerebro: extração, scoring, promoção"""
from .checkpoints import CheckpointManager
from .extractor import Extractor
from .scorer import Scorer
from .promoter import Promoter

__all__ = ["CheckpointManager", "Extractor", "Scorer", "Promoter"]
```

- [ ] **Step 2: Escrever teste para checkpoint triggers**

```python
# tests/test_checkpoints.py
import pytest
from src.consolidation.checkpoints import CheckpointManager, CheckpointTrigger


class TestCheckpointManager:

    def test_detect_feature_done(self, tmp_path):
        """Detecta fim de feature por testes passando"""
        manager = CheckpointManager(tmp_path)

        # Simula testes passando após mudanças
        trigger = manager.check_triggers({
            "tests_passed": True,
            "files_changed": ["src/auth.py"]
        })

        assert CheckpointTrigger.FEATURE_DONE in trigger

    def test_detect_session_end(self, tmp_path):
        """Detecta fim de sessão"""
        manager = CheckpointManager(tmp_path)

        trigger = manager.check_triggers({
            "session_ending": True
        })

        assert CheckpointTrigger.SESSION_END in trigger

    def test_detect_error_critical(self, tmp_path):
        """Detecta erro crítico"""
        manager = CheckpointManager(tmp_path)

        trigger = manager.check_triggers({
            "error_severity": "critical"
        })

        assert CheckpointTrigger.ERROR_CRITICAL in trigger
```

- [ ] **Step 3: Implementar checkpoints.py**

```python
# src/consolidation/checkpoints.py
from enum import Enum
from typing import Dict, List


class CheckpointTrigger(Enum):
    FEATURE_DONE = "feature_done"
    SESSION_END = "session_end"
    ERROR_CRITICAL = "error_critical"
    MANUAL = "manual"


class CheckpointManager:
    """Gerencia triggers de checkpoint"""

    def __init__(self, config_path):
        self.config_path = config_path

    def check_triggers(self, context: Dict) -> List[CheckpointTrigger]:
        """Verifica triggers baseado no contexto"""
        triggers = []

        if context.get("tests_passed") and context.get("files_changed"):
            triggers.append(CheckpointTrigger.FEATURE_DONE)

        if context.get("session_ending"):
            triggers.append(CheckpointTrigger.SESSION_END)

        if context.get("error_severity") in ["critical", "high"]:
            triggers.append(CheckpointTrigger.ERROR_CRITICAL)

        return triggers

    def should_checkpoint(self, context: Dict) -> bool:
        """Decide se deve fazer checkpoint"""
        return len(self.check_triggers(context)) > 0
```

- [ ] **Step 4: Rodar testes**

Run: `pytest tests/test_checkpoints.py -v`

Expected: 3 testes passando

- [ ] **Step 5: Commit**

```bash
git add src/consolidation/__init__.py src/consolidation/checkpoints.py tests/test_checkpoints.py
git commit -m "feat: triggers de checkpoint (feature_done, session_end, error_critical)"
```

---

## FASE 3: Índice Híbrido

### Task 10: Metadata DB

**Files:**
- Create: `src/index/__init__.py`
- Create: `src/index/metadata_db.py`
- Test: `tests/test_metadata_db.py`

- [ ] **Step 1: Criar src/index/__init__.py**

```python
"""Índice do Cerebro: SQLite + FTS + embeddings"""
from .metadata_db import MetadataDB
from .embeddings_db import EmbeddingsDB
from .queries import QueryEngine

__all__ = ["MetadataDB", "EmbeddingsDB", "QueryEngine"]
```

- [ ] **Step 2: Escrever teste para metadata DB**

```python
# tests/test_metadata_db.py
import pytest
from pathlib import Path
from src.index.metadata_db import MetadataDB


class TestMetadataDB:

    def test_create_schema(self, tmp_path):
        """Cria schema do banco"""
        db = MetadataDB(tmp_path / "metadata.db")

        # Verifica tabelas
        tables = db.list_tables()
        assert "memories" in tables
        assert "memories_fts" in tables

    def test_insert_memory(self, tmp_path):
        """Insere memória no índice"""
        db = MetadataDB(tmp_path / "metadata.db")

        db.insert({
            "id": "mem_001",
            "type": "decision",
            "project": "test-project",
            "title": "DB Choice",
            "path": "official/test-project/decisions/db-choice.md"
        })

        memories = db.search(project="test-project")
        assert len(memories) == 1

    def test_fts_search(self, tmp_path):
        """Busca full-text"""
        db = MetadataDB(tmp_path / "metadata.db")

        db.insert({
            "id": "mem_001",
            "type": "error",
            "project": "test-project",
            "title": "Deadlock no pool",
            "content": "Deadlock no connection pool",
            "tags": "deadlock,pool"
        })

        results = db.search_fts("deadlock")
        assert len(results) == 1
```

- [ ] **Step 3: Implementar metadata_db.py**

```python
# src/index/metadata_db.py
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class MetadataDB:
    """SQLite + FTS para metadados"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self):
        """Cria schema do banco"""
        conn = self._connect()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                type TEXT,
                project TEXT,
                title TEXT,
                tags TEXT,
                severity TEXT,
                impact TEXT,
                importance_score REAL,
                recency_score REAL,
                frequency_score REAL,
                links_score REAL,
                total_score REAL,
                created_at TEXT,
                updated_at TEXT,
                last_accessed TEXT,
                access_count INTEGER DEFAULT 0,
                path TEXT,
                layer TEXT,
                content_hash TEXT
            )
        """)

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                id UNINDEXED,
                title,
                content,
                tags,
                project
            )
        """)

        conn.commit()
        conn.close()

    def list_tables(self) -> List[str]:
        """Lista tabelas do banco"""
        conn = self._connect()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables

    def insert(self, data: Dict[str, Any]) -> None:
        """Insere memória no índice"""
        conn = self._connect()

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])

        conn.execute(
            f"INSERT OR REPLACE INTO memories ({columns}) VALUES ({placeholders})",
            list(data.values())
        )

        # Atualiza FTS
        if "content" in data:
            conn.execute(
                "INSERT OR REPLACE INTO memories_fts (id, title, content, tags, project) VALUES (?, ?, ?, ?, ?)",
                (data.get("id"), data.get("title", ""), data.get("content", ""), data.get("tags", ""), data.get("project", ""))
            )

        conn.commit()
        conn.close()

    def search(self, project: Optional[str] = None, type: Optional[str] = None) -> List[Dict]:
        """Busca por metadados"""
        conn = self._connect()

        query = "SELECT * FROM memories WHERE 1=1"
        params = []

        if project:
            query += " AND project = ?"
            params.append(project)

        if type:
            query += " AND type = ?"
            params.append(type)

        cursor = conn.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def search_fts(self, query: str, project: Optional[str] = None) -> List[Dict]:
        """Busca full-text"""
        conn = self._connect()

        if project:
            sql = """
                SELECT m.* FROM memories m
                JOIN memories_fts f ON f.id = m.id
                WHERE f MATCH ? AND m.project = ?
            """
            cursor = conn.execute(sql, (query, project))
        else:
            sql = """
                SELECT m.* FROM memories m
                JOIN memories_fts f ON f.id = m.id
                WHERE f MATCH ?
            """
            cursor = conn.execute(sql, (query,))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
```

- [ ] **Step 4: Rodar testes**

Run: `pytest tests/test_metadata_db.py -v`

Expected: 3 testes passando

- [ ] **Step 5: Commit**

```bash
git add src/index/__init__.py src/index/metadata_db.py tests/test_metadata_db.py
git commit -m "feat: metadata DB SQLite com FTS"
```

---

## FASE 4: Forgetting/Scoring

### Task 11: Scorer RFM

**Files:**
- Create: `src/consolidation/scorer.py`
- Test: `tests/test_scorer.py`

- [ ] **Step 1: Escrever teste para scorer**

```python
# tests/test_scorer.py
import pytest
from datetime import datetime, timedelta
from src.consolidation.scorer import Scorer, ScoringConfig


class TestScorer:

    def test_calculate_recency_score(self):
        """Calcula score de recência"""
        config = ScoringConfig()
        scorer = Scorer(config)

        recent = datetime.utcnow()
        old = datetime.utcnow() - timedelta(days=30)

        recent_score = scorer._recency_score(recent)
        old_score = scorer._recency_score(old)

        assert recent_score > old_score

    def test_calculate_total_score(self):
        """Calcula score total RFM"""
        config = ScoringConfig(
            recency_weight=0.3,
            frequency_weight=0.2,
            importance_weight=0.3,
            links_weight=0.2
        )
        scorer = Scorer(config)

        score = scorer.calculate({
            "last_accessed": datetime.utcnow(),
            "access_count": 10,
            "severity": "high",
            "related_to": ["err_001", "err_002"]
        })

        assert 0 <= score <= 1

    def test_decay_applied(self):
        """Decay reduz score com tempo"""
        config = ScoringConfig()
        scorer = Scorer(config)

        base_score = 0.8
        decayed = scorer.apply_decay(base_score, days=30, decay_rate=0.01)

        assert decayed < base_score
```

- [ ] **Step 2: Implementar scorer.py**

```python
# src/consolidation/scorer.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any
import math


@dataclass
class ScoringConfig:
    recency_weight: float = 0.3
    frequency_weight: float = 0.2
    importance_weight: float = 0.3
    links_weight: float = 0.2


class Scorer:
    """Calcula scores RFM"""

    def __init__(self, config: ScoringConfig):
        self.config = config

    def calculate(self, memory: Dict[str, Any]) -> float:
        """Calcula score total"""
        r = self._recency_score(memory.get("last_accessed"))
        f = self._frequency_score(memory.get("access_count", 0))
        i = self._importance_score(memory)
        l = self._links_score(memory.get("related_to", []))

        total = (
            self.config.recency_weight * r +
            self.config.frequency_weight * f +
            self.config.importance_weight * i +
            self.config.links_weight * l
        )

        return min(1.0, max(0.0, total))

    def _recency_score(self, last_accessed: datetime) -> float:
        """Score de recência (0-1)"""
        if not last_accessed:
            return 0.0

        days_ago = (datetime.utcnow() - last_accessed).days
        return math.exp(-0.05 * days_ago)

    def _frequency_score(self, access_count: int) -> float:
        """Score de frequência (0-1)"""
        return 1.0 - math.exp(-0.1 * access_count)

    def _importance_score(self, memory: Dict[str, Any]) -> float:
        """Score de importância baseado em severity/impact"""
        severity_map = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2}
        return severity_map.get(memory.get("severity", "low"), 0.2)

    def _links_score(self, related_to: list) -> float:
        """Score de links"""
        if not related_to:
            return 0.0
        return min(1.0, len(related_to) * 0.25)

    def apply_decay(self, score: float, days: int, decay_rate: float) -> float:
        """Aplica decay temporal"""
        return score * math.exp(-decay_rate * days)
```

- [ ] **Step 3: Rodar testes**

Run: `pytest tests/test_scorer.py -v`

Expected: 3 testes passando

- [ ] **Step 4: Commit**

```bash
git add src/consolidation/scorer.py tests/test_scorer.py
git commit -m "feat: scorer RFM com decay temporal"
```

---

### Task 12: Guard Rails

**Files:**
- Create: `src/forgetting/__init__.py`
- Create: `src/forgetting/guard_rails.py`
- Create: `src/forgetting/decay.py`
- Create: `src/forgetting/gc.py`
- Test: `tests/test_guard_rails.py`

- [ ] **Step 1: Criar src/forgetting/__init__.py**

```python
"""Forgetting do Cerebro: decay, guard rails, garbage collection"""
from .guard_rails import GuardRails
from .decay import DecayManager
from .gc import GarbageCollector

__all__ = ["GuardRails", "DecayManager", "GarbageCollector"]
```

- [ ] **Step 2: Escrever teste para guard rails**

```python
# tests/test_guard_rails.py
import pytest
from src.forgetting.guard_rails import GuardRails


class TestGuardRails:

    def test_never_delete_critical_decision(self, tmp_path):
        """Não deleta decisão crítica"""
        rails = GuardRails(tmp_path / "config.yaml")

        can_delete = rails.can_delete({
            "type": "decision",
            "tags": ["critical"]
        })

        assert can_delete is False

    def test_never_delete_high_severity_error(self, tmp_path):
        """Não deleta erro de alta severidade"""
        rails = GuardRails(tmp_path / "config.yaml")

        can_delete = rails.can_delete({
            "type": "error",
            "severity": "high"
        })

        assert can_delete is False

    def test_can_archive_old_raw_event(self, tmp_path):
        """Pode arquivar evento raw antigo"""
        rails = GuardRails(tmp_path / "config.yaml")

        should_archive = rails.should_archive({
            "layer": "raw",
            "created_at": "2026-01-01T00:00:00Z"
        }, days_threshold=30)

        assert should_archive is True
```

- [ ] **Step 3: Implementar guard_rails.py**

```python
# src/forgetting/guard_rails.py
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import yaml


class GuardRails:
    """Guard rails para forgetting"""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        if not self.config_path.exists():
            return {
                "never_delete": ["decisions.critical", "errors.severity=high"],
                "always_archive": {"raw": 30, "working": 90}
            }

        return yaml.safe_load(self.config_path.read_text())

    def can_delete(self, memory: Dict[str, Any]) -> bool:
        """Verifica se pode deletar"""
        rules = self.config.get("never_delete", [])

        for rule in rules:
            if self._matches_rule(memory, rule):
                return False

        return True

    def _matches_rule(self, memory: Dict[str, Any], rule: str) -> bool:
        """Verifica se memória corresponde à regra"""
        if rule == "decisions.critical":
            return memory.get("type") == "decision" and "critical" in memory.get("tags", [])

        if rule == "errors.severity=high":
            return memory.get("type") == "error" and memory.get("severity") in ["high", "critical"]

        if rule == "errors.impact=critical":
            return memory.get("type") == "error" and memory.get("impact") == "critical"

        return False

    def should_archive(self, memory: Dict[str, Any], days_threshold: int) -> bool:
        """Verifica se deve arquivar"""
        created = memory.get("created_at")
        if not created:
            return False

        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        days_old = (datetime.utcnow() - created_dt).days

        return days_old > days_threshold
```

- [ ] **Step 4: Rodar testes**

Run: `pytest tests/test_guard_rails.py -v`

Expected: 3 testes passando

- [ ] **Step 5: Commit**

```bash
git add src/forgetting/__init__.py src/forgetting/guard_rails.py tests/test_guard_rails.py
git commit -m "feat: guard rails para never_delete e always_archive"
```

---

## Self-Review do Plano

### 1. Spec Coverage

| Seção do Spec | Task(s) |
|---------------|---------|
| Schema de Evento | Task 2 |
| JSONL append-only | Task 3 |
| Session Manager | Task 4 |
| YAML Storage (Working) | Task 5 |
| Markdown Storage (Official) | Task 6 |
| MEMORY.md view | Task 7 |
| Core Captures (Hooks) | Task 8 |
| Checkpoint Triggers | Task 9 |
| Metadata DB + FTS | Task 10 |
| Scorer RFM | Task 11 |
| Guard Rails | Task 12 |

**Gaps identificados:**
- Extrator (Raw → Working) não implementado
- Promoter (Working → Official) não implementado
- Embeddings DB não implementado
- GC com log memory.gc não implementado
- CLI /checkpoint não implementado
- Hooks customizados (hooks.yaml) não implementado

### 2. Placeholder Scan

- Nenhum TBD/TODO encontrado
- Todos os passos têm código completo

### 3. Type Consistency

- `EventType` consistente em todos os arquivos
- `JSONLStorage`, `YAMLStorage`, `MarkdownStorage` com interfaces similares
- Scores: `recency_score`, `frequency_score`, `importance_score`, `links_score`, `total_score`

---

**Plano parcial salvo.** As fases 3 e 4 precisam de tarefas adicionais para completar:

- Extractor, Promoter, EmbeddingsDB, GC, CLI, Hooks customizados

Quer que eu complete as tarefas restantes ou prefere começar a execução deste plano parcial?

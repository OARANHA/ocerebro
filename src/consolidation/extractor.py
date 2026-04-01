"""Extractor: transforma eventos raw em drafts YAML para working"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from src.core.jsonl_storage import JSONLStorage
from src.core.event_schema import Event, EventType
from src.working.yaml_storage import YAMLStorage


@dataclass
class ExtractionResult:
    """Resultado da extração de eventos"""
    session_id: str
    project: str
    events: List[Event] = field(default_factory=list)
    start_event_id: Optional[str] = None
    end_event_id: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)


class Extractor:
    """
    Extrai eventos da camada raw e gera drafts YAML para working.

    Responsabilidades:
    - Ler eventos JSONL de um projeto
    - Filtrar eventos por sessão ou range
    - Agrupar eventos por tipo (tool_calls, git_events, test_results, errors)
    - Gerar resumo estruturado para draft YAML
    - Identificar events_range para rastreabilidade
    """

    def __init__(self, raw_storage: JSONLStorage, working_storage: YAMLStorage):
        """
        Inicializa o Extractor.

        Args:
            raw_storage: Instância do JSONLStorage para leitura
            working_storage: Instância do YAMLStorage para escrita dos drafts
        """
        self.raw_storage = raw_storage
        self.working_storage = working_storage

    def extract_session(self, project: str, session_id: str) -> ExtractionResult:
        """
        Extrai todos os eventos de uma sessão.

        Args:
            project: Nome do projeto
            session_id: ID da sessão

        Returns:
            Resultado da extração com eventos e resumo
        """
        all_events = self.raw_storage.read(project)

        # Filtra eventos da sessão
        session_events = [e for e in all_events if e.session_id == session_id]

        # Ordena por timestamp
        session_events.sort(key=lambda e: e.ts)

        if not session_events:
            return ExtractionResult(
                session_id=session_id,
                project=project,
                events=[],
                summary={"status": "no_events"}
            )

        # Gera resumo
        summary = self._generate_summary(session_events)

        return ExtractionResult(
            session_id=session_id,
            project=project,
            events=session_events,
            start_event_id=session_events[0].event_id,
            end_event_id=session_events[-1].event_id,
            summary=summary
        )

    def extract_range(self, project: str, start_id: str, end_id: str) -> ExtractionResult:
        """
        Extrai eventos em um range de IDs.

        Args:
            project: Nome do projeto
            start_id: ID inicial (inclusive)
            end_id: ID final (inclusive)

        Returns:
            Resultado da extração
        """
        events = self.raw_storage.read_range(project, start_id, end_id)
        events.sort(key=lambda e: e.ts)

        if not events:
            return ExtractionResult(
                session_id="unknown",
                project=project,
                events=[],
                summary={"status": "no_events_in_range"}
            )

        # Pega session_id predominante
        session_counts: Dict[str, int] = {}
        for e in events:
            session_counts[e.session_id] = session_counts.get(e.session_id, 0) + 1
        main_session = max(session_counts, key=session_counts.get)

        summary = self._generate_summary(events)

        return ExtractionResult(
            session_id=main_session,
            project=project,
            events=events,
            start_event_id=start_id,
            end_event_id=end_id,
            summary=summary
        )

    def _generate_summary(self, events: List[Event]) -> Dict[str, Any]:
        """
        Gera resumo estruturado dos eventos.

        Args:
            events: Lista de eventos

        Returns:
            Dicionário com resumo
        """
        tool_calls = [e for e in events if e.event_type == EventType.TOOL_CALL]
        git_events = [e for e in events if e.event_type == EventType.GIT_EVENT]
        test_results = [e for e in events if e.event_type == EventType.TEST_RESULT]
        errors = [e for e in events if e.event_type == EventType.ERROR]

        # Calcula duração aproximada
        if events:
            start = datetime.fromisoformat(events[0].ts.replace("Z", "+00:00"))
            end = datetime.fromisoformat(events[-1].ts.replace("Z", "+00:00"))
            duration_seconds = (end - start).total_seconds()
        else:
            duration_seconds = 0

        # Extrai arquivos changed (de tool_calls com git)
        files_changed = set()
        for tc in tool_calls:
            if tc.subtype == "Edit" and "file_path" in tc.payload.get("call", {}):
                files_changed.add(tc.payload["call"]["file_path"])

        # Extrai testes passing
        tests_passed = sum(1 for t in test_results if t.payload.get("status") == "pass")
        tests_failed = sum(1 for t in test_results if t.payload.get("status") == "fail")

        return {
            "total_events": len(events),
            "tool_calls": len(tool_calls),
            "git_events": len(git_events),
            "test_results": len(test_results),
            "errors": len(errors),
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "files_changed": list(files_changed),
            "duration_seconds": duration_seconds,
            "status": "complete"
        }

    def create_draft(
        self,
        result: ExtractionResult,
        draft_type: str = "session",
        draft_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cria draft YAML a partir do resultado da extração.

        Args:
            result: Resultado da extração
            draft_type: Tipo de draft (session, feature, error)
            draft_name: Nome do draft (opcional, gera automático se None)

        Returns:
            Dados do draft para escrita em YAML
        """
        if draft_name is None:
            draft_name = f"{draft_type}_{result.session_id[:8]}"

        # Gera lista de eventos significativos
        significant_events = []
        for event in result.events:
            if event.event_type in [EventType.ERROR, EventType.GIT_EVENT]:
                significant_events.append({
                    "type": event.event_type.value,
                    "subtype": event.subtype,
                    "summary": str(event.payload)[:200]
                })

        # Extrai erros críticos
        critical_errors = [
            e for e in result.events
            if e.event_type == EventType.ERROR
        ]

        draft = {
            "id": draft_name,
            "type": draft_type,
            "project": result.project,
            "session_id": result.session_id,
            "events_range": {
                "from": result.start_event_id,
                "to": result.end_event_id
            },
            "summary": result.summary,
            "significant_events": significant_events[:10],  # Max 10
            "critical_errors": [
                {"type": e.subtype, "context": e.payload}
                for e in critical_errors
            ],
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "needs_review": len(critical_errors) > 0 or result.summary.get("tests_failed", 0) > 0
        }

        return draft

    def write_draft(
        self,
        project: str,
        draft: Dict[str, Any],
        draft_type: str = "session"
    ) -> str:
        """
        Escreve draft em YAML na camada working.

        Args:
            project: Nome do projeto
            draft: Dados do draft
            draft_type: Tipo de draft

        Returns:
            Nome do draft escrito
        """
        draft_name = draft["id"]

        if draft_type == "session":
            self.working_storage.write_session(project, draft_name, draft)
        elif draft_type == "feature":
            self.working_storage.write_feature(project, draft_name, draft)
        else:
            # Para outros tipos, usa session como fallback
            self.working_storage.write_session(project, draft_name, draft)

        return draft_name

    def extract_and_write(
        self,
        project: str,
        session_id: str,
        draft_type: str = "session"
    ) -> str:
        """
        Extrai sessão e escreve draft em working.

        Args:
            project: Nome do projeto
            session_id: ID da sessão
            draft_type: Tipo de draft

        Returns:
            Nome do draft escrito
        """
        result = self.extract_session(project, session_id)

        if not result.events:
            raise ValueError(f"Nenhum evento encontrado para sessão {session_id}")

        draft = self.create_draft(result, draft_type)
        return self.write_draft(project, draft, draft_type)

    def find_incomplete_sessions(self, project: str) -> List[str]:
        """
        Encontra sessões incompletas (sem checkpoint.created).

        Args:
            project: Nome do projeto

        Returns:
            Lista de session_ids incompletas
        """
        all_events = self.raw_storage.read(project)

        # Agrupa por session_id
        sessions: Dict[str, List[Event]] = {}
        for e in all_events:
            if e.session_id not in sessions:
                sessions[e.session_id] = []
            sessions[e.session_id].append(e)

        # Encontra sessões sem checkpoint
        incomplete = []
        for session_id, events in sessions.items():
            has_checkpoint = any(
                e.event_type == EventType.CHECKPOINT_CREATED
                for e in events
            )
            if not has_checkpoint:
                incomplete.append(session_id)

        return incomplete

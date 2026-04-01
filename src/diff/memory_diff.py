"""Memory Diff: análise diferencial de memória entre dois pontos no tempo"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.official.markdown_storage import MarkdownStorage
from src.working.yaml_storage import YAMLStorage
from src.core.jsonl_storage import JSONLStorage
from src.core.event_schema import Event
from src.consolidation.scorer import Scorer, ScoringConfig


@dataclass
class MemoryDiffResult:
    """Resultado da análise diferencial de memória"""
    # Período analisado
    start_date: str
    end_date: str

    # Decisões
    decisions_added: List[Dict[str, Any]] = field(default_factory=list)
    decisions_removed: List[Dict[str, Any]] = field(default_factory=list)

    # Erros
    errors_documented: List[Dict[str, Any]] = field(default_factory=list)

    # Drafts pendentes
    drafts_pending: List[Dict[str, Any]] = field(default_factory=list)

    # Memórias em risco de GC
    at_risk: List[Dict[str, Any]] = field(default_factory=list)

    # Resumo de eventos
    events_summary: Dict[str, Any] = field(default_factory=dict)

    # Estatísticas
    stats: Dict[str, Any] = field(default_factory=dict)


class MemoryDiff:
    """
    Análise diferencial de memória entre dois pontos no tempo.

    Compara o estado da memória em dois períodos e gera relatórios sobre:
    - Decisões adicionadas/removidas
    - Erros documentados
    - Drafts pendentes de promoção
    - Memórias em risco de garbage collection
    - Resumo de atividade de eventos

    Addressed critical issues:
    1. Uses list_official(project, "decisions") instead of non-existent list_decisions()
    2. Parses date strings to datetime before passing to scorer
    3. Checks if promoted_at exists in draft data
    4. Robust _parse_ts() helper for Event.ts timezone handling
    5. Handles missing date fields in frontmatter gracefully
    """

    def __init__(
        self,
        official_storage: MarkdownStorage,
        working_storage: YAMLStorage,
        raw_storage: JSONLStorage
    ):
        """
        Inicializa o MemoryDiff.

        Args:
            official_storage: Instância do MarkdownStorage
            working_storage: Instância do YAMLStorage
            raw_storage: Instância do JSONLStorage
        """
        self.official = official_storage
        self.working = working_storage
        self.raw = raw_storage
        self._scorer = Scorer(ScoringConfig())

    def _parse_ts(self, ts: str) -> datetime:
        """
        Parse robusto de timestamp para datetime.

        Issue #4: Lida com edge cases de timezone

        Args:
            ts: Timestamp string (ISO format, com ou sem 'Z')

        Returns:
            datetime com timezone info
        """
        if not ts:
            return datetime.now(timezone.utc)

        # Remove 'Z' suffix se presente
        ts_clean = ts.rstrip("Z")

        try:
            dt = datetime.fromisoformat(ts_clean)
            # Adiciona UTC se nao houver timezone
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            # Fallback para now se parse falhar
            return datetime.now(timezone.utc)

    def _parse_frontmatter_dates(self, fm: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse date fields from frontmatter para datetime.

        Issue #2: Scorer.calculate() espera datetime, mas frontmatter armazena strings

        Args:
            fm: Frontmatter dictionary

        Returns:
            Dictionary com campos de data parseados
        """
        result = dict(fm)  # Copy para nao mutar original

        # Parse last_accessed
        if isinstance(result.get("last_accessed"), str):
            result["last_accessed"] = self._parse_ts(result["last_accessed"])

        # Parse date (Issue #5: pode nao existir em todos os frontmatter)
        if isinstance(result.get("date"), str):
            result["date"] = self._parse_ts(result["date"])

        # Parse created_at se existir
        if isinstance(result.get("created_at"), str):
            result["created_at"] = self._parse_ts(result["created_at"])

        return result

    def _is_in_period(self, ts: str, start: datetime, end: datetime) -> bool:
        """Verifica se timestamp está dentro do período"""
        dt = self._parse_ts(ts)
        return start <= dt <= end

    def _get_period_dates(
        self,
        period_days: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Tuple[datetime, datetime]:
        """
        Calcula datas de início e fim do período.

        Args:
            period_days: Dias do período (ex: 7, 30)
            start_date: Data de início explícita (ISO string)
            end_date: Data de fim explícita (ISO string)

        Returns:
            Tuple (start_date, end_date) como datetime
        """
        now = datetime.now(timezone.utc)

        if start_date and end_date:
            # Datas explícitas
            start = self._parse_ts(start_date)
            end = self._parse_ts(end_date)
        elif period_days:
            # Período relativo
            end = now
            from datetime import timedelta
            start = now - timedelta(days=period_days)
        else:
            # Default: últimos 7 dias
            from datetime import timedelta
            end = now
            start = now - timedelta(days=7)

        return start, end

    def _compare_decisions(
        self,
        project: str,
        start: datetime,
        end: datetime
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Compara decisões entre dois períodos.

        Issue #1: Usa list_official(project, "decisions") em vez de list_decisions()

        Args:
            project: Nome do projeto
            start: Data de início
            end: Data de fim

        Returns:
            Tuple (decisoes_adicionadas, decisoes_removidas)
        """
        # Issue #1: list_official com subdir "decisions"
        decisions = self.official.list_official(project, "decisions")

        added = []
        removed = []

        for decision in decisions:
            # Issue #5: date field pode nao existir
            date_str = decision.get("date")
            if not date_str:
                # Tenta fallback para created_at ou events_from
                date_str = decision.get("created_at") or decision.get("events_from")

            if date_str:
                decision_date = self._parse_ts(date_str)
                if start <= decision_date <= end:
                    added.append({
                        "id": decision.get("decision_id", decision.get("id", "unknown")),
                        "title": decision.get("title", "Sem título"),
                        "date": date_str,
                        "status": decision.get("status", "unknown"),
                        "tags": decision.get("tags", [])
                    })

        # Nota: decisoes removidas sao mais complexas - requereria snapshot histórico
        # Por enquanto, retornamos lista vazia até que histórico seja implementado
        return added, removed

    def _get_errors_documented(
        self,
        project: str,
        start: datetime,
        end: datetime
    ) -> List[Dict[str, Any]]:
        """
        Obtém erros documentados no período.

        Args:
            project: Nome do projeto
            start: Data de início
            end: Data de fim

        Returns:
            Lista de erros documentados
        """
        errors = self.official.list_official(project, "errors")
        documented = []

        for error in errors:
            # Issue #5: date field pode nao existir
            date_str = error.get("date") or error.get("created_at")
            if date_str:
                error_date = self._parse_ts(date_str)
                if start <= error_date <= end:
                    documented.append({
                        "id": error.get("error_id", error.get("id", "unknown")),
                        "severity": error.get("severity", "unknown"),
                        "status": error.get("status", "unknown"),
                        "category": error.get("category", "unknown"),
                        "date": date_str
                    })

        return documented

    def _get_pending_drafts(
        self,
        project: str,
        start: datetime,
        end: datetime
    ) -> List[Dict[str, Any]]:
        """
        Obtém drafts pendentes de promoção.

        Issue #3: Verifica se promoted_at existe e lida gracefulmente

        Args:
            project: Nome do projeto
            start: Data de início
            end: Data de fim

        Returns:
            Lista de drafts pendentes
        """
        pending = []

        # Sessions
        sessions = self.working.list_sessions(project)
        for session in sessions:
            status = session.get("status", "draft")
            # Issue #3: promoted_at pode nao existir
            promoted_at = session.get("promoted_at")

            if status in ["draft", "needs_review"] and not promoted_at:
                # Verifica se foi criado/modified no período
                session_ts = session.get("created_at") or session.get("updated_at")
                if not session_ts or self._is_in_period(session_ts, start, end):
                    pending.append({
                        "type": "session",
                        "id": session.get("id", "unknown"),
                        "status": status,
                        "needs_review": session.get("needs_review", False),
                        "created_at": session_ts
                    })

        # Features
        features = self.working.list_features(project)
        for feature in features:
            status = feature.get("status", "draft")
            promoted_at = feature.get("promoted_at")

            if status in ["draft", "needs_review"] and not promoted_at:
                feature_ts = feature.get("created_at") or feature.get("updated_at")
                if not feature_ts or self._is_in_period(feature_ts, start, end):
                    pending.append({
                        "type": "feature",
                        "id": feature.get("id", "unknown"),
                        "status": status,
                        "needs_review": feature.get("needs_review", False),
                        "created_at": feature_ts
                    })

        return pending

    def _get_at_risk_memories(
        self,
        project: str,
        threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Identifica memórias em risco de garbage collection.

        Issue #2: Parse dates antes de passar para scorer

        Args:
            project: Nome do projeto
            threshold: Threshold de score para considerar em risco

        Returns:
            Lista de memórias em risco
        """
        at_risk = []

        # Decision memórias
        decisions = self.official.list_official(project, "decisions")
        for decision in decisions:
            # Issue #2: Parse dates antes de scorer
            decision_parsed = self._parse_frontmatter_dates(decision)

            try:
                score = self._scorer.calculate(decision_parsed)
                if score < threshold:
                    at_risk.append({
                        "type": "decision",
                        "id": decision.get("decision_id", decision.get("id", "unknown")),
                        "title": decision.get("title", "Sem título"),
                        "score": round(score, 3),
                        "last_accessed": decision.get("last_accessed"),
                        "risk_level": "high" if score < 0.15 else "medium"
                    })
            except Exception:
                # Se scorer falhar, ignora esta memória
                continue

        # Error memórias
        errors = self.official.list_official(project, "errors")
        for error in errors:
            error_parsed = self._parse_frontmatter_dates(error)

            try:
                score = self._scorer.calculate(error_parsed)
                if score < threshold:
                    at_risk.append({
                        "type": "error",
                        "id": error.get("error_id", error.get("id", "unknown")),
                        "severity": error.get("severity", "unknown"),
                        "score": round(score, 3),
                        "last_accessed": error.get("last_accessed"),
                        "risk_level": "high" if score < 0.15 else "medium"
                    })
            except Exception:
                continue

        return at_risk

    def _get_events_summary(
        self,
        project: str,
        start: datetime,
        end: datetime
    ) -> Dict[str, Any]:
        """
        Gera resumo de eventos no período.

        Issue #4: Usa _parse_ts robusto para Event.ts

        Args:
            project: Nome do projeto
            start: Data de início
            end: Data de fim

        Returns:
            Resumo de eventos
        """
        # Lê todos os eventos do projeto (método correto: read())
        events = self.raw.read(project)

        # Filtra por período
        filtered = []
        for event in events:
            # Issue #4: Parse robusto do timestamp
            event_ts = self._parse_ts(event.ts if hasattr(event, 'ts') else event.get('ts', ''))
            if start <= event_ts <= end:
                filtered.append(event)

        # Agrupa por tipo
        by_type: Dict[str, int] = {}
        by_subtype: Dict[str, int] = {}
        by_origin: Dict[str, int] = {}

        for event in filtered:
            event_type = event.event_type if hasattr(event, 'event_type') else event.get('event_type', 'unknown')
            event_subtype = event.subtype if hasattr(event, 'subtype') else event.get('subtype', 'unknown')
            event_origin = event.origin if hasattr(event, 'origin') else event.get('origin', 'unknown')

            by_type[event_type] = by_type.get(event_type, 0) + 1
            by_subtype[event_subtype] = by_subtype.get(event_subtype, 0) + 1
            by_origin[event_origin] = by_origin.get(event_origin, 0) + 1

        return {
            "total_events": len(filtered),
            "by_type": by_type,
            "by_subtype": by_subtype,
            "by_origin": by_origin,
            "period_start": start.isoformat(),
            "period_end": end.isoformat()
        }

    def analyze(
        self,
        project: str,
        period_days: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        gc_threshold: float = 0.3
    ) -> MemoryDiffResult:
        """
        Analisa diferenças de memória entre dois pontos no tempo.

        Args:
            project: Nome do projeto
            period_days: Dias do período (ex: 7, 30)
            start_date: Data de início explícita (ISO string)
            end_date: Data de fim explícita (ISO string)
            gc_threshold: Threshold para garbage collection risk

        Returns:
            MemoryDiffResult com análise completa
        """
        # Calcula datas do período
        start, end = self._get_period_dates(period_days, start_date, end_date)

        # Compara decisões (Issue #1: usa list_official com subdir)
        decisions_added, decisions_removed = self._compare_decisions(project, start, end)

        # Erros documentados
        errors_documented = self._get_errors_documented(project, start, end)

        # Drafts pendentes (Issue #3: checa promoted_at)
        drafts_pending = self._get_pending_drafts(project, start, end)

        # Memórias em risco (Issue #2: parse dates antes de scorer)
        at_risk = self._get_at_risk_memories(project, gc_threshold)

        # Resumo de eventos (Issue #4: parse robusto de ts)
        events_summary = self._get_events_summary(project, start, end)

        # Estatísticas
        stats = {
            "decisions_added": len(decisions_added),
            "decisions_removed": len(decisions_removed),
            "errors_documented": len(errors_documented),
            "drafts_pending": len(drafts_pending),
            "at_risk_count": len(at_risk),
            "total_events": events_summary["total_events"]
        }

        return MemoryDiffResult(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            decisions_added=decisions_added,
            decisions_removed=decisions_removed,
            errors_documented=errors_documented,
            drafts_pending=drafts_pending,
            at_risk=at_risk,
            events_summary=events_summary,
            stats=stats
        )

    def generate_report(self, result: MemoryDiffResult, format: str = "markdown") -> str:
        """
        Gera relatório em formato legível.

        Args:
            result: Resultado da análise
            format: Formato de saída (markdown, json)

        Returns:
            Relatório formatado
        """
        if format == "json":
            import json
            from dataclasses import asdict
            return json.dumps(asdict(result), indent=2)

        # Markdown (default)
        lines = [
            "# Memory Diff Report",
            "",
            f"**Período:** {result.start_date[:10]} até {result.end_date[:10]}",
            "",
            "## Resumo",
            "",
            f"- Decisões adicionadas: {result.stats.get('decisions_added', 0)}",
            f"- Decisões removidas: {result.stats.get('decisions_removed', 0)}",
            f"- Erros documentados: {result.stats.get('errors_documented', 0)}",
            f"- Drafts pendentes: {result.stats.get('drafts_pending', 0)}",
            f"- Memórias em risco: {result.stats.get('at_risk_count', 0)}",
            f"- Total de eventos: {result.stats.get('total_events', 0)}",
            "",
        ]

        # Decisões adicionadas
        if result.decisions_added:
            lines.append("## Decisões Adicionadas")
            lines.append("")
            for d in result.decisions_added:
                lines.append(f"- **[{d['id']}]** {d['title']} ({d['date'][:10]})")
            lines.append("")

        # Erros documentados
        if result.errors_documented:
            lines.append("## Erros Documentados")
            lines.append("")
            for e in result.errors_documented:
                lines.append(f"- **[{e['id']}]** {e['category']} - {e['severity']} ({e['date'][:10]})")
            lines.append("")

        # Drafts pendentes
        if result.drafts_pending:
            lines.append("## Drafts Pendentes de Promoção")
            lines.append("")
            for d in result.drafts_pending:
                review_flag = " [NEEDS REVIEW]" if d.get('needs_review') else ""
                lines.append(f"- **[{d['type']}/{d['id']}]**{review_flag}")
            lines.append("")

        # Memórias em risco
        if result.at_risk:
            lines.append("## Memórias em Risco de GC")
            lines.append("")
            for m in sorted(result.at_risk, key=lambda x: x['score']):
                risk_emoji = "[CRITICAL]" if m['risk_level'] == 'high' else "[WARN]"
                lines.append(f"- {risk_emoji} **[{m['type']}/{m['id']}]** {m.get('title', m.get('severity', ''))} (score: {m['score']:.3f})")
            lines.append("")

        # Eventos
        if result.events_summary.get('by_type'):
            lines.append("## Eventos por Tipo")
            lines.append("")
            for event_type, count in sorted(result.events_summary['by_type'].items(), key=lambda x: -x[1]):
                lines.append(f"- {event_type}: {count}")
            lines.append("")

        return "\n".join(lines)

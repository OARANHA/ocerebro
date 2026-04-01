"""Promoter: promove drafts de working para official"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from src.working.yaml_storage import YAMLStorage
from src.official.markdown_storage import MarkdownStorage
from src.official.templates import ErrorTemplate, DecisionTemplate


@dataclass
class PromotionResult:
    """Resultado da promoção"""
    success: bool
    source_type: str
    source_id: str
    target_type: str
    target_path: str
    promoted_at: str
    metadata: Dict[str, Any] = None


class Promoter:
    """
    Promove drafts de working para official.

    Responsabilidades:
    - Ler drafts YAML de working
    - Transformar em Markdown com frontmatter
    - Escrever em official/{type}/{project}/
    - Registrar evento promotion.performed
    - Suportar supervisão humana para casos ambíguos
    """

    def __init__(
        self,
        working_storage: YAMLStorage,
        official_storage: MarkdownStorage
    ):
        """
        Inicializa o Promoter.

        Args:
            working_storage: Instância do YAMLStorage
            official_storage: Instância do MarkdownStorage
        """
        self.working_storage = working_storage
        self.official_storage = official_storage

    def promote_session(
        self,
        project: str,
        session_id: str,
        promote_to: str = "decision"
    ) -> Optional[PromotionResult]:
        """
        Promove sessão para official.

        Args:
            project: Nome do projeto
            session_id: ID da sessão
            promote_to: Tipo de promoção (decision, error)

        Returns:
            Resultado da promoção ou None se falhar
        """
        draft = self.working_storage.read_session(project, session_id)

        if not draft:
            return None

        return self._promote_draft(
            project=project,
            draft=draft,
            draft_type="session",
            promote_to=promote_to
        )

    def promote_feature(
        self,
        project: str,
        feature_name: str,
        promote_to: str = "decision"
    ) -> Optional[PromotionResult]:
        """
        Promove feature para official.

        Args:
            project: Nome do projeto
            feature_name: Nome da feature
            promote_to: Tipo de promoção

        Returns:
            Resultado da promoção ou None se falhar
        """
        draft = self.working_storage.read_feature(project, feature_name)

        if not draft:
            return None

        return self._promote_draft(
            project=project,
            draft=draft,
            draft_type="feature",
            promote_to=promote_to
        )

    def _promote_draft(
        self,
        project: str,
        draft: Dict[str, Any],
        draft_type: str,
        promote_to: str
    ) -> PromotionResult:
        """
        Promove draft para official.

        Args:
            project: Nome do projeto
            draft: Dados do draft
            draft_type: Tipo do draft
            promote_to: Tipo de promoção

        Returns:
            Resultado da promoção
        """
        draft_id = draft.get("id", "unknown")

        if promote_to == "decision":
            return self._promote_to_decision(project, draft, draft_id)
        elif promote_to == "error":
            return self._promote_to_error(project, draft, draft_id)
        else:
            raise ValueError(f"Tipo de promoção desconhecido: {promote_to}")

    def _promote_to_decision(
        self,
        project: str,
        draft: Dict[str, Any],
        draft_id: str
    ) -> PromotionResult:
        """
        Promove draft para decisão arquitetural.

        Args:
            project: Nome do projeto
            draft: Dados do draft
            draft_id: ID do draft

        Returns:
            Resultado da promoção
        """
        summary = draft.get("summary", {})

        # Gera título da decisão
        title = draft.get("title", f"Decisão {draft_id}")
        if not draft.get("title") and summary.get("files_changed"):
            title = f"Mudanças em {', '.join(summary['files_changed'][:2])}"

        # Prepara frontmatter
        frontmatter = DecisionTemplate.frontmatter(
            decision_id=draft_id,
            title=title,
            status="approved",
            date=datetime.now(timezone.utc).isoformat()[:10],
            project=project,
            tags=["auto-promoted", draft.get("type", "session")]
        )

        # Adiciona metadados do events_range
        if "events_range" in draft:
            frontmatter["events_from"] = draft["events_range"].get("from")
            frontmatter["events_to"] = draft["events_range"].get("to")

        # Gera corpo
        body_sections = [
            "## Resumo",
            "",
            f"Sessão: {draft.get('session_id', 'N/A')}",
            f"Total de eventos: {summary.get('total_events', 0)}",
            ""
        ]

        # Adiciona arquivos changed
        if summary.get("files_changed"):
            body_sections.extend([
                "## Arquivos Modificados",
                ""
            ])
            for f in summary["files_changed"]:
                body_sections.append(f"- `{f}`")
            body_sections.append("")

        # Adiciona eventos significativos
        if draft.get("significant_events"):
            body_sections.extend([
                "## Eventos Significativos",
                ""
            ])
            for evt in draft["significant_events"][:5]:
                body_sections.append(f"- **{evt.get('type', 'unknown')}** ({evt.get('subtype', '')}): {evt.get('summary', '')[:100]}")
            body_sections.append("")

        # Adiciona testes
        if summary.get("tests_passed") or summary.get("tests_failed"):
            body_sections.extend([
                "## Testes",
                "",
                f"- Passando: {summary.get('tests_passed', 0)}",
                f"- Falhando: {summary.get('tests_failed', 0)}",
                ""
            ])

        content = "\n".join(body_sections)

        # Escreve em official
        self.official_storage.write_decision(
            project=project,
            name=draft_id,
            frontmatter=frontmatter,
            content=content
        )

        return PromotionResult(
            success=True,
            source_type=draft.get("type", "session"),
            source_id=draft_id,
            target_type="decision",
            target_path=f"official/{project}/decisions/{draft_id}.md",
            promoted_at=datetime.now(timezone.utc).isoformat(),
            metadata={"title": title}
        )

    def _promote_to_error(
        self,
        project: str,
        draft: Dict[str, Any],
        draft_id: str
    ) -> PromotionResult:
        """
        Promove draft para erro documentado.

        Args:
            project: Nome do projeto
            draft: Dados do draft
            draft_id: ID do draft

        Returns:
            Resultado da promoção
        """
        critical_errors = draft.get("critical_errors", [])

        if not critical_errors:
            # Se não há erros críticos, não faz sentido promover como erro
            return PromotionResult(
                success=False,
                source_type=draft.get("type", "session"),
                source_id=draft_id,
                target_type="error",
                target_path="",
                promoted_at=datetime.now(timezone.utc).isoformat(),
                metadata={"reason": "no_critical_errors"}
            )

        # Pega primeiro erro crítico
        error = critical_errors[0]

        # Prepara frontmatter
        frontmatter = ErrorTemplate.frontmatter(
            error_id=draft_id,
            severity="high",
            status="resolved",
            category=error.get("type", "unknown"),
            area="auto-detected",
            project=project,
            tags=["auto-promoted"]
        )

        # Gera corpo
        error_original = str(error.get("context", {}))[:500]

        # BUG-02 FIX: Extrai causa raiz e solução dos dados do erro
        causa_raiz = error.get("message") or error.get("details") or error.get("root_cause") or ""
        solucao = error.get("resolution") or error.get("solution") or error.get("fix_applied") or ""

        body = ErrorTemplate.body(
            error_original=error_original,
            causa_raiz=causa_raiz,
            solucao_aplicada=solucao,
            prevencao_futura=None
        )

        # Escreve em official
        self.official_storage.write_error(
            project=project,
            name=draft_id,
            frontmatter=frontmatter,
            content=body
        )

        return PromotionResult(
            success=True,
            source_type=draft.get("type", "session"),
            source_id=draft_id,
            target_type="error",
            target_path=f"official/{project}/errors/{draft_id}.md",
            promoted_at=datetime.now(timezone.utc).isoformat(),
            metadata={"error_type": error.get("type")}
        )

    def promote_with_review(
        self,
        project: str,
        draft_id: str,
        draft_type: str,
        promote_to: str,
        review_callback=None
    ) -> Optional[PromotionResult]:
        """
        Promove draft com revisão opcional.

        Args:
            project: Nome do projeto
            draft_id: ID do draft
            draft_type: Tipo do draft (session, feature)
            promote_to: Tipo de promoção (decision, error)
            review_callback: Callback para revisão (recebe draft, retorna approve/skip/reject)

        Returns:
            Resultado da promoção ou None se skip/reject
        """
        # Lê draft
        if draft_type == "session":
            draft = self.working_storage.read_session(project, draft_id)
        elif draft_type == "feature":
            draft = self.working_storage.read_feature(project, draft_id)
        else:
            return None

        if not draft:
            return None

        # Chama callback de revisão se fornecido
        if review_callback:
            action = review_callback(draft)
            if action == "skip":
                return None
            elif action == "reject":
                draft["status"] = "rejected"
                if draft_type == "session":
                    self.working_storage.write_session(project, draft_id, draft)
                else:
                    self.working_storage.write_feature(project, draft_id, draft)
                return None

        # Promove
        return self._promote_draft(
            project=project,
            draft=draft,
            draft_type=draft_type,
            promote_to=promote_to
        )

    def list_pending_promotions(self, project: str) -> List[Dict[str, Any]]:
        """
        Lista drafts pendentes de promoção.

        Args:
            project: Nome do projeto

        Returns:
            Lista de drafts com status=draft ou needs_review
        """
        pending = []

        # Verifica sessions
        sessions = self.working_storage.list_sessions(project)
        for session in sessions:
            if session.get("status") in ["draft", "needs_review"]:
                pending.append({
                    "type": "session",
                    "id": session.get("id"),
                    "status": session.get("status"),
                    "needs_review": session.get("needs_review", False)
                })

        # Verifica features
        features = self.working_storage.list_features(project)
        for feature in features:
            if feature.get("status") in ["draft", "needs_review"]:
                pending.append({
                    "type": "feature",
                    "id": feature.get("id"),
                    "status": feature.get("status"),
                    "needs_review": feature.get("needs_review", False)
                })

        return pending

    def mark_promoted(
        self,
        project: str,
        draft_id: str,
        draft_type: str,
        result: PromotionResult
    ) -> None:
        """
        Marca draft como promovido.

        Args:
            project: Nome do projeto
            draft_id: ID do draft
            draft_type: Tipo do draft
            result: Resultado da promoção
        """
        draft = {
            "status": "promoted",
            "promoted_at": result.promoted_at,
            "promoted_to": result.target_type,
            "promoted_path": result.target_path
        }

        # Atualiza draft original
        if draft_type == "session":
            existing = self.working_storage.read_session(project, draft_id)
            if existing:
                existing.update(draft)
                self.working_storage.write_session(project, draft_id, existing)
        elif draft_type == "feature":
            existing = self.working_storage.read_feature(project, draft_id)
            if existing:
                existing.update(draft)
                self.working_storage.write_feature(project, draft_id, existing)

"""Templates para camada Official do Cerebro"""

from typing import Any, Dict, List, Optional


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
        tags: List[str] = None,
        related_to: List[str] = None,
        similar_to: List[str] = None
    ) -> Dict[str, Any]:
        """Cria frontmatter para erro"""
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
        prevencao_futura: Optional[str] = None
    ) -> str:
        """Cria corpo do post-mortem de erro"""
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
        decision_id: str,
        title: str,
        status: str,
        date: str,
        project: str,
        tags: List[str] = None,
        related_to: List[str] = None
    ) -> Dict[str, Any]:
        """Cria frontmatter para decisão"""
        return {
            "id": decision_id,
            "type": "decision",
            "title": title,
            "status": status,
            "date": date,
            "project": project,
            "tags": tags or [],
            "related_to": related_to or []
        }

    @staticmethod
    def body(
        contexto: str,
        decisao: str,
        alternativas: Optional[str] = None,
        consequencias: Optional[str] = None
    ) -> str:
        """Cria corpo da decisão"""
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

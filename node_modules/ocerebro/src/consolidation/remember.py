"""Remember: revisão e promoção de memórias (replica /remember interno da Anthropic).

Replica o fluxo do remember.ts do Claude Code:
1. Lê todas as camadas de memória (MEMORY.md, CLAUDE.md, CLAUDE.local.md)
2. Classifica entradas por tipo (user/feedback/project/reference)
3. Detecta duplicatas, conflitos e entradas desatualizadas
4. Propõe relatório antes de aplicar qualquer mudança
5. Só aplica com aprovação explícita

O /remember interno é bloqueado por USER_TYPE === 'ant' — só funcionários
da Anthropic têm acesso. Este módulo entrega o mesmo fluxo para todos.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from src.core.paths import (
    get_auto_mem_path,
    get_memory_index,
    get_user_memory_path,
    get_project_memory_path,
)
from src.memdir.scanner import scan_memory_files, MemoryHeader, parse_frontmatter
from src.working.yaml_storage import YAMLStorage
from src.official.markdown_storage import MarkdownStorage
from src.consolidation.promoter import Promoter


MemoryType = Literal['user', 'feedback', 'project', 'reference']
MemoryScope = Literal['private', 'team']
MemoryDest = Literal['claude_md', 'claude_local', 'team', 'stay', 'ambiguous', 'reject']


@dataclass
class MemoryEntry:
    """Entrada de memória de qualquer camada.

    Attributes:
        source: Arquivo de origem (path absoluto)
        layer: Camada (memory, claude_md, claude_local)
        type: Tipo de memória
        name: Nome da memória
        description: Descrição
        content: Conteúdo completo
        mtime: Timestamp de modificação
    """
    source: Path
    layer: str
    type: Optional[MemoryType] = None
    name: Optional[str] = None
    description: Optional[str] = None
    content: str = ""
    mtime: float = 0.0


@dataclass
class ClassificationResult:
    """Resultado da classificação de uma memória.

    Attributes:
        entry: Entrada original
        proposed_type: Tipo proposto
        proposed_scope: Escopo proposto (private/team)
        proposed_dest: Destino proposto
        reason: Razão da classificação
        conflicts: Conflitos detectados com outras camadas
        is_duplicate: Se é duplicata de memória existente
    """
    entry: MemoryEntry
    proposed_type: Optional[MemoryType] = None
    proposed_scope: MemoryScope = 'private'
    proposed_dest: MemoryDest = 'stay'
    reason: str = ""
    conflicts: List[str] = field(default_factory=list)
    is_duplicate: bool = False


@dataclass
class RememberReport:
    """Relatório completo do remember.

    Attributes:
        promotions: Memórias para promover
        cleanup: Duplicatas, conflitos, desatualizadas para remover
        ambiguous: Entradas que precisam de input do usuário
        no_action: Entradas que não requerem ação
    """
    promotions: List[Tuple[MemoryEntry, ClassificationResult]] = field(default_factory=list)
    cleanup: List[Tuple[MemoryEntry, str]] = field(default_factory=list)
    ambiguous: List[Tuple[MemoryEntry, str]] = field(default_factory=list)
    no_action: List[MemoryEntry] = field(default_factory=list)


# ============================================================================
# CLASSIFICADOR DE MEMÓRIAS
# ============================================================================

class MemoryClassifier:
    """Classifica memórias usando taxonomia da Anthropic.

    Replica a lógica de classification do remember.ts interno.
    """

    # Regras de classificação baseadas em memoryTypes.ts
    TYPE_KEYWORDS = {
        'user': ['preferência', 'objetivo', 'papel', 'experiência', 'background', 'skill'],
        'feedback': ['não', 'evite', 'prefira', 'sempre', 'nunca', 'corrija', 'confirme'],
        'project': ['deadline', 'release', 'entrega', 'milestone', 'sprint', 'projeto'],
        'reference': ['link', 'url', 'docs', 'documentação', 'repositório', 'dashboard'],
    }

    DEST_RULES = {
        'user': 'claude_local',  # Sempre privado
        'feedback': 'claude_local',  # Padrão: privado, team se convenção de projeto
        'project': 'claude_md',  # Tendência forte para team
        'reference': 'claude_md',  # Geralmente team
    }

    def classify(self, entry: MemoryEntry, existing: List[MemoryEntry] = None) -> ClassificationResult:
        """
        Classifica uma entrada de memória.

        Args:
            entry: Entrada para classificar
            existing: Lista de memórias existentes para verificar conflitos

        Returns:
            ClassificationResult com tipo, escopo e destino propostos
        """
        result = ClassificationResult(entry=entry)

        # Passo 1: Determina tipo baseado em palavras-chave e contexto
        result.proposed_type = self._infer_type(entry)

        # Passo 2: Determina escopo (private vs team)
        result.proposed_scope = self._infer_scope(result.proposed_type, entry)

        # Passo 3: Determina destino
        result.proposed_dest = self.DEST_RULES.get(result.proposed_type, 'stay')

        # Passo 4: Verifica duplicatas e conflitos
        if existing:
            self._check_conflicts(entry, existing, result)

        # Passo 5: Gera razão
        result.reason = self._generate_reason(result)

        return result

    def _infer_type(self, entry: MemoryEntry) -> MemoryType:
        """Infere tipo baseado em conteúdo e descrição."""
        text = (entry.description or "") + " " + (entry.content or "")[:500]
        text_lower = text.lower()

        scores = {}
        for mem_type, keywords in self.TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text_lower)
            scores[mem_type] = score

        # Retorna tipo com maior score
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)

        # Fallback: tenta inferir por contexto
        if entry.layer == 'claude_local':
            return 'feedback'
        if entry.layer == 'claude_md':
            return 'project'

        return 'project'  # Default

    def _infer_scope(self, mem_type: MemoryType, entry: MemoryEntry) -> MemoryScope:
        """Infere escopo (private vs team)."""
        if mem_type == 'user':
            return 'private'  # Sempre privado

        if mem_type == 'feedback':
            # Feedback é privado por padrão, team se for convenção de projeto
            text = (entry.description or "").lower()
            if any(kw in text for kw in ['projeto', 'time', 'convenção', 'padrão']):
                return 'team'
            return 'private'

        if mem_type in ['project', 'reference']:
            # Tendência para team
            return 'team'

        return 'private'

    def _check_conflicts(
        self,
        entry: MemoryEntry,
        existing: List[MemoryEntry],
        result: ClassificationResult
    ) -> None:
        """Verifica duplicatas e conflitos com outras camadas."""
        for existing_entry in existing:
            # Verifica duplicata por nome
            if entry.name and existing_entry.name:
                if entry.name.lower() == existing_entry.name.lower():
                    result.is_duplicate = True
                    result.conflicts.append(f"Duplicata de {existing_entry.source}")
                    return

            # Verifica conflito de conteúdo
            if entry.description and existing_entry.description:
                if entry.description.lower() == existing_entry.description.lower():
                    result.conflicts.append(f"Conteúdo idêntico em {existing_entry.source}")

    def _generate_reason(self, result: ClassificationResult) -> str:
        """Gera razão legível para a classificação."""
        reasons = []

        reasons.append(f"Tipo: {result.proposed_type or 'não determinado'}")
        reasons.append(f"Escopo: {result.proposed_scope}")

        if result.is_duplicate:
            reasons.append("Duplicata detectada")

        if result.conflicts:
            reasons.append(f"Conflitos: {', '.join(result.conflicts)}")

        return "; ".join(reasons)


# ============================================================================
# GATHER LAYERS
# ============================================================================

def gather_layers(project_root: Path = None) -> Tuple[List[MemoryEntry], Dict[str, Any]]:
    """
    Lê todas as camadas de memória.

    Replica gatherLayers() do remember.ts interno.

    Camadas lidas:
    1. MEMORY.md + arquivos linkados (memória automática)
    2. CLAUDE.md (se existir)
    3. CLAUDE.local.md (se existir)

    Args:
        project_root: Raiz do projeto (default: git root)

    Returns:
        Tuple (lista de todas as entradas, metadados das camadas)
    """
    memory_dir = get_auto_mem_path(project_root)
    entries = []
    layers = {
        'memory': [],
        'claude_md': None,
        'claude_local': None,
    }

    # Camada 1: MEMORY.md + arquivos linkados
    memory_index = get_memory_index(memory_dir)
    if memory_index.exists():
        content = memory_index.read_text(encoding="utf-8")
        layers['memory'] = content

        # Parse linhas do índice para extrair links
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- [") or line.startswith("- "):
                # Extrai nome do arquivo do link
                # Formato: "- [type] filename.md (timestamp): description"
                import re
                match = re.search(r'\]\s+(\S+\.md)', line)
                if match:
                    filename = match.group(1)
                    file_path = memory_dir / filename

                    if file_path.exists():
                        entry = read_memory_file(file_path, 'memory')
                        if entry:
                            entries.append(entry)

    # Camada 2: CLAUDE.md (projeto)
    claude_md_path = get_project_memory_path(memory_dir)
    if claude_md_path.exists():
        entry = read_memory_file(claude_md_path, 'claude_md')
        if entry:
            entries.append(entry)
            layers['claude_md'] = entry.content

    # Camada 3: CLAUDE.local.md (usuário)
    claude_local_path = get_user_memory_path(memory_dir)
    if claude_local_path.exists():
        entry = read_memory_file(claude_local_path, 'claude_local')
        if entry:
            entries.append(entry)
            layers['claude_local'] = entry.content

    return entries, layers


def read_memory_file(file_path: Path, layer: str) -> Optional[MemoryEntry]:
    """
    Lê arquivo de memória e parseia frontmatter.

    Args:
        file_path: Path do arquivo
        layer: Camada de origem

    Returns:
        MemoryEntry ou None se falhar
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        stat = file_path.stat()

        # Parse frontmatter
        frontmatter = parse_frontmatter(content)

        return MemoryEntry(
            source=file_path,
            layer=layer,
            type=frontmatter.get("type"),
            name=frontmatter.get("name"),
            description=frontmatter.get("description"),
            content=content,
            mtime=stat.st_mtime
        )
    except Exception:
        return None


# ============================================================================
# FIND CLEANUP
# ============================================================================

def find_cleanup(entries: List[MemoryEntry], classifications: Dict[str, ClassificationResult]) -> List[Tuple[MemoryEntry, str]]:
    """
    Encontra memórias candidatas a cleanup.

    Replica findCleanup() do remember.ts interno.

    Critérios:
    - Duplicatas: entrada em memory/ já em CLAUDE.md
    - Desatualizadas: CLAUDE.md contradiz entry mais recente
    - Conflitos: contradição entre camadas

    Args:
        entries: Lista de todas as entradas
        classifications: Classificações de cada entrada

    Returns:
        Lista de (entrada, razão para cleanup)
    """
    cleanup = []

    # Agrupa entradas por nome
    by_name: Dict[str, List[MemoryEntry]] = {}
    for entry in entries:
        if entry.name:
            key = entry.name.lower()
            by_name.setdefault(key, []).append(entry)

    # Verifica duplicatas
    for name, group in by_name.items():
        if len(group) > 1:
            # Ordena por mtime (mais recente primeiro)
            group.sort(key=lambda e: e.mtime, reverse=True)

            # Mantém a mais recente, marca outras como cleanup
            for entry in group[1:]:
                cleanup.append((entry, f"Duplicata de {group[0].source}"))

    # Verifica conflitos entre camadas
    memory_entries = [e for e in entries if e.layer == 'memory']
    claude_md_entries = [e for e in entries if e.layer == 'claude_md']

    for mem_entry in memory_entries:
        for claude_entry in claude_md_entries:
            if mem_entry.name and claude_entry.name:
                if mem_entry.name.lower() == claude_entry.name.lower():
                    # Mesmo nome, camadas diferentes — verifica conflito
                    if mem_entry.description != claude_entry.description:
                        # Desatualizada — mantém a mais recente
                        if mem_entry.mtime > claude_entry.mtime:
                            cleanup.append((claude_entry, f"Desatualizada (memória mais recente: {mem_entry.source})"))
                        else:
                            cleanup.append((mem_entry, f"Desatualizada (CLAUDE.md mais recente: {claude_entry.source})"))

    return cleanup


# ============================================================================
# ORQUESTRADOR PRINCIPAL
# ============================================================================

def run_remember(
    project_root: Path = None,
    dry_run: bool = True,
) -> RememberReport:
    """
    Executa fluxo remember de revisão e promoção.

    Replica o fluxo do /remember interno da Anthropic.

    Passos:
    1. gather_layers() — lê todas as camadas
    2. classify_entries() — classifica por tipo
    3. find_cleanup() — detecta duplicatas e conflitos
    4. build_report() — gera relatório em 4 seções
    5. apply() — NUNCA chamado sem aprovação explícita

    Args:
        project_root: Raiz do projeto (default: git root)
        dry_run: Se True, apenas gera relatório, não aplica

    Returns:
        RememberReport com promoções, cleanup, ambiguous e no_action
    """
    # Passo 1: Lê todas as camadas
    entries, layers = gather_layers(project_root)

    # Passo 2: Classifica entradas
    classifier = MemoryClassifier()
    classifications = {}

    for entry in entries:
        classification = classifier.classify(entry, entries)
        classifications[entry.source] = classification

    # Passo 3: Encontra cleanup
    cleanup = find_cleanup(entries, classifications)

    # Passo 4: Separa por categoria
    report = RememberReport()

    for entry in entries:
        classification = classifications.get(entry.source)

        if not classification:
            report.no_action.append(entry)
            continue

        if classification.is_duplicate:
            report.cleanup.append((entry, "Duplicata"))
            continue

        if classification.conflicts:
            report.ambiguous.append((entry, "; ".join(classification.conflicts)))
            continue

        # Verifica se precisa promoção
        if classification.proposed_dest != 'stay':
            report.promotions.append((entry, classification))
        else:
            report.no_action.append(entry)

    # Adiciona cleanup encontrado
    for entry, reason in cleanup:
        if (entry, reason) not in report.cleanup:
            report.cleanup.append((entry, reason))

    return report


def generate_remember_report(report: RememberReport) -> str:
    """
    Gera relatório legível do remember.

    Formato em 4 seções:
    1. Promotions (destino + racional)
    2. Cleanup (duplicatas, conflitos, desatualizadas)
    3. Ambiguous (precisa input do usuário)
    4. No action

    Args:
        report: RememberReport para formatar

    Returns:
        Relatório em markdown
    """
    lines = [
        "# Remember Report — Revisão de Memórias",
        "",
        "Este relatório propõe mudanças nas camadas de memória.",
        "Nenhuma modificação será feita sem aprovação explícita.",
        "",
    ]

    # Seção 1: Promotions
    lines.append("## 1. Promoções Propostas")
    lines.append("")

    if report.promotions:
        for entry, classification in report.promotions:
            lines.append(f"### {entry.name or entry.source.name}")
            lines.append("")
            lines.append(f"- **Tipo:** {classification.proposed_type}")
            lines.append(f"- **Escopo:** {classification.proposed_scope}")
            lines.append(f"- **Destino:** {classification.proposed_dest}")
            lines.append(f"- **Razão:** {classification.reason}")
            lines.append(f"- **Origem:** {entry.source}")
            lines.append("")
    else:
        lines.append("Nenhuma promoção proposta.")
        lines.append("")

    # Seção 2: Cleanup
    lines.append("## 2. Cleanup (Duplicatas/Conflitos)")
    lines.append("")

    if report.cleanup:
        for entry, reason in report.cleanup:
            name = entry.name or entry.source.name
            lines.append(f"- **{name}** ({entry.source})")
            lines.append(f"  - Razão: {reason}")
            lines.append("")
    else:
        lines.append("Nenhum cleanup necessário.")
        lines.append("")

    # Seção 3: Ambiguous
    lines.append("## 3. Ambíguos (Requer Input)")
    lines.append("")

    if report.ambiguous:
        for entry, conflicts in report.ambiguous:
            name = entry.name or entry.source.name
            lines.append(f"- **{name}** ({entry.source})")
            lines.append(f"  - Conflitos: {conflicts}")
            lines.append("")
    else:
        lines.append("Nenhum conflito ambíguo.")
        lines.append("")

    # Seção 4: No action
    lines.append("## 4. Sem Ação")
    lines.append("")

    if report.no_action:
        lines.append(f"{len(report.no_action)} entradas não requerem ação.")
        lines.append("")
    else:
        lines.append("Todas as entradas requerem ação.")
        lines.append("")

    return "\n".join(lines)

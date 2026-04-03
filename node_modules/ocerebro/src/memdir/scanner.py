"""Scan de arquivos de memória do Claude Code.

Replica exatamente:
- src/memdir/memoryScan.ts — scanMemoryFiles() + formatMemoryManifest()
- Lê apenas primeiras 30 linhas (frontmatter)
- Exclui MEMORY.md do scan
- Sort por mtime DESC (newest-first)
- Cap em 200 arquivos
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

from src.core.paths import MAX_MEMORY_FILES, FRONTMATTER_MAX_LINES, MEMORY_INDEX_FILENAME


MemoryType = Literal['user', 'feedback', 'project', 'reference']


@dataclass
class MemoryHeader:
    """Cabeçalho de arquivo de memória.

    Replica MemoryHeader do Claude Code (memoryScan.ts).

    Attributes:
        filename: Path relativo dentro do memory_dir
        file_path: Path absoluto
        mtime_ms: Timestamp em ms (para sort newest-first)
        description: Descrição do frontmatter
        type: Tipo de memória (user/feedback/project/reference)
        name: Nome da memória (do frontmatter)
    """
    filename: str
    file_path: Path
    mtime_ms: float
    description: Optional[str] = None
    type: Optional[MemoryType] = None
    name: Optional[str] = None

    def to_manifest_line(self) -> str:
        """Formata como linha do manifesto MEMORY.md.

        Replica formatMemoryManifest() do Claude Code.

        Formato: "- [type] filename (ISO timestamp): description"
        Exemplo: "- [feedback] feedback_testing.md (2026-03-15T10:00:00Z): não usar mocks"
        """
        # Converte mtime_ms para datetime
        mtime_sec = self.mtime_ms / 1000
        dt = datetime.fromtimestamp(mtime_sec, tz=timezone.utc)
        iso_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Constrói linha
        parts = ["-"]

        # Adiciona type se existir
        if self.type:
            parts.append(f"[{self.type}]")

        # Adiciona filename
        parts.append(self.filename)

        # Adiciona timestamp
        parts.append(f"({iso_str}):")

        # Adiciona descrição se existir
        if self.description:
            parts.append(self.description)

        return " ".join(parts)


def parse_frontmatter(text: str) -> dict:
    """
    Parse frontmatter YAML de arquivo de memória.

    Frontmatter esperado:
    ```
    ---
    name: nome da memória
    description: uma linha — usada para decidir relevância futura
    type: user | feedback | project | reference
    ---
    ```

    Args:
        text: Conteúdo do arquivo (pelo menos primeiras 30 linhas)

    Returns:
        Dict com name, description, type extraídos
    """
    result = {
        "name": None,
        "description": None,
        "type": None
    }

    # Verifica se tem frontmatter
    if not text.strip().startswith("---"):
        return result

    # Encontra fim do frontmatter
    lines = text.split("\n")
    if len(lines) < 2:
        return result

    # Procura --- de fechamento
    end_idx = -1
    for i in range(1, min(len(lines), 15)):  # Frontmatter normalmente < 15 linhas
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        return result

    # Parse linhas do frontmatter
    for i in range(1, end_idx):
        line = lines[i].strip()
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "name":
                result["name"] = value
            elif key == "description":
                result["description"] = value
            elif key == "type":
                if value in ['user', 'feedback', 'project', 'reference']:
                    result["type"] = value

    return result


def scan_memory_files(memory_dir: Path) -> List[MemoryHeader]:
    """
    Scan de arquivos de memória.

    Replica scanMemoryFiles() do Claude Code (memoryScan.ts).

    - readdir recursivo
    - filtra *.md excluindo MEMORY.md
    - lê só as primeiras 30 linhas (frontmatter apenas)
    - parseia frontmatter: name, description, type
    - sort por mtime DESC (newest-first)
    - cap em MAX_MEMORY_FILES=200
    - retorna [] em caso de erro (nunca levanta exceção)

    Args:
        memory_dir: Diretório de memória para scan

    Returns:
        Lista de MemoryHeader ordenada por mtime DESC
    """
    if not memory_dir.exists():
        return []

    try:
        # Coleta todos os arquivos .md (recursivo)
        md_files = list(memory_dir.rglob("*.md"))
    except Exception:
        return []

    headers = []

    for file_path in md_files:
        try:
            # Exclui MEMORY.md — regra explícita no código do Claude Code
            if file_path.name == MEMORY_INDEX_FILENAME:
                continue

            # Pega mtime em milissegundos
            stat = file_path.stat()
            mtime_ms = stat.st_mtime * 1000

            # Lê apenas primeiras 30 linhas (FRONTMATTER_MAX_LINES)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= FRONTMATTER_MAX_LINES:
                            break
                        lines.append(line)
                    content = "".join(lines)
            except Exception:
                content = ""

            # Parse frontmatter
            frontmatter = parse_frontmatter(content)

            # Cria header
            rel_path = file_path.relative_to(memory_dir)
            header = MemoryHeader(
                filename=str(rel_path),
                file_path=file_path,
                mtime_ms=mtime_ms,
                description=frontmatter.get("description"),
                type=frontmatter.get("type"),
                name=frontmatter.get("name")
            )
            headers.append(header)

        except Exception:
            # Silenciosamente ignora arquivos com erro
            continue

    # Sort por mtime DESC (newest-first)
    headers.sort(key=lambda h: h.mtime_ms, reverse=True)

    # Cap em MAX_MEMORY_FILES
    return headers[:MAX_MEMORY_FILES]


def format_memory_manifest(memories: List[MemoryHeader]) -> str:
    """
    Formata lista de memórias como manifesto para injeção no prompt.

    Replica formatMemoryManifest() do Claude Code (memoryScan.ts).

    Formato:
    ```
    Existing memories:
    - [feedback] feedback_testing.md (2026-03-15T10:00:00Z): não usar mocks
    - [project] project_deadline.md (2026-03-14T08:00:00Z): release até sexta
    ```

    Args:
        memories: Lista de MemoryHeader

    Returns:
        String formatada para injeção no prompt
    """
    if not memories:
        return "Existing memories: (none)"

    lines = ["Existing memories:"]

    for mem in memories:
        lines.append(mem.to_manifest_line())

    return "\n".join(lines)


def get_existing_memories_summary(memory_dir: Path) -> str:
    """
    Scan + format em uma única função utilitária.

    Args:
        memory_dir: Diretório de memória para scan

    Returns:
        Resumo formatado para injeção no prompt
    """
    memories = scan_memory_files(memory_dir)
    return format_memory_manifest(memories)

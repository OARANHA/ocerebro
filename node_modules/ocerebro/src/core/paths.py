"""Resolução de paths do sistema de memória do Claude Code.

Replica exatamente a lógica do Claude Code:
- src/memdir/paths.ts — sanitizePath(), getAutoMemPath(), getAutoMemDailyLogPath()
- CLAUDE_COWORK_MEMORY_PATH_OVERRIDE (env var) tem prioridade
- autoMemoryDirectory em settings.json como fallback
- ~/.claude/projects/<sanitized-git-root>/memory/ como default
"""

import os
import re
from datetime import date
from pathlib import Path
from typing import Optional


def sanitize_path(absolute_path: str) -> str:
    """
    Replica sanitizePath() do Claude Code (src/memdir/paths.ts).

    Converte separadores de path em '-' para formar o nome do diretório.
    Remove caracteres especiais e normaliza para ASCII seguro.

    Exemplo:
        /home/user/projects/ocerebro → -home-user-projects-ocerebro
        C:\\Users\\dev\\my-project → -c--users-dev-my-project

    Args:
        absolute_path: Path absoluto para sanitizar

    Returns:
        String sanitizada para uso como nome de diretório
    """
    import re

    # Normaliza separadores Windows para Unix
    normalized = absolute_path.replace("\\", "/")

    # Normaliza drive letter para lowercase (E:/ → e:/)
    if len(normalized) >= 2 and normalized[1] == ":":
        normalized = normalized[0].lower() + normalized[1:]

    # Substitui / e : por -
    sanitized = re.sub(r'[/\\:]', '-', normalized)

    # Remove caracteres especiais
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', sanitized)

    # Remove múltiplos '-' consecutivos
    sanitized = re.sub(r'-+', '-', sanitized)

    # Garante início com -
    if not sanitized.startswith('-'):
        sanitized = '-' + sanitized

    return sanitized


def get_git_root(project_root: Path = None) -> Path:
    """
    Encontra a raiz do repositório git.

    Args:
        project_root: Diretório inicial para busca (default: cwd)

    Returns:
        Path da raiz do git

    Raises:
        FileNotFoundError: Se não estiver em repositório git
    """
    if project_root is None:
        project_root = Path.cwd()

    current = project_root.resolve()

    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    raise FileNotFoundError(
        f"Não foi possível encontrar raiz do git a partir de {project_root}"
    )


def get_claude_home() -> Path:
    """
    Retorna o diretório base do Claude (~/.claude).

    Priority:
    1. CLAUDE_HOME env var
    2. ~/.claude (default)

    Returns:
        Path do diretório Claude home
    """
    claude_home = os.environ.get("CLAUDE_HOME")
    if claude_home:
        return Path(claude_home).resolve()

    # Default: ~/.claude
    home = Path.home()
    return home / ".claude"


def get_auto_mem_path(project_root: Path = None) -> Path:
    """
    Resolve o path do diretório de memória automática.

    Priority:
    1. CLAUDE_COWORK_MEMORY_PATH_OVERRIDE (env var)
    2. autoMemoryDirectory em ~/.claude/settings.json
    3. ~/.claude/projects/<sanitized-git-root>/memory/

    Replica:
    - getAutoMemPath() do Claude Code
    - Priority: env override > settings.json > default

    Args:
        project_root: Diretório do projeto (default: git root do cwd)

    Returns:
        Path do diretório de memória
    """
    # Priority 1: Environment variable override
    override = os.environ.get("CLAUDE_COWORK_MEMORY_PATH_OVERRIDE")
    if override:
        mem_path = Path(override).resolve()
        mem_path.mkdir(parents=True, exist_ok=True)
        return mem_path

    # Priority 2: Check settings.json (TODO: implementar quando settings.json parser existir)
    # settings_path = get_claude_home() / "settings.json"
    # if settings_path.exists():
    #     settings = json.loads(settings_path.read_text())
    #     if "autoMemoryDirectory" in settings:
    #         return Path(settings["autoMemoryDirectory"]).resolve()

    # Priority 3: Default path based on git root
    try:
        git_root = get_git_root(project_root)
        sanitized = sanitize_path(str(git_root))
    except FileNotFoundError:
        # Fallback: usa cwd se não tiver git
        sanitized = sanitize_path(str(Path.cwd().resolve()))

    claude_home = get_claude_home()
    mem_dir = claude_home / "projects" / sanitized / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)

    return mem_dir


def get_memory_index(memory_dir: Path = None) -> Path:
    """
    Retorna o path do arquivo MEMORY.md (índice de memórias).

    Replica: getMemoryIndexPath() do Claude Code

    Args:
        memory_dir: Diretório de memória (default: get_auto_mem_path())

    Returns:
        Path para MEMORY.md
    """
    if memory_dir is None:
        memory_dir = get_auto_mem_path()

    return memory_dir / "MEMORY.md"


def get_daily_log_path(memory_dir: Path = None, date_: date = None) -> Path:
    """
    Retorna o path do log diário (KAIROS).

    Replica: getAutoMemDailyLogPath() do Claude Code
    Path: memory_dir / logs / YYYY / MM / YYYY-MM-DD.md

    Args:
        memory_dir: Diretório de memória (default: get_auto_mem_path())
        date_: Data do log (default: hoje)

    Returns:
        Path para o arquivo de log diário
    """
    if memory_dir is None:
        memory_dir = get_auto_mem_path()

    if date_ is None:
        date_ = date.today()

    # Estrutura: logs/YYYY/MM/YYYY-MM-DD.md
    year = date_.year
    month = date_.month
    day_file = f"{date_.isoformat()}.md"

    log_dir = memory_dir / "logs" / str(year) / f"{month:02d}"
    log_dir.mkdir(parents=True, exist_ok=True)

    return log_dir / day_file


def get_user_memory_path(memory_dir: Path = None) -> Path:
    """
    Retorna o path preferencial para CLAUDE.local.md (memória do usuário).

    Args:
        memory_dir: Diretório de memória (default: get_auto_mem_path())

    Returns:
        Path para CLAUDE.local.md
    """
    if memory_dir is None:
        memory_dir = get_auto_mem_path()

    # Nota: CLAUDE.local.md fica na raiz do projeto, não em memory_dir
    # Este método é um placeholder para futura integração
    try:
        git_root = get_git_root()
        return git_root / "CLAUDE.local.md"
    except FileNotFoundError:
        # Fallback: memory_dir
        return memory_dir / "CLAUDE.local.md"


def get_project_memory_path(memory_dir: Path = None) -> Path:
    """
    Retorna o path preferencial para CLAUDE.md (memória do projeto).

    Args:
        memory_dir: Diretório de memória (default: get_auto_mem_path())

    Returns:
        Path para CLAUDE.md
    """
    if memory_dir is None:
        memory_dir = get_auto_mem_path()

    # Nota: CLAUDE.md fica na raiz do projeto, não em memory_dir
    # Este método é um placeholder para futura integração
    try:
        git_root = get_git_root()
        return git_root / "CLAUDE.md"
    except FileNotFoundError:
        # Fallback: memory_dir
        return memory_dir / "CLAUDE.md"


# Constants - replica de memoryScan.ts
MAX_MEMORY_FILES = 200
FRONTMATTER_MAX_LINES = 30
MEMORY_INDEX_FILENAME = "MEMORY.md"
MEMORY_INDEX_MAX_LINES = 200
MEMORY_INDEX_MAX_SIZE_KB = 25

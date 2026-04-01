"""Testes para src/core/paths.py - Resolução de paths do sistema de memória."""

import os
import pytest
from pathlib import Path
from src.core.paths import (
    sanitize_path,
    get_git_root,
    get_claude_home,
    get_auto_mem_path,
    get_memory_index,
    get_daily_log_path,
    get_user_memory_path,
    get_project_memory_path,
    MAX_MEMORY_FILES,
    FRONTMATTER_MAX_LINES,
    MEMORY_INDEX_FILENAME,
    MEMORY_INDEX_MAX_LINES,
)


class TestSanitizePath:
    """Testes para sanitize_path()"""

    def test_unix_path(self):
        """Testa path Unix"""
        result = sanitize_path("/home/user/projects/ocerebro")
        assert result == "-home-user-projects-ocerebro"

    def test_windows_path(self):
        """Testa path Windows"""
        result = sanitize_path("C:\\Users\\dev\\my-project")
        assert result.startswith("-")
        assert "Users" in result
        assert "dev" in result
        assert "my-project" in result

    def test_removes_special_chars(self):
        """Testa remoção de caracteres especiais"""
        result = sanitize_path("/home/user/my@project#test")
        assert "@" not in result
        assert "#" not in result

    def test_consecutive_separators(self):
        """Testa múltiplos separadores consecutivos"""
        result = sanitize_path("/home//user///projects")
        assert "--" not in result

    def test_starts_with_dash_for_absolute(self):
        """Testa que path absoluto começa com dash"""
        result = sanitize_path("/absolute/path")
        assert result.startswith("-")


class TestGetGitRoot:
    """Testes para get_git_root()"""

    def test_finds_git_root(self, tmp_path):
        """Testa que encontra raiz do git"""
        # Cria estrutura com .git
        git_root = tmp_path / "project"
        git_root.mkdir()
        (git_root / ".git").mkdir()

        result = get_git_root(git_root)
        assert result == git_root

    def test_raises_if_no_git(self, tmp_path):
        """Testa que levanta erro se não tem git"""
        with pytest.raises(FileNotFoundError):
            get_git_root(tmp_path)


class TestGetClaudeHome:
    """Testes para get_claude_home()"""

    def test_default_home(self, monkeypatch):
        """Testa home padrão"""
        monkeypatch.delenv("CLAUDE_HOME", raising=False)
        result = get_claude_home()
        assert result.name == ".claude"
        assert result.parent == Path.home()

    def test_env_override(self, monkeypatch, tmp_path):
        """Testa override via env var"""
        custom_home = tmp_path / "custom_claude"
        custom_home.mkdir()
        monkeypatch.setenv("CLAUDE_HOME", str(custom_home))

        result = get_claude_home()
        assert result == custom_home


class TestGetAutoMemPath:
    """Testes para get_auto_mem_path()"""

    def test_env_override(self, monkeypatch, tmp_path):
        """Testa override via CLAUDE_COWORK_MEMORY_PATH_OVERRIDE"""
        override_path = tmp_path / "override" / "memory"
        override_path.mkdir(parents=True)
        monkeypatch.setenv("CLAUDE_COWORK_MEMORY_PATH_OVERRIDE", str(override_path))

        result = get_auto_mem_path()
        assert result == override_path

    def test_creates_directory(self, tmp_path):
        """Testa que cria diretório se não existir"""
        # Simula fallback para path padrão
        non_existent = tmp_path / "non_existent" / "memory"

        # Nota: Este teste depende de ter git ou não
        # Em ambiente de teste, geralmente não tem git
        result = get_auto_mem_path(tmp_path)
        assert result.exists()


class TestConstants:
    """Testes para constantes"""

    def test_max_memory_files(self):
        """Testa constante MAX_MEMORY_FILES"""
        assert MAX_MEMORY_FILES == 200

    def test_frontmatter_max_lines(self):
        """Testa constante FRONTMATTER_MAX_LINES"""
        assert FRONTMATTER_MAX_LINES == 30

    def test_memory_index_filename(self):
        """Testa constante MEMORY_INDEX_FILENAME"""
        assert MEMORY_INDEX_FILENAME == "MEMORY.md"

    def test_memory_index_max_lines(self):
        """Testa constante MEMORY_INDEX_MAX_LINES"""
        assert MEMORY_INDEX_MAX_LINES == 200


class TestGetMemoryIndex:
    """Testes para get_memory_index()"""

    def test_returns_memory_md(self, tmp_path):
        """Testa que retorna path para MEMORY.md"""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()

        result = get_memory_index(memory_dir)
        assert result.name == "MEMORY.md"
        assert result.parent == memory_dir


class TestGetDailyLogPath:
    """Testes para get_daily_log_path()"""

    def test_structured_path(self, tmp_path):
        """Testa estrutura logs/YYYY/MM/YYYY-MM-DD.md"""
        from datetime import date

        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()

        test_date = date(2026, 3, 15)
        result = get_daily_log_path(memory_dir, test_date)

        assert result.name == "2026-03-15.md"
        assert result.parent.name == "03"  # MM
        assert result.parent.parent.name == "2026"  # YYYY

    def test_creates_parent_dirs(self, tmp_path):
        """Testa que cria diretórios pai"""
        from datetime import date

        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()

        test_date = date(2026, 3, 15)
        result = get_daily_log_path(memory_dir, test_date)

        assert result.parent.exists()
        assert result.parent.parent.exists()


class TestGetUserMemoryPath:
    """Testes para get_user_memory_path()"""

    def test_returns_claude_local_md(self, tmp_path):
        """Testa que retorna path para CLAUDE.local.md"""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()

        # Sem git, usa fallback para memory_dir
        result = get_user_memory_path(memory_dir)
        assert result.name == "CLAUDE.local.md"


class TestGetProjectMemoryPath:
    """Testes para get_project_memory_path()"""

    def test_returns_claude_md(self, tmp_path):
        """Testa que retorna path para CLAUDE.md"""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()

        # Sem git, usa fallback para memory_dir
        result = get_project_memory_path(memory_dir)
        assert result.name == "CLAUDE.md"

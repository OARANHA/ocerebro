"""Testes para MarkdownStorage"""

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

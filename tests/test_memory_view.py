"""Testes para MemoryView"""

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

    def test_write_to_file(self, tmp_cerebro_dir):
        """Escreve MEMORY.md em arquivo"""
        official = MarkdownStorage(tmp_cerebro_dir / "official")
        working = YAMLStorage(tmp_cerebro_dir / "working")
        view = MemoryView(tmp_cerebro_dir, official, working)

        memory_file = view.write_to_file("test-project")

        assert memory_file.exists()
        assert memory_file.name == "MEMORY.md"

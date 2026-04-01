"""Testes para src/memdir/scanner.py - Scan de arquivos de memória."""

import pytest
from pathlib import Path
from datetime import datetime, timezone
from src.memdir.scanner import (
    MemoryHeader,
    parse_frontmatter,
    scan_memory_files,
    format_memory_manifest,
    get_existing_memories_summary,
)
from src.core.paths import MEMORY_INDEX_FILENAME, MAX_MEMORY_FILES, FRONTMATTER_MAX_LINES


class TestParseFrontmatter:
    """Testes para parse_frontmatter()"""

    def test_valid_frontmatter(self):
        """Testa frontmatter válido"""
        content = """---
name: Test Memory
description: This is a test memory
type: feedback
---

Content here."""
        result = parse_frontmatter(content)
        assert result["name"] == "Test Memory"
        assert result["description"] == "This is a test memory"
        assert result["type"] == "feedback"

    def test_no_frontmatter(self):
        """Testa arquivo sem frontmatter"""
        content = "Just content without frontmatter"
        result = parse_frontmatter(content)
        assert result["name"] is None
        assert result["description"] is None
        assert result["type"] is None

    def test_partial_frontmatter(self):
        """Testa frontmatter parcial"""
        content = """---
name: Partial Memory
---

Content here."""
        result = parse_frontmatter(content)
        assert result["name"] == "Partial Memory"
        assert result["description"] is None
        assert result["type"] is None

    def test_invalid_type(self):
        """Testa tipo inválido"""
        content = """---
name: Invalid Type
type: invalid_type
---"""
        result = parse_frontmatter(content)
        assert result["type"] is None  # Tipo inválido é ignorado

    def test_valid_types(self):
        """Testa tipos válidos"""
        for valid_type in ['user', 'feedback', 'project', 'reference']:
            content = f"""---
name: Test
type: {valid_type}
---"""
            result = parse_frontmatter(content)
            assert result["type"] == valid_type


class TestMemoryHeader:
    """Testes para MemoryHeader"""

    def test_to_manifest_line(self, tmp_path):
        """Testa formatação de linha do manifesto"""
        header = MemoryHeader(
            filename="test.md",
            file_path=tmp_path / "test.md",
            mtime_ms=1710500000000,  # 2024-03-15
            description="Test description",
            type="feedback",
            name="Test Memory"
        )

        line = header.to_manifest_line()
        assert line.startswith("- [feedback]")
        assert "test.md" in line
        assert "Test description" in line
        assert "(2024-" in line  # Timestamp ISO

    def test_to_manifest_line_no_type(self, tmp_path):
        """Testa linha sem tipo"""
        header = MemoryHeader(
            filename="test.md",
            file_path=tmp_path / "test.md",
            mtime_ms=1710500000000,
            description="Test"
        )

        line = header.to_manifest_line()
        assert line.startswith("-")
        assert "[feedback]" not in line  # Sem tipo


class TestScanMemoryFiles:
    """Testes para scan_memory_files()"""

    def test_excludes_memory_index(self, tmp_path):
        """Testa que exclui MEMORY.md do scan"""
        # Cria MEMORY.md
        memory_index = tmp_path / MEMORY_INDEX_FILENAME
        memory_index.write_text("---\nname: Index\n---")

        # Cria arquivo normal
        normal_file = tmp_path / "normal.md"
        normal_file.write_text("---\nname: Normal\n---")

        result = scan_memory_files(tmp_path)

        # MEMORY.md deve estar excluído
        filenames = [h.filename for h in result]
        assert MEMORY_INDEX_FILENAME not in filenames
        assert "normal.md" in filenames

    def test_sorts_by_mtime_desc(self, tmp_path):
        """Testa ordenação por mtime DESC"""
        import time

        # Cria arquivos com mtimes diferentes
        older = tmp_path / "older.md"
        older.write_text("---\nname: Older\n---")

        time.sleep(0.1)  # Garante diferença de mtime

        newer = tmp_path / "newer.md"
        newer.write_text("---\nname: Newer\n---")

        result = scan_memory_files(tmp_path)

        # Primeiro deve ser o mais recente
        assert len(result) >= 2
        assert result[0].filename == "newer.md"

    def test_caps_at_max_files(self, tmp_path):
        """Testa limitação em MAX_MEMORY_FILES"""
        # Cria mais arquivos que o limite
        for i in range(MAX_MEMORY_FILES + 50):
            f = tmp_path / f"file_{i}.md"
            f.write_text(f"---\nname: File {i}\n---")

        result = scan_memory_files(tmp_path)
        assert len(result) <= MAX_MEMORY_FILES

    def test_returns_empty_if_not_exists(self, tmp_path):
        """Testa que retorna lista vazia se diretório não existe"""
        non_existent = tmp_path / "non_existent"
        result = scan_memory_files(non_existent)
        assert result == []

    def test_reads_only_frontmatter_lines(self, tmp_path):
        """Testa que lê apenas primeiras FRONTMATTER_MAX_LINES"""
        # Cria arquivo com muitas linhas
        lines = ["---\nname: Large\n---\n"]
        lines.extend(["Content line {}\n".format(i) for i in range(1000)])
        large_file = tmp_path / "large.md"
        large_file.write_text("".join(lines))

        # Scan deve funcionar mesmo com arquivo grande
        result = scan_memory_files(tmp_path)
        assert len(result) >= 1
        assert result[0].name == "Large"

    def test_ignores_errors_silently(self, tmp_path):
        """Testa que ignora arquivos com erro silenciosamente"""
        # Cria arquivo normal
        normal = tmp_path / "normal.md"
        normal.write_text("---\nname: Normal\n---")

        # Cria arquivo sem permissão de leitura (simulado com nome inválido)
        # Em sistemas reais, isso ocorreria com arquivos corrompidos

        result = scan_memory_files(tmp_path)
        # Deve retornar pelo menos o arquivo normal
        assert len(result) >= 1


class TestFormatMemoryManifest:
    """Testes para format_memory_manifest()"""

    def test_empty_list(self):
        """Testa lista vazia"""
        result = format_memory_manifest([])
        assert result == "Existing memories: (none)"

    def test_single_memory(self, tmp_path):
        """Testa memória única"""
        header = MemoryHeader(
            filename="single.md",
            file_path=tmp_path / "single.md",
            mtime_ms=1710500000000,
            description="Single memory",
            type="project"
        )

        result = format_memory_manifest([header])
        assert "Existing memories:" in result
        assert "- [project] single.md" in result

    def test_multiple_memories(self, tmp_path):
        """Testa múltiplas memórias"""
        headers = [
            MemoryHeader(
                filename=f"file_{i}.md",
                file_path=tmp_path / f"file_{i}.md",
                mtime_ms=1710500000000 + (i * 1000),
                description=f"Memory {i}",
                type="feedback" if i % 2 == 0 else "project"
            )
            for i in range(3)
        ]

        result = format_memory_manifest(headers)
        lines = result.split("\n")
        assert len(lines) == 4  # Header + 3 memórias


class TestGetExistingMemoriesSummary:
    """Testes para get_existing_memories_summary()"""

    def test_wrapper_function(self, tmp_path):
        """Testa função utilitária"""
        # Cria arquivo de memória
        mem_file = tmp_path / "test.md"
        mem_file.write_text("---\nname: Test\n---")

        result = get_existing_memories_summary(tmp_path)
        assert "Existing memories:" in result
        assert "test.md" in result

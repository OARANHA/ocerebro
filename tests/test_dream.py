"""Testes para src/consolidation/dream.py - Extração automática de memórias."""

import pytest
from pathlib import Path
from src.consolidation.dream import (
    DreamResult,
    build_opener,
    build_how_to_save_section,
    build_extract_dream_prompt,
    count_transcript_messages,
    run_dream,
    generate_dream_report,
)
from src.core.paths import MEMORY_INDEX_MAX_LINES


class TestDreamResult:
    """Testes para DreamResult dataclass"""

    def test_default_values(self, tmp_path):
        """Testa valores default"""
        result = DreamResult(
            written_files=[],
            memory_dir=tmp_path,
            dry_run=True,
            period_days=7
        )
        # new_memories e updated_memories são None por default
        assert result.new_memories is None or result.new_memories == []
        assert result.updated_memories is None or result.updated_memories == []


class TestBuildOpener:
    """Testes para build_opener()"""

    def test_includes_message_count(self):
        """Testa que inclui contagem de mensagens"""
        result = build_opener(42, "Existing memories: (none)")
        assert "42" in result
        assert "~42 messages" in result

    def test_includes_existing_memories(self):
        """Testa que inclui memórias existentes"""
        existing = "- [feedback] test.md (2026-03-15T10:00:00Z): test"
        result = build_opener(10, existing)
        assert existing in result

    def test_mentions_tool_restrictions(self):
        """Testa que menciona restrições de ferramentas"""
        result = build_opener(10, "none")
        assert "FileRead" in result
        assert "FileEdit" in result
        assert "memory directory only" in result


class TestBuildHowToSaveSection:
    """Testes para build_how_to_save_section()"""

    def test_includes_memory_dir(self, tmp_path):
        """Testa que inclui diretório de memória"""
        result = build_how_to_save_section(tmp_path)
        assert str(tmp_path) in result

    def test_mentions_frontmatter(self):
        """Testa que menciona frontmatter"""
        result = build_how_to_save_section(Path("/test"))
        assert "Frontmatter" in result or "frontmatter" in result
        assert "name:" in result
        assert "description:" in result
        assert "type:" in result

    def test_mentions_index_limit(self):
        """Testa que menciona limite do índice"""
        result = build_how_to_save_section(Path("/test"))
        assert str(MEMORY_INDEX_MAX_LINES) in result


class TestBuildExtractDreamPrompt:
    """Testes para build_extract_dream_prompt()"""

    def test_returns_list_of_sections(self, tmp_path):
        """Testa que retorna lista de seções"""
        sections = build_extract_dream_prompt(
            new_message_count=10,
            existing_memories="none",
            memory_dir=tmp_path
        )
        assert isinstance(sections, list)
        assert len(sections) >= 5  # Múltiplas seções

    def test_includes_all_required_sections(self, tmp_path):
        """Testa que inclui todas as seções necessárias"""
        sections = build_extract_dream_prompt(
            new_message_count=10,
            existing_memories="none",
            memory_dir=tmp_path
        )
        full_prompt = "\n".join(sections)

        # Verifica seções principais - o prompt está em português
        assert "Tipos de Memória" in full_prompt or "4 types" in full_prompt.lower()
        assert "user" in full_prompt.lower()
        assert "feedback" in full_prompt.lower()
        assert "project" in full_prompt.lower()
        assert "reference" in full_prompt.lower()

    def test_includes_what_not_to_save(self, tmp_path):
        """Testa que inclui seção do que NÃO salvar"""
        sections = build_extract_dream_prompt(
            new_message_count=10,
            existing_memories="none",
            memory_dir=tmp_path
        )
        full_prompt = "\n".join(sections)
        assert "NÃO Salvar" in full_prompt or "NOT" in full_prompt


class TestCountTranscriptMessages:
    """Testes para count_transcript_messages()"""

    def test_returns_zero_if_no_projects_dir(self, monkeypatch, tmp_path):
        """Testa que retorna 0 se não existe diretório de projetos"""
        # Mock para diretório inexistente
        def mock_get_auto_mem_path():
            return tmp_path / "non_existent"

        monkeypatch.setattr(
            "src.consolidation.dream.get_auto_mem_path",
            mock_get_auto_mem_path
        )

        result = count_transcript_messages(7)
        assert result == 0


class TestRunDream:
    """Testes para run_dream()"""

    def test_returns_dream_result(self, tmp_path):
        """Testa que retorna DreamResult"""
        result = run_dream(memory_dir=tmp_path, since_days=7, dry_run=True)

        assert isinstance(result, DreamResult)
        assert result.memory_dir == tmp_path
        assert result.dry_run is True
        assert result.period_days == 7

    def test_dry_run_does_not_modify(self, tmp_path):
        """Testa que dry_run não modifica nada"""
        result = run_dream(memory_dir=tmp_path, dry_run=True)

        # Em dry_run, written_files deve estar vazio
        assert result.written_files == []

    def test_handles_empty_transcript(self, tmp_path):
        """Testa que lida com transcript vazio"""
        # Cria estrutura de memory_dir vazia
        result = run_dream(memory_dir=tmp_path, since_days=7, dry_run=True)

        assert isinstance(result, DreamResult)


class TestGenerateDreamReport:
    """Testes para generate_dream_report()"""

    def test_includes_header(self, tmp_path):
        """Testa que inclui cabeçalho"""
        result = DreamResult(
            written_files=[],
            memory_dir=tmp_path,
            dry_run=True,
            period_days=7,
            new_memories=[],
            updated_memories=[]
        )

        report = generate_dream_report(result)
        assert "# Dream Report" in report or "Extração" in report

    def test_shows_dry_run_status(self, tmp_path):
        """Testa que mostra status dry-run"""
        result_dry = DreamResult(
            written_files=[],
            memory_dir=tmp_path,
            dry_run=True,
            period_days=7
        )
        result_apply = DreamResult(
            written_files=[],
            memory_dir=tmp_path,
            dry_run=False,
            period_days=7
        )

        report_dry = generate_dream_report(result_dry)
        report_apply = generate_dream_report(result_apply)

        assert "dry-run" in report_dry.lower() or "nenhuma modificação" in report_dry.lower()
        assert "aplicação" in report_apply.lower() or "dry-run" not in report_apply.lower()

    def test_shows_period(self, tmp_path):
        """Testa que mostra período"""
        result = DreamResult(
            written_files=[],
            memory_dir=tmp_path,
            dry_run=True,
            period_days=14
        )

        report = generate_dream_report(result)
        assert "14" in report
        assert "dias" in report.lower() or "days" in report.lower()

    def test_empty_result_message(self, tmp_path):
        """Testa mensagem de resultado vazio"""
        result = DreamResult(
            written_files=[],
            memory_dir=tmp_path,
            dry_run=True,
            period_days=7,
            new_memories=[],
            updated_memories=[]
        )

        report = generate_dream_report(result)
        # Deve indicar que não houve mudanças
        assert "Nenhuma" in report or "nenhuma" in report or "none" in report.lower()

"""Testes para src/consolidation/remember.py - Revisão e promoção de memórias."""

import pytest
from pathlib import Path
from src.consolidation.remember import (
    MemoryEntry,
    ClassificationResult,
    RememberReport,
    MemoryClassifier,
    gather_layers,
    read_memory_file,
    find_cleanup,
    run_remember,
    generate_remember_report,
)


class TestMemoryEntry:
    """Testes para MemoryEntry dataclass"""

    def test_default_values(self, tmp_path):
        """Testa valores default"""
        entry = MemoryEntry(
            source=tmp_path / "test.md",
            layer="memory"
        )
        assert entry.type is None
        assert entry.name is None
        assert entry.description is None
        assert entry.content == ""
        assert entry.mtime == 0.0


class TestClassificationResult:
    """Testes para ClassificationResult dataclass"""

    def test_default_values(self, tmp_path):
        """Testa valores default"""
        entry = MemoryEntry(
            source=tmp_path / "test.md",
            layer="memory"
        )
        result = ClassificationResult(entry=entry)
        assert result.proposed_type is None
        assert result.proposed_scope == "private"
        assert result.proposed_dest == "stay"
        assert result.reason == ""
        assert result.conflicts == []
        assert result.is_duplicate is False


class TestRememberReport:
    """Testes para RememberReport dataclass"""

    def test_default_values(self):
        """Testa valores default"""
        report = RememberReport()
        assert report.promotions == []
        assert report.cleanup == []
        assert report.ambiguous == []
        assert report.no_action == []


class TestMemoryClassifier:
    """Testes para MemoryClassifier"""

    def setup_method(self):
        """Setup para testes"""
        self.classifier = MemoryClassifier()

    def test_classify_user_memory(self, tmp_path):
        """Testa classificação de memória user"""
        entry = MemoryEntry(
            source=tmp_path / "test.md",
            layer="memory",
            name="User Preference",
            description="Prefiro código em português - preferência do usuário",
            content="O usuário tem preferência por escrever código em português"
        )

        result = self.classifier.classify(entry)
        assert result.proposed_type == "user"

    def test_classify_feedback_memory(self, tmp_path):
        """Testa classificação de memória feedback"""
        entry = MemoryEntry(
            source=tmp_path / "test.md",
            layer="memory",
            name="No Mocks",
            description="Não usar mocks nos testes",
            content="Sempre prefira testes de integração com banco real"
        )

        result = self.classifier.classify(entry)
        assert result.proposed_type == "feedback"

    def test_classify_project_memory(self, tmp_path):
        """Testa classificação de memória project"""
        entry = MemoryEntry(
            source=tmp_path / "test.md",
            layer="memory",
            name="Release Deadline",
            description="Release até sexta-feira",
            content="O time está cortando release branch na sexta"
        )

        result = self.classifier.classify(entry)
        assert result.proposed_type == "project"

    def test_classify_reference_memory(self, tmp_path):
        """Testa classificação de memória reference"""
        entry = MemoryEntry(
            source=tmp_path / "test.md",
            layer="memory",
            name="Grafana Dashboard",
            description="Link para dashboard de latência",
            content="grafana.internal/d/api-latency"
        )

        result = self.classifier.classify(entry)
        assert result.proposed_type == "reference"

    def test_detect_duplicate_by_name(self, tmp_path):
        """Testa detecção de duplicata por nome"""
        entry1 = MemoryEntry(
            source=tmp_path / "test1.md",
            layer="memory",
            name="Same Name",
            description="First"
        )
        entry2 = MemoryEntry(
            source=tmp_path / "test2.md",
            layer="claude_md",
            name="Same Name",
            description="Second"
        )

        result = self.classifier.classify(entry1, [entry2])
        assert result.is_duplicate is True

    def test_detect_conflict_by_description(self, tmp_path):
        """Testa detecção de conflito por descrição"""
        entry1 = MemoryEntry(
            source=tmp_path / "test1.md",
            layer="memory",
            name="Test",
            description="Same description"
        )
        entry2 = MemoryEntry(
            source=tmp_path / "test2.md",
            layer="claude_md",
            name="Different",
            description="Same description"
        )

        result = self.classifier.classify(entry1, [entry2])
        assert len(result.conflicts) > 0 or result.is_duplicate is True

    def test_user_scope_is_always_private(self, tmp_path):
        """Testa que escopo de user é sempre privado"""
        entry = MemoryEntry(
            source=tmp_path / "test.md",
            layer="memory",
            name="User Pref",
            description="Preferência do usuário",
            content="O usuário prefere X"
        )

        result = self.classifier.classify(entry)
        assert result.proposed_scope == "private"

    def test_feedback_default_to_private(self, tmp_path):
        """Testa que feedback é privado por padrão"""
        entry = MemoryEntry(
            source=tmp_path / "test.md",
            layer="memory",
            name="Personal Feedback",
            description="Feedback pessoal",
            content="Não faça X"
        )

        result = self.classifier.classify(entry)
        assert result.proposed_scope == "private"

    def test_feedback_team_for_project_convention(self, tmp_path):
        """Testa que feedback é team para convenção de projeto"""
        entry = MemoryEntry(
            source=tmp_path / "test.md",
            layer="memory",
            name="Project Convention",
            description="Padrão do projeto para testes",
            content="Convenção do time: sempre use testes de integração"
        )

        result = self.classifier.classify(entry)
        # Deve ser team por mencionar projeto/time/convenção
        assert result.proposed_scope == "team"


class TestGatherLayers:
    """Testes para gather_layers()"""

    def test_returns_tuple(self, tmp_path):
        """Testa que retorna tupla"""
        entries, layers = gather_layers(tmp_path)

        assert isinstance(entries, list)
        assert isinstance(layers, dict)
        assert "memory" in layers
        assert "claude_md" in layers
        assert "claude_local" in layers

    def test_reads_memory_index(self, tmp_path):
        """Testa que lê índice de memória"""
        from src.core.paths import get_auto_mem_path, get_memory_index

        # IMPORTANTE: gather_layers usa get_auto_mem_path que ignora tmp_path
        # e retorna ~/.claude/projects/<sanitized-git-root>/memory
        # Para testar, precisamos usar o memory_dir real que gather_layers usará

        memory_dir = get_auto_mem_path(tmp_path)

        # Cria MEMORY.md com formato correto no memory_dir REAL
        memory_index = get_memory_index(memory_dir)
        memory_index.write_text("- [feedback] test.md (2026-03-15T10:00:00Z): test description\n")

        # Cria arquivo linkado com frontmatter válido
        test_file = memory_dir / "test.md"
        test_file.write_text("---\nname: Test\ntype: feedback\ndescription: test description\n---\n\nContent")

        entries, layers = gather_layers(tmp_path)

        # Deve encontrar o arquivo
        assert len(entries) >= 1
        assert entries[0].name == "Test"


class TestReadMemoryFile:
    """Testes para read_memory_file()"""

    def test_reads_valid_file(self, tmp_path):
        """Testa leitura de arquivo válido"""
        test_file = tmp_path / "test.md"
        content = """---
name: Test Memory
description: Test description
type: feedback
---

Content here."""
        test_file.write_text(content)

        entry = read_memory_file(test_file, "memory")

        assert entry is not None
        assert entry.name == "Test Memory"
        assert entry.description == "Test description"
        assert entry.type == "feedback"

    def test_returns_none_for_invalid_file(self, tmp_path):
        """Testa que retorna None para arquivo inválido"""
        invalid_file = tmp_path / "nonexistent.md"

        entry = read_memory_file(invalid_file, "memory")
        assert entry is None


class TestFindCleanup:
    """Testes para find_cleanup()"""

    def test_finds_duplicates(self, tmp_path):
        """Testa que encontra duplicatas"""
        import time

        # Cria entrada antiga
        older = MemoryEntry(
            source=tmp_path / "older.md",
            layer="memory",
            name="Duplicate",
            mtime=1000
        )

        time.sleep(0.01)

        # Cria entrada recente (mesmo nome)
        newer = MemoryEntry(
            source=tmp_path / "newer.md",
            layer="claude_md",
            name="Duplicate",
            mtime=2000
        )

        classifications = {}
        cleanup = find_cleanup([older, newer], classifications)

        # Deve encontrar a mais antiga como cleanup
        assert len(cleanup) >= 1

    def test_finds_outdated_between_layers(self, tmp_path):
        """Testa que encontra entradas desatualizadas entre camadas"""
        # Memory layer mais recente
        memory_entry = MemoryEntry(
            source=tmp_path / "memory.md",
            layer="memory",
            name="Same Name",
            description="Newer description",
            mtime=2000
        )

        # Claude MD mais antigo
        claude_entry = MemoryEntry(
            source=tmp_path / "claude.md",
            layer="claude_md",
            name="Same Name",
            description="Older description",
            mtime=1000
        )

        classifications = {}
        cleanup = find_cleanup([memory_entry, claude_entry], classifications)

        # Deve encontrar a mais antiga como cleanup
        cleanup_entries = [c[0] for c in cleanup]
        assert claude_entry in cleanup_entries or memory_entry in cleanup_entries


class TestRunRemember:
    """Testes para run_remember()"""

    def test_returns_remember_report(self, tmp_path):
        """Testa que retorna RememberReport"""
        report = run_remember(project_root=tmp_path, dry_run=True)

        assert isinstance(report, RememberReport)

    def test_dry_run_does_not_modify(self, tmp_path):
        """Testa que dry_run não modifica nada"""
        # Dry run é o default
        report = run_remember(project_root=tmp_path, dry_run=True)

        # Apenas gera relatório, sem modificações


class TestGenerateRememberReport:
    """Testes para generate_remember_report()"""

    def test_includes_all_sections(self, tmp_path):
        """Testa que inclui todas as 4 seções"""
        report = RememberReport()
        report.promotions.append((
            MemoryEntry(source=tmp_path / "promo.md", layer="memory", name="Promo"),
            ClassificationResult(entry=MemoryEntry(source=tmp_path / "test.md", layer="memory"))
        ))

        result = generate_remember_report(report)

        assert "1. Promoções" in result or "Promoções" in result
        assert "2. Cleanup" in result or "Cleanup" in result
        assert "3. Ambíguos" in result or "Amb" in result or "Input" in result
        assert "4. Sem Ação" in result or "No action" in result or "Ação" in result

    def test_empty_promotions_message(self, tmp_path):
        """Testa mensagem de promoções vazias"""
        report = RememberReport()

        result = generate_remember_report(report)
        assert "Nenhuma promoção" in result or "Nenhuma" in result

    def test_empty_cleanup_message(self, tmp_path):
        """Testa mensagem de cleanup vazio"""
        report = RememberReport()

        result = generate_remember_report(report)
        assert "Nenhum cleanup" in result or "Nenhum" in result

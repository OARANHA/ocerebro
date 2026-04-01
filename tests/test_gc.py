"""Testes para src/forgetting/gc.py - Garbage collection de memórias."""

import pytest
from pathlib import Path
import time
import os
from src.forgetting.gc import GarbageCollector
from src.core.paths import MAX_MEMORY_FILES


class TestGarbageCollector:
    """Testes para GarbageCollector"""

    def setup_method(self):
        """Setup para testes"""
        self.gc = GarbageCollector(Path("/tmp"))  # Path não usado nos novos métodos)

    def test_find_candidates_by_mtime(self, tmp_path):
        """Testa que encontra candidatas por mtime"""
        import os

        # Cria arquivo antigo
        old_file = tmp_path / "old.md"
        old_file.write_text("---\nname: Old\n---")

        # Define mtime antigo (10 dias atrás)
        old_time = time.time() - (10 * 24 * 60 * 60)
        os.utime(old_file, (old_time, old_time))

        # Cria arquivo recente
        new_file = tmp_path / "new.md"
        new_file.write_text("---\nname: New\n---")

        candidates = self.gc.find_candidates_for_archive(tmp_path, days_threshold=7)

        # Arquivo antigo deve ser candidato
        filenames = [c["filename"] for c in candidates]
        assert "old.md" in filenames

    def test_excludes_memory_index(self, tmp_path):
        """Testa que exclui MEMORY.md do scan"""
        memory_index = tmp_path / "MEMORY.md"
        memory_index.write_text("# Memory Index")

        # Define mtime antigo
        old_time = time.time() - (10 * 24 * 60 * 60)
        os.utime(memory_index, (old_time, old_time))

        candidates = self.gc.find_candidates_for_archive(tmp_path, days_threshold=7)

        filenames = [c["filename"] for c in candidates]
        assert "MEMORY.md" not in filenames

    def test_never_removes_user_type(self, tmp_path):
        """Testa que nunca remove memórias de tipo user"""
        import os

        user_file = tmp_path / "user_pref.md"
        user_file.write_text("---\nname: User Pref\ntype: user\n---")

        # Define mtime antigo
        old_time = time.time() - (30 * 24 * 60 * 60)
        os.utime(user_file, (old_time, old_time))

        candidates = self.gc.find_candidates_for_archive(tmp_path, days_threshold=7)

        # User type NÃO deve ser candidato
        filenames = [c["filename"] for c in candidates]
        assert "user_pref.md" not in filenames

    def test_never_removes_feedback_type(self, tmp_path):
        """Testa que nunca remove memórias de tipo feedback"""
        import os

        feedback_file = tmp_path / "feedback.md"
        feedback_file.write_text("---\nname: Feedback\ntype: feedback\n---")

        # Define mtime antigo
        old_time = time.time() - (30 * 24 * 60 * 60)
        os.utime(feedback_file, (old_time, old_time))

        candidates = self.gc.find_candidates_for_archive(tmp_path, days_threshold=7)

        # Feedback type NÃO deve ser candidato
        filenames = [c["filename"] for c in candidates]
        assert "feedback.md" not in filenames

    def test_allows_project_type_for_gc(self, tmp_path):
        """Testa que permite project type para GC"""
        import os

        project_file = tmp_path / "project.md"
        project_file.write_text("---\nname: Project\ntype: project\n---")

        # Define mtime antigo
        old_time = time.time() - (30 * 24 * 60 * 60)
        os.utime(project_file, (old_time, old_time))

        candidates = self.gc.find_candidates_for_archive(tmp_path, days_threshold=7)

        # Project type PODE ser candidato
        filenames = [c["filename"] for c in candidates]
        assert "project.md" in filenames

    def test_allows_reference_type_for_gc(self, tmp_path):
        """Testa que permite reference type para GC"""
        import os

        reference_file = tmp_path / "reference.md"
        reference_file.write_text("---\nname: Reference\ntype: reference\n---")

        # Define mtime antigo
        old_time = time.time() - (30 * 24 * 60 * 60)
        os.utime(reference_file, (old_time, old_time))

        candidates = self.gc.find_candidates_for_archive(tmp_path, days_threshold=7)

        # Reference type PODE ser candidato
        filenames = [c["filename"] for c in candidates]
        assert "reference.md" in filenames

    def test_returns_empty_if_dir_not_exists(self, tmp_path):
        """Testa que retorna lista vazia se diretório não existe"""
        non_existent = tmp_path / "non_existent"

        candidates = self.gc.find_candidates_for_archive(non_existent, days_threshold=7)
        assert candidates == []

    def test_ignores_files_with_errors(self, tmp_path):
        """Testa que ignora arquivos com erro silenciosamente"""
        # Cria arquivo normal
        normal_file = tmp_path / "normal.md"
        normal_file.write_text("---\nname: Normal\ntype: project\n---")

        # Define mtime antigo
        import os
        old_time = time.time() - (10 * 24 * 60 * 60)
        os.utime(normal_file, (old_time, old_time))

        # Scan não deve levantar exceção
        candidates = self.gc.find_candidates_for_archive(tmp_path, days_threshold=7)
        assert isinstance(candidates, list)

    def test_find_candidates_for_deletion(self, tmp_path):
        """Testa que encontra candidatas para deleção"""
        import os

        # Cria arquivo muito antigo
        very_old_file = tmp_path / "very_old.md"
        very_old_file.write_text("---\nname: Very Old\ntype: project\n---")

        # Define mtime muito antigo (60 dias)
        old_time = time.time() - (60 * 24 * 60 * 60)
        os.utime(very_old_file, (old_time, old_time))

        # Primeiro encontra candidatas para archive
        archive_candidates = self.gc.find_candidates_for_archive(tmp_path, days_threshold=7)

        # Depois encontra candidatas para deleção
        deletion_candidates = self.gc.find_candidates_for_deletion(
            archive_candidates, deletion_threshold_days=30
        )

        # Arquivo muito antigo deve ser candidato para deleção
        filenames = [c["filename"] for c in deletion_candidates]
        assert "very_old.md" in filenames

    def test_deletion_never_removes_user_type(self, tmp_path):
        """Testa que deleção nunca remove user type"""
        import os

        user_file = tmp_path / "user.md"
        user_file.write_text("---\nname: User\ntype: user\n---")

        # Define mtime muito antigo
        old_time = time.time() - (60 * 24 * 60 * 60)
        os.utime(user_file, (old_time, old_time))

        archive_candidates = self.gc.find_candidates_for_archive(tmp_path, days_threshold=7)
        deletion_candidates = self.gc.find_candidates_for_deletion(
            archive_candidates, deletion_threshold_days=30
        )

        # User type NÃO deve ser candidato para deleção
        filenames = [c["filename"] for c in deletion_candidates]
        assert "user.md" not in filenames

    def test_deletion_never_removes_feedback_type(self, tmp_path):
        """Testa que deleção nunca remove feedback type"""
        import os

        feedback_file = tmp_path / "feedback.md"
        feedback_file.write_text("---\nname: Feedback\ntype: feedback\n---")

        # Define mtime muito antigo
        old_time = time.time() - (60 * 24 * 60 * 60)
        os.utime(feedback_file, (old_time, old_time))

        archive_candidates = self.gc.find_candidates_for_archive(tmp_path, days_threshold=7)
        deletion_candidates = self.gc.find_candidates_for_deletion(
            archive_candidates, deletion_threshold_days=30
        )

        # Feedback type NÃO deve ser candidato para deleção
        filenames = [c["filename"] for c in deletion_candidates]
        assert "feedback.md" not in filenames

    def test_run_gc_dry_run(self, tmp_path):
        """Testa run_gc em modo dry_run"""
        import os

        # Cria arquivo antigo
        old_file = tmp_path / "old.md"
        old_file.write_text("---\nname: Old\ntype: project\n---")

        # Define mtime antigo
        old_time = time.time() - (30 * 24 * 60 * 60)
        os.utime(old_file, (old_time, old_time))

        results = self.gc.run_gc(
            memory_dir=tmp_path,
            archive_threshold_days=7,
            deletion_threshold_days=14,
            dry_run=True
        )

        # Dry run não deleta nada
        assert results["dry_run"] is True
        assert len(results["deleted"]) == 0
        assert "old.md" in results["archive_candidates"]

    def test_run_gc_report_generation(self, tmp_path):
        """Testa geração de relatório do run_gc"""
        results = {
            "archive_candidates": ["old.md"],
            "deletion_candidates": ["very_old.md"],
            "archived": [],
            "deleted": [],
            "dry_run": True
        }

        report = self.gc.generate_gc_report(results)

        assert isinstance(report, str)
        assert "Garbage Collection" in report or "GC" in report
        assert "old.md" in report

    def test_generate_gc_report_empty(self, tmp_path):
        """Testa relatório vazio"""
        results = {
            "archive_candidates": [],
            "deletion_candidates": [],
            "archived": [],
            "deleted": [],
            "dry_run": True
        }

        report = self.gc.generate_gc_report(results)

        assert isinstance(report, str)
        assert "Nenhuma" in report or "nenhuma" in report or "none" in report.lower()

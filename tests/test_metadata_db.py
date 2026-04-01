"""Testes para MetadataDB"""

import pytest
from pathlib import Path
from src.index.metadata_db import MetadataDB


class TestMetadataDB:

    def test_create_schema(self, tmp_path):
        """Cria schema do banco"""
        db = MetadataDB(tmp_path / "metadata.db")

        # Verifica tabelas
        tables = db.list_tables()
        assert "memories" in tables
        assert "memories_fts" in tables

    def test_insert_memory(self, tmp_path):
        """Insere memória no índice"""
        db = MetadataDB(tmp_path / "metadata.db")

        db.insert({
            "id": "mem_001",
            "type": "decision",
            "project": "test-project",
            "title": "DB Choice",
            "path": "official/test-project/decisions/db-choice.md"
        })

        memories = db.search(project="test-project")
        assert len(memories) == 1

    def test_fts_search(self, tmp_path):
        """Busca full-text"""
        db = MetadataDB(tmp_path / "metadata.db")

        db.insert({
            "id": "mem_001",
            "type": "error",
            "project": "test-project",
            "title": "Deadlock no pool",
            "content": "Deadlock no connection pool",
            "tags": "deadlock,pool"
        })

        results = db.search_fts("deadlock")
        assert len(results) == 1

    def test_get_by_id(self, tmp_path):
        """Obtém memória por ID"""
        db = MetadataDB(tmp_path / "metadata.db")

        db.insert({
            "id": "mem_001",
            "type": "decision",
            "project": "test-project",
            "title": "DB Choice"
        })

        memory = db.get_by_id("mem_001")
        assert memory is not None
        assert memory["title"] == "DB Choice"

    def test_update_access(self, tmp_path):
        """Atualiza contagem de acessos"""
        db = MetadataDB(tmp_path / "metadata.db")

        db.insert({
            "id": "mem_001",
            "type": "decision",
            "project": "test-project",
            "title": "DB Choice",
            "access_count": 0
        })

        db.update_access("mem_001")

        memory = db.get_by_id("mem_001")
        assert memory["access_count"] >= 1

    def test_delete(self, tmp_path):
        """Remove memória do índice"""
        db = MetadataDB(tmp_path / "metadata.db")

        db.insert({
            "id": "mem_001",
            "type": "decision",
            "project": "test-project",
            "title": "DB Choice"
        })

        db.delete("mem_001")

        memory = db.get_by_id("mem_001")
        assert memory is None

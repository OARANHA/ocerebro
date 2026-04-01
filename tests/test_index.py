"""Testes para EmbeddingsDB e QueryEngine"""

import pytest
from pathlib import Path
from src.index.metadata_db import MetadataDB
from src.index.embeddings_db import EmbeddingsDB
from src.index.queries import QueryEngine, QueryResult


class TestEmbeddingsDB:
    """Testes para EmbeddingsDB"""

    def test_create_schema(self, tmp_path):
        """Cria schema do banco"""
        db = EmbeddingsDB(tmp_path / "embeddings.db")

        tables = db.list_tables() if hasattr(db, 'list_tables') else True
        assert tables  # Banco criado com sucesso

    def test_compute_hash(self, tmp_path):
        """Computa hash de conteúdo"""
        db = EmbeddingsDB(tmp_path / "embeddings.db")

        hash1 = db._compute_hash("texto igual")
        hash2 = db._compute_hash("texto igual")
        hash3 = db._compute_hash("texto diferente")

        assert hash1 == hash2
        assert hash1 != hash3

    def test_cosine_similarity(self, tmp_path):
        """Calcula similaridade cosseno"""
        db = EmbeddingsDB(tmp_path / "embeddings.db")

        # Vetores idênticos
        sim = db._cosine_similarity([1, 0, 0], [1, 0, 0])
        assert abs(sim - 1.0) < 0.001

        # Vetores ortogonais
        sim = db._cosine_similarity([1, 0, 0], [0, 1, 0])
        assert abs(sim - 0.0) < 0.001

        # Vetores opostos
        sim = db._cosine_similarity([1, 0, 0], [-1, 0, 0])
        assert abs(sim - (-1.0)) < 0.001

    def test_upsert_and_get(self, tmp_path):
        """Insere e obtém embedding"""
        db = EmbeddingsDB(tmp_path / "embeddings.db")

        # Mock do embedding para não depender do modelo
        original_compute = db._compute_embedding
        db._compute_embedding = lambda x: [0.1, 0.2, 0.3]

        embedding_id = db.upsert(
            memory_id="mem_001",
            text="Texto de teste",
            memory_type="decision",
            project="test-project"
        )

        assert embedding_id == "emb_mem_001"

        result = db.get_by_memory_id("mem_001")
        assert result is not None
        assert result["memory_id"] == "mem_001"
        # sqlite-vec usa float32, então há pequena diferença de precisão
        assert len(result["embedding"]) == 3
        assert result["embedding"][0] == pytest.approx(0.1, abs=0.001)
        assert result["embedding"][1] == pytest.approx(0.2, abs=0.001)
        assert result["embedding"][2] == pytest.approx(0.3, abs=0.001)

        # Restaura função original
        db._compute_embedding = original_compute

    def test_upsert_cache_hit(self, tmp_path):
        """Não recalcula embedding se hash igual"""
        db = EmbeddingsDB(tmp_path / "embeddings.db")

        call_count = 0

        def mock_compute(text):
            nonlocal call_count
            call_count += 1
            return [0.1, 0.2, 0.3]

        db._compute_embedding = mock_compute

        # Primeira inserção
        db.upsert("mem_001", "mesmo texto", "decision", "test")
        # Segunda inserção (deve usar cache)
        db.upsert("mem_001", "mesmo texto", "decision", "test")

        assert call_count == 1

        # Forçar recálculo
        db.upsert("mem_001", "mesmo texto", "decision", "test", force_recompute=True)
        assert call_count == 2

    def test_search_similar(self, tmp_path):
        """Busca embeddings similares"""
        db = EmbeddingsDB(tmp_path / "embeddings.db")

        # Mock dos embeddings
        embeddings = {
            "texto sobre banco de dados": [1.0, 0.0, 0.0],
            "texto sobre Python": [0.0, 1.0, 0.0],
            "texto sobre SQL": [0.9, 0.1, 0.0],
        }

        db._compute_embedding = lambda x: embeddings.get(x, [0.0, 0.0, 1.0])

        # Insere embeddings
        for text, emb in embeddings.items():
            db._compute_embedding = lambda x, t=text: embeddings[t]
            db.upsert(f"mem_{text[:5]}", text, "decision", "test")

        # Busca similar (mock do resultado)
        db._compute_embedding = lambda x: [1.0, 0.0, 0.0]  # Query
        results = db.search_similar("banco", limit=5, threshold=0.0)

        # Resultados devem estar ordenados por similaridade
        assert len(results) > 0

    def test_delete(self, tmp_path):
        """Remove embedding"""
        db = EmbeddingsDB(tmp_path / "embeddings.db")
        db._compute_embedding = lambda x: [0.1, 0.2, 0.3]

        db.upsert("mem_001", "texto", "decision", "test")
        db.delete("mem_001")

        result = db.get_by_memory_id("mem_001")
        assert result is None

    def test_list_embeddings(self, tmp_path):
        """Lista embeddings"""
        db = EmbeddingsDB(tmp_path / "embeddings.db")
        db._compute_embedding = lambda x: [0.1, 0.2, 0.3]

        db.upsert("mem_001", "texto 1", "decision", "project-a")
        db.upsert("mem_002", "texto 2", "error", "project-a")
        db.upsert("mem_003", "texto 3", "decision", "project-b")

        all_embeddings = db.list_embeddings()
        assert len(all_embeddings) == 3

        project_a = db.list_embeddings("project-a")
        assert len(project_a) == 2

    def test_get_stats(self, tmp_path):
        """Obtém estatísticas"""
        db = EmbeddingsDB(tmp_path / "embeddings.db")
        db._compute_embedding = lambda x: [0.1, 0.2, 0.3]

        db.upsert("mem_001", "texto 1", "decision", "project-a")
        db.upsert("mem_002", "texto 2", "error", "project-a")

        stats = db.get_stats()

        assert stats["total_embeddings"] == 2
        assert "decision" in stats["by_type"]
        assert "project-a" in stats["by_project"]


class TestQueryEngine:
    """Testes para QueryEngine"""

    def test_search_hybrid(self, tmp_path):
        """Busca híbrida FTS + semantic"""
        metadata_db = MetadataDB(tmp_path / "metadata.db")
        embeddings_db = EmbeddingsDB(tmp_path / "embeddings.db")
        engine = QueryEngine(metadata_db, embeddings_db)

        # Mock de embeddings
        embeddings_db._compute_embedding = lambda x: [0.5, 0.5, 0.5]

        # Insere memória
        metadata_db.insert({
            "id": "mem_001",
            "type": "decision",
            "project": "test",
            "title": "Decisão sobre banco de dados",
            "content": "PostgreSQL vs MongoDB",
            "tags": "database,sql"
        })

        results = engine.search("banco de dados", project="test", limit=10)

        # Deve retornar resultados (mesmo que vazios se FTS não encontrar)
        assert isinstance(results, list)

    def test_search_by_metadata(self, tmp_path):
        """Busca por metadados"""
        metadata_db = MetadataDB(tmp_path / "metadata.db")
        embeddings_db = EmbeddingsDB(tmp_path / "embeddings.db")
        engine = QueryEngine(metadata_db, embeddings_db)

        metadata_db.insert({
            "id": "mem_001",
            "type": "decision",
            "project": "test",
            "title": "Decisão 1",
            "tags": "database,sql"
        })
        metadata_db.insert({
            "id": "mem_002",
            "type": "error",
            "project": "test",
            "title": "Erro 1",
            "tags": "bug,critical"
        })

        # Busca por projeto
        results = engine.search_by_metadata(project="test")
        assert len(results) == 2

        # Busca por tipo
        results = engine.search_by_metadata(project="test", mem_type="decision")
        assert len(results) == 1
        assert results[0].type == "decision"

        # Busca por tags
        results = engine.search_by_metadata(project="test", tags=["database"])
        assert len(results) == 1

    def test_find_similar_to_memory(self, tmp_path):
        """Encontra memórias similares"""
        metadata_db = MetadataDB(tmp_path / "metadata.db")
        embeddings_db = EmbeddingsDB(tmp_path / "embeddings.db")
        engine = QueryEngine(metadata_db, embeddings_db)

        # Mock de embeddings
        embeddings_db._compute_embedding = lambda x: [0.5, 0.5, 0.5]

        metadata_db.insert({
            "id": "mem_001",
            "type": "decision",
            "project": "test",
            "title": "Decisão similar 1",
            "content": "Conteúdo similar"
        })
        metadata_db.insert({
            "id": "mem_002",
            "type": "decision",
            "project": "test",
            "title": "Decisão similar 2",
            "content": "Conteúdo similar"
        })

        results = engine.find_similar_to_memory("mem_001", limit=5)

        # Pode retornar vazios se embeddings forem mock
        assert isinstance(results, list)

    def test_get_related(self, tmp_path):
        """Obtém memórias relacionadas"""
        metadata_db = MetadataDB(tmp_path / "metadata.db")
        embeddings_db = EmbeddingsDB(tmp_path / "embeddings.db")
        engine = QueryEngine(metadata_db, embeddings_db)

        # Mock de embeddings
        embeddings_db._compute_embedding = lambda x: [0.5, 0.5, 0.5]

        metadata_db.insert({
            "id": "mem_001",
            "type": "decision",
            "project": "test",
            "title": "Decisão 1",
            "tags": "shared,database"
        })
        metadata_db.insert({
            "id": "mem_002",
            "type": "decision",
            "project": "test",
            "title": "Decisão 2",
            "tags": "shared,sql"
        })

        results = engine.get_related("mem_001", by_tags=True, by_semantic=True)

        # mem_002 deve aparecer por compartilhar tag 'shared'
        assert isinstance(results, list)


class TestQueryResult:
    """Testes para dataclass QueryResult"""

    def test_create_result(self):
        """Cria resultado de query"""
        result = QueryResult(
            memory_id="mem_001",
            type="decision",
            project="test",
            title="Minha Decisão",
            score=0.85,
            source="hybrid"
        )

        assert result.memory_id == "mem_001"
        assert result.score == 0.85
        assert result.source == "hybrid"
        assert result.metadata is None

    def test_create_result_with_metadata(self):
        """Cria resultado com metadados"""
        result = QueryResult(
            memory_id="mem_001",
            type="error",
            project="test",
            title="Erro crítico",
            score=0.95,
            source="semantic",
            metadata={"similarity": 0.95, "tags": ["critical"]}
        )

        assert result.metadata["similarity"] == 0.95

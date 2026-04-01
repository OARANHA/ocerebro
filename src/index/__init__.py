"""Índice do Cerebro: SQLite + FTS + embeddings"""
from .metadata_db import MetadataDB


class EmbeddingsDB:
    """
    Banco de dados para embeddings vetoriais.

    Stub - será implementado futuramente.
    """
    pass


class QueryEngine:
    """
    Engine de consultas híbridas (FTS + embeddings).

    Stub - será implementado futuramente.
    """
    pass


__all__ = ["MetadataDB", "EmbeddingsDB", "QueryEngine"]

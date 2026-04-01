"""SQLite + FTS para metadados do Cerebro"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class MetadataDB:
    """
    Banco de dados SQLite com FTS5 para índice de memórias.

    Armazena metadados estruturados e oferece busca full-text
    via FTS5 virtual table.
    """

    def __init__(self, db_path: Path):
        """
        Inicializa o MetadataDB.

        Args:
            db_path: Path para o arquivo do banco de dados
        """
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        """
        Cria conexão com o banco.

        Returns:
            Conexão SQLite configurada
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self):
        """Cria schema do banco"""
        conn = self._connect()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                type TEXT,
                project TEXT,
                title TEXT,
                content TEXT,
                tags TEXT,
                severity TEXT,
                impact TEXT,
                importance_score REAL,
                recency_score REAL,
                frequency_score REAL,
                links_score REAL,
                total_score REAL,
                created_at TEXT,
                updated_at TEXT,
                last_accessed TEXT,
                access_count INTEGER DEFAULT 0,
                path TEXT,
                layer TEXT,
                content_hash TEXT
            )
        """)

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                id UNINDEXED,
                title,
                content,
                tags,
                project
            )
        """)

        conn.commit()
        conn.close()

    def list_tables(self) -> List[str]:
        """
        Lista tabelas do banco.

        Returns:
            Lista de nomes de tabelas
        """
        conn = self._connect()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables

    def insert(self, data: Dict[str, Any]) -> None:
        """
        Insere memória no índice.

        Args:
            data: Dados da memória
        """
        conn = self._connect()

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])

        conn.execute(
            f"INSERT OR REPLACE INTO memories ({columns}) VALUES ({placeholders})",
            list(data.values())
        )

        # Atualiza FTS
        if "content" in data:
            conn.execute(
                "INSERT OR REPLACE INTO memories_fts (id, title, content, tags, project) VALUES (?, ?, ?, ?, ?)",
                (data.get("id"), data.get("title", ""), data.get("content", ""), data.get("tags", ""), data.get("project", ""))
            )

        conn.commit()
        conn.close()

    def search(self, project: Optional[str] = None, type: Optional[str] = None) -> List[Dict]:
        """
        Busca por metadados.

        Args:
            project: Filtrar por projeto (opcional)
            type: Filtrar por tipo (opcional)

        Returns:
            Lista de memórias encontradas
        """
        conn = self._connect()

        query = "SELECT * FROM memories WHERE 1=1"
        params = []

        if project:
            query += " AND project = ?"
            params.append(project)

        if type:
            query += " AND type = ?"
            params.append(type)

        cursor = conn.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def search_fts(self, query: str, project: Optional[str] = None) -> List[Dict]:
        """
        Busca full-text.

        Args:
            query: Termo de busca
            project: Filtrar por projeto (opcional)

        Returns:
            Lista de memórias encontradas
        """
        conn = self._connect()

        if project:
            sql = """
                SELECT m.* FROM memories m
                JOIN memories_fts fts ON fts.id = m.id
                WHERE memories_fts MATCH ? AND m.project = ?
            """
            cursor = conn.execute(sql, (query, project))
        else:
            sql = """
                SELECT m.* FROM memories m
                JOIN memories_fts fts ON fts.id = m.id
                WHERE memories_fts MATCH ?
            """
            cursor = conn.execute(sql, (query,))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def get_by_id(self, memory_id: str) -> Optional[Dict]:
        """
        Obtém memória por ID.

        Args:
            memory_id: ID da memória

        Returns:
            Dados da memória ou None
        """
        conn = self._connect()
        cursor = conn.execute(
            "SELECT * FROM memories WHERE id = ?",
            (memory_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_access(self, memory_id: str) -> None:
        """
        Atualiza contagem de acessos.

        Args:
            memory_id: ID da memória
        """
        conn = self._connect()
        conn.execute("""
            UPDATE memories
            SET access_count = access_count + 1,
                last_accessed = datetime('now')
            WHERE id = ?
        """, (memory_id,))
        conn.commit()
        conn.close()

    def delete(self, memory_id: str) -> None:
        """
        Remove memória do índice.

        Args:
            memory_id: ID da memória
        """
        conn = self._connect()
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.execute("DELETE FROM memories_fts WHERE id = ?", (memory_id,))
        conn.commit()
        conn.close()

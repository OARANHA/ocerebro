"""Armazenamento JSONL append-only com rotação mensal"""

import json
from pathlib import Path
from typing import List, Optional
from src.core.event_schema import Event


class JSONLStorage:
    """
    Armazenamento append-only de eventos em formato JSONL.

    Arquivos são organizados por projeto e mês:
    raw/{project}/events-YYYY-MM.jsonl

    Rotação automática por mês - cada arquivo contém eventos de um mês específico.
    """

    def __init__(self, base_dir: Path):
        """
        Inicializa o armazenamento JSONL.

        Args:
            base_dir: Diretório base para a pasta raw/
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_project_dir(self, project: str) -> Path:
        """Retorna diretório do projeto"""
        return self.base_dir / project

    def _get_current_file(self, project: str) -> Path:
        """
        Retorna o arquivo JSONL atual para um projeto.

        O arquivo é nomeado com o mês atual: events-YYYY-MM.jsonl

        WINDOWS FIX: Usa datetime.now(timezone.utc) ao invés de utcnow() deprecated
        """
        project_dir = self._get_project_dir(project)
        project_dir.mkdir(parents=True, exist_ok=True)

        # WINDOWS FIX: datetime.now(timezone.utc) ao invés de datetime.utcnow()
        from datetime import datetime, timezone
        month_str = datetime.now(timezone.utc).strftime("%Y-%m")
        return project_dir / f"events-{month_str}.jsonl"

    def append(self, event: Event) -> None:
        """
        Anexa um evento ao arquivo JSONL do projeto.

        Args:
            event: Evento a ser anexado
        """
        jsonl_file = self._get_current_file(event.project)

        with open(jsonl_file, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def read(self, project: str) -> List[Event]:
        """
        Lê todos os eventos de um projeto.

        Args:
            project: Nome do projeto

        Returns:
            Lista de eventos ordenados por timestamp
        """
        project_dir = self._get_project_dir(project)
        if not project_dir.exists():
            return []

        events = []
        for jsonl_file in sorted(project_dir.glob("events-*.jsonl")):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(Event.model_validate_json(line))

        return events

    def read_iter(self, project: str):
        """
        Gerador — não carrega tudo em memória.

        PERFORMANCE FIX: Permite iterar sobre eventos sem carregar todos em memória

        Args:
            project: Nome do projeto

        Yields:
            Eventos um por um
        """
        project_dir = self._get_project_dir(project)
        if not project_dir.exists():
            return

        for jsonl_file in sorted(project_dir.glob("events-*.jsonl")):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield Event.model_validate_json(line)

    def read_last_n(self, project: str, n: int = 1000) -> List[Event]:
        """
        Lê apenas os N eventos mais recentes.

        PERFORMANCE FIX: Usa deque com maxlen para memória constante O(n)

        Args:
            project: Nome do projeto
            n: Número máximo de eventos (padrão: 1000)

        Returns:
            Lista dos N eventos mais recentes
        """
        from collections import deque
        return list(deque(self.read_iter(project), maxlen=n))

    def read_since(self, project: str, since: str) -> List[Event]:
        """
        Lê eventos desde uma data específica.

        WARN-05 FIX: Filtra por data durante a leitura para evitar carregar tudo em memória

        Args:
            project: Nome do projeto
            since: Data mínima (ISO format, ex: "2026-03-01T00:00:00Z")

        Returns:
            Lista de eventos após a data especificada
        """
        from datetime import datetime, timezone

        project_dir = self._get_project_dir(project)
        if not project_dir.exists():
            return []

        # Parse da data de início
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            # Fallback: lê tudo
            return self.read(project)

        events = []
        for jsonl_file in sorted(project_dir.glob("events-*.jsonl")):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = Event.model_validate_json(line)
                        # Parse do timestamp do evento
                        event_ts = event.ts.replace("Z", "+00:00")
                        event_dt = datetime.fromisoformat(event_ts)

                        if event_dt >= since_dt:
                            events.append(event)
                    except Exception:
                        # Ignora eventos com timestamp inválido
                        continue

        return events

    def read_range(self, project: str, start_id: str, end_id: str) -> List[Event]:
        """
        Lê eventos em um intervalo de IDs.

        HIGH FIX: Valida existência dos IDs antes de filtrar

        Args:
            project: Nome do projeto
            start_id: ID inicial (inclusive)
            end_id: ID final (inclusive)

        Returns:
            Lista de eventos no intervalo especificado

        Raises:
            ValueError: Se start_id ou end_id não existirem
        """
        if not start_id or not end_id:
            raise ValueError("start_id e end_id são obrigatórios")

        all_events = self.read(project)
        ids = {e.event_id for e in all_events}

        if start_id not in ids:
            raise ValueError(f"start_id não encontrado: {start_id}")
        if end_id not in ids:
            raise ValueError(f"end_id não encontrado: {end_id}")

        in_range = False
        result = []

        for event in all_events:
            if event.event_id == start_id:
                in_range = True

            if in_range:
                result.append(event)

            if event.event_id == end_id:
                break

        return result

    def get_file_stats(self, project: str) -> dict:
        """
        Retorna estatísticas dos arquivos de um projeto.

        Args:
            project: Nome do projeto

        Returns:
            Dicionário com estatísticas por arquivo
        """
        project_dir = self._get_project_dir(project)
        if not project_dir.exists():
            return {}

        stats = {}
        for jsonl_file in sorted(project_dir.glob("events-*.jsonl")):
            size_bytes = jsonl_file.stat().st_size
            line_count = sum(1 for _ in open(jsonl_file, "r", encoding="utf-8"))
            stats[jsonl_file.name] = {
                "size_bytes": size_bytes,
                "event_count": line_count
            }

        return stats

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
        """
        project_dir = self._get_project_dir(project)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Usa os primeiros 7 caracteres do timestamp (YYYY-MM)
        from datetime import datetime
        month_str = datetime.utcnow().strftime("%Y-%m")
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

    def read_range(self, project: str, start_id: str, end_id: str) -> List[Event]:
        """
        Lê eventos em um intervalo de IDs.

        Args:
            project: Nome do projeto
            start_id: ID inicial (inclusive)
            end_id: ID final (inclusive)

        Returns:
            Lista de eventos no intervalo especificado
        """
        all_events = self.read(project)

        # Filtra eventos no intervalo de IDs
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

"""Garbage collection para memórias do Cerebro"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class GarbageCollector:
    """
    Garbage collection para memórias.

    Identifica memórias candidatas para arquivamento ou remoção
    baseado em policies de forgetting.
    """

    def __init__(self, config_path: Path):
        """
        Inicializa o GarbageCollector.

        Args:
            config_path: Path para configuração
        """
        self.config_path = config_path

    def find_candidates_for_archive(
        self,
        memories: List[Dict[str, Any]],
        days_threshold: int
    ) -> List[Dict[str, Any]]:
        """
        Encontra memórias candidatas para arquivamento.

        Args:
            memories: Lista de memórias
            days_threshold: Dias mínimos para arquivar

        Returns:
            Lista de memórias candidatas
        """
        candidates = []
        now = datetime.now(timezone.utc)

        for memory in memories:
            created_at = memory.get("created_at")
            if not created_at:
                continue

            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            days_old = (now - created_dt).days

            if days_old > days_threshold:
                candidates.append(memory)

        return candidates

    def find_candidates_for_deletion(
        self,
        memories: List[Dict[str, Any]],
        can_delete_fn
    ) -> List[Dict[str, Any]]:
        """
        Encontra memórias candidatas para deleção.

        Args:
            memories: Lista de memórias
            can_delete_fn: Função que verifica se pode deletar

        Returns:
            Lista de memórias candidatas
        """
        candidates = []

        for memory in memories:
            if can_delete_fn(memory):
                candidates.append(memory)

        return candidates

    def log_gc_event(
        self,
        action: str,
        memory_id: str,
        reason: str,
        log_path: Path
    ) -> None:
        """
        Loga evento de GC.

        Args:
            action: Ação realizada (archive, delete)
            memory_id: ID da memória
            reason: Motivo da ação
            log_path: Path para arquivo de log
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        log_entry = f"{timestamp} | {action} | {memory_id} | {reason}\n"

        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)

    def run_gc(
        self,
        memories: List[Dict[str, Any]],
        can_delete_fn,
        archive_threshold: int,
        log_path: Optional[Path] = None
    ) -> Dict[str, List[str]]:
        """
        Executa garbage collection.

        Args:
            memories: Lista de memórias
            can_delete_fn: Função que verifica se pode deletar
            archive_threshold: Dias para arquivamento
            log_path: Path para log (opcional)

        Returns:
            Dicionário com IDs arquivados e deletados
        """
        results = {"archived": [], "deleted": []}

        archive_candidates = self.find_candidates_for_archive(memories, archive_threshold)
        delete_candidates = self.find_candidates_for_deletion(archive_candidates, can_delete_fn)

        for memory in delete_candidates:
            memory_id = memory.get("id", "unknown")
            results["deleted"].append(memory_id)

            if log_path:
                self.log_gc_event("delete", memory_id, "GC criteria met", log_path)

        for memory in archive_candidates:
            memory_id = memory.get("id", "unknown")
            if memory_id not in results["deleted"]:
                results["archived"].append(memory_id)

                if log_path:
                    self.log_gc_event("archive", memory_id, "Age threshold met", log_path)

        return results

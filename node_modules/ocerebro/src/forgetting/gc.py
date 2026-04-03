"""Garbage collection para memórias do Cerebro.

Replica a lógica de garbage collection do Claude Code:
- Filtra por mtime do arquivo (última modificação)
- Nunca remove memórias de tipo 'user' ou 'feedback'
- Aplica threshold de dias sem acesso para working sessions
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.memdir.scanner import parse_frontmatter
from src.core.paths import MAX_MEMORY_FILES


class GarbageCollector:
    """
    Garbage collection para memórias.

    Identifica memórias candidatas para arquivamento ou remoção
    baseado em policies de forgetting.
    """

    def __init__(self, config_path: Path, metadata_db: Optional[Any] = None):
        """
        Inicializa o GarbageCollector.

        Args:
            config_path: Path para configuração
            metadata_db: Instância opcional do MetadataDB para consultar scores
        """
        self.config_path = config_path
        self.metadata_db = metadata_db

    def find_candidates_for_archive(
        self,
        memory_dir: Path,
        days_threshold: int
    ) -> List[Dict[str, Any]]:
        """
        Encontra memórias candidatas para arquivamento.

        Args:
            memory_dir: Diretório de memória para scan
            days_threshold: Dias mínimos para arquivar

        Returns:
            Lista de memórias candidatas
        """
        candidates = []
        now = datetime.now()
        cutoff_ts = (now.timestamp()) - (days_threshold * 24 * 60 * 60)

        if not memory_dir.exists():
            return candidates

        # Scan de arquivos .md (excluindo MEMORY.md)
        for file_path in memory_dir.rglob("*.md"):
            if file_path.name == "MEMORY.md":
                continue

            try:
                # Usa mtime (última modificação) em vez de created_at
                mtime = file_path.stat().st_mtime

                if mtime < cutoff_ts:
                    # Verifica tipo no frontmatter
                    content = file_path.read_text(encoding="utf-8")[:2000]
                    frontmatter = parse_frontmatter(content)
                    mem_type = frontmatter.get("type")

                    # Nunca arquiva memórias de tipo 'user' ou 'feedback'
                    if mem_type in ['user', 'feedback']:
                        continue

                    # Tarefa 2: Verifica total_score se metadata_db estiver disponível
                    if self.metadata_db:
                        mem_id = frontmatter.get("name", file_path.stem)
                        memory_data = self.metadata_db.get_by_id(mem_id)
                        if memory_data and memory_data.get("total_score", 0) >= 0.5:
                            # Memória com alto score não é candidata
                            continue

                    candidates.append({
                        "file_path": str(file_path),
                        "filename": file_path.name,
                        "type": mem_type,
                        "name": frontmatter.get("name"),
                        "description": frontmatter.get("description"),
                        "mtime": mtime,
                        "days_since_modified": int((now.timestamp() - mtime) / (24 * 60 * 60))
                    })
            except Exception:
                # Silenciosamente ignora arquivos com erro
                continue

        return candidates

    def find_candidates_for_deletion(
        self,
        candidates: List[Dict[str, Any]],
        deletion_threshold_days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Encontra memórias candidatas para deleção.

        Critérios:
        - mtime > deletion_threshold_days (mais antigo que threshold)
        - Tipo NÃO é 'user', 'feedback', ou 'project' com atividade recente
        - Não está linkada no MEMORY.md

        Args:
            candidates: Lista de memórias candidatas (do find_candidates_for_archive)
            deletion_threshold_days: Dias para deleção (default: 30)

        Returns:
            Lista de memórias candidatas para deleção
        """
        deletion_candidates = []
        now = datetime.now()
        deletion_cutoff = now.timestamp() - (deletion_threshold_days * 24 * 60 * 60)

        for memory in candidates:
            mtime = memory.get("mtime", 0)
            mem_type = memory.get("type")

            # Nunca deleta user ou feedback
            if mem_type in ['user', 'feedback']:
                continue

            # Deleta se mtime > threshold
            if mtime < deletion_cutoff:
                deletion_candidates.append(memory)

        return deletion_candidates

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
        memory_dir: Path,
        archive_threshold_days: int = 7,
        deletion_threshold_days: int = 30,
        dry_run: bool = True,
        log_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Executa garbage collection.

        Args:
            memory_dir: Diretório de memória para scan
            archive_threshold_days: Dias para arquivamento (default: 7)
            deletion_threshold_days: Dias para deleção (default: 30)
            dry_run: Se True, apenas lista candidatas, não remove
            log_path: Path para log (opcional)

        Returns:
            Dicionário com resultados do GC
        """
        results = {
            "archive_candidates": [],
            "deletion_candidates": [],
            "archived": [],
            "deleted": [],
            "dry_run": dry_run
        }

        # Passo 1: Encontra candidatas para arquivamento
        archive_candidates = self.find_candidates_for_archive(
            memory_dir, archive_threshold_days
        )
        results["archive_candidates"] = [c["filename"] for c in archive_candidates]

        # Passo 2: Encontra candidatas para deleção
        deletion_candidates = self.find_candidates_for_deletion(
            archive_candidates, deletion_threshold_days
        )
        results["deletion_candidates"] = [c["filename"] for c in deletion_candidates]

        # Passo 3: Aplica GC (se não for dry_run)
        if not dry_run:
            for candidate in deletion_candidates:
                try:
                    file_path = Path(candidate["file_path"])
                    file_path.unlink()
                    results["deleted"].append(candidate["filename"])

                    if log_path:
                        self.log_gc_event(
                            "delete",
                            candidate["filename"],
                            f"GC: {candidate['days_since_modified']} dias sem modificação",
                            log_path
                        )
                except Exception as e:
                    # Loga erro mas continua
                    if log_path:
                        self.log_gc_event("error", candidate["filename"], str(e), log_path)

            # Arquiva as restantes (não deletadas)
            import shutil

            arquivo_dir = memory_dir / "arquivo"
            arquivo_dir.mkdir(parents=True, exist_ok=True)

            memory_index = memory_dir / "MEMORY.md"

            for candidate in archive_candidates:
                if candidate["filename"] not in results["deleted"]:
                    src_path = Path(candidate["file_path"])
                    dst_path = arquivo_dir / src_path.name
                    try:
                        shutil.move(str(src_path), str(dst_path))
                        results["archived"].append(candidate["filename"])

                        # Remove referência do MEMORY.md
                        if memory_index.exists():
                            lines = memory_index.read_text(encoding="utf-8").splitlines()
                            updated = [
                                l for l in lines
                                if candidate["filename"] not in l
                            ]
                            memory_index.write_text(
                                "\n".join(updated), encoding="utf-8"
                            )

                        if log_path:
                            self.log_gc_event(
                                "archive",
                                candidate["filename"],
                                f"GC: {candidate['days_since_modified']} dias sem modificação",
                                log_path
                            )
                    except Exception as e:
                        if log_path:
                            self.log_gc_event(
                                "error", candidate["filename"], str(e), log_path
                            )

        return results

    def generate_gc_report(self, results: Dict[str, Any]) -> str:
        """
        Gera relatório legível do GC.

        Args:
            results: Dicionário de resultados do run_gc

        Returns:
            Relatório em markdown
        """
        lines = [
            "# Garbage Collection Report",
            "",
            f"**Modo:** {'Dry-run (nenhuma modificação)' if results['dry_run'] else 'Aplicação direta'}",
            "",
            "## Resumo",
            "",
            f"- Candidatas para arquivamento: {len(results['archive_candidates'])}",
            f"- Candidatas para deleção: {len(results['deletion_candidates'])}",
            f"- Arquivadas: {len(results['archived'])}",
            f"- Deletadas: {len(results['deleted'])}",
            "",
        ]

        if results["archive_candidates"]:
            lines.append("## Candidatas para Arquivamento")
            lines.append("")
            for filename in results["archive_candidates"]:
                lines.append(f"- {filename}")
            lines.append("")

        if results["deletion_candidates"]:
            lines.append("## Candidatas para Deleção")
            lines.append("")
            for filename in results["deletion_candidates"]:
                lines.append(f"- {filename}")
            lines.append("")

        if not results["archive_candidates"] and not results["deletion_candidates"]:
            lines.append("Nenhuma memória candidata para GC.")
            lines.append("")

        return "\n".join(lines)

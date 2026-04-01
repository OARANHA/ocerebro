"""Testes para CLI do Cerebro"""

import pytest
from pathlib import Path
from src.cli.main import CerebroCLI
from src.core.event_schema import Event, EventType, EventOrigin


class TestCerebroCLI:

    def test_checkpoint_manual(self, tmp_cerebro_dir):
        """Trigger manual de checkpoint"""
        cli = CerebroCLI(tmp_cerebro_dir)

        # Cria evento de teste
        event = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={},
            session_id="sess_abc"
        )
        cli.raw_storage.append(event)

        result = cli.checkpoint("test-project", "sess_abc", "test")

        assert "Checkpoint criado" in result
        assert "sess_abc" in result

    def test_checkpoint_no_events(self, tmp_cerebro_dir):
        """Checkpoint sem eventos"""
        cli = CerebroCLI(tmp_cerebro_dir)

        result = cli.checkpoint("test-project", "sess_nonexistent")

        assert "Nenhum evento encontrado" in result

    def test_memory_generation(self, tmp_cerebro_dir):
        """Gera memória ativa"""
        cli = CerebroCLI(tmp_cerebro_dir)

        result = cli.memory("test-project")

        assert "# Cerebro - Memória Ativa" in result

    def test_memory_write_to_file(self, tmp_cerebro_dir):
        """Gera memória ativa em arquivo"""
        cli = CerebroCLI(tmp_cerebro_dir)
        output_file = tmp_cerebro_dir / "MEMORY.md"

        result = cli.memory("test-project", output=output_file)

        assert "MEMORY.md gerado" in result
        assert output_file.exists()

    def test_search_no_results(self, tmp_cerebro_dir):
        """Busca sem resultados"""
        cli = CerebroCLI(tmp_cerebro_dir)

        result = cli.search("termo inexistente")

        assert "Nenhum resultado encontrado" in result

    def test_promote_session(self, tmp_cerebro_dir):
        """Promove sessão para official"""
        cli = CerebroCLI(tmp_cerebro_dir)

        # Cria draft
        cli.working_storage.write_session("test-project", "sess_promote", {
            "id": "sess_promote",
            "type": "session",
            "summary": {
                "total_events": 5,
                "files_changed": ["src/auth.py"]
            },
            "status": "draft"
        })

        result = cli.promote("test-project", "sess_promote", "session", "decision")

        assert "Promovido" in result

    def test_promote_nonexistent(self, tmp_cerebro_dir):
        """Promove draft inexistente"""
        cli = CerebroCLI(tmp_cerebro_dir)

        result = cli.promote("test-project", "nonexistent", "session", "decision")

        assert "não pôde ser promovido" in result or "não encontrado" in result

    def test_gc_dry_run(self, tmp_cerebro_dir):
        """GC em dry run"""
        cli = CerebroCLI(tmp_cerebro_dir)

        # Nota: Método renomeado de gc() para gc_cmd() para evitar conflito
        result = cli.gc_cmd(dry_run=True)

        assert "Garbage Collection" in result or "Relatório" in result

    def test_status(self, tmp_cerebro_dir):
        """Status do sistema"""
        cli = CerebroCLI(tmp_cerebro_dir)

        result = cli.status()

        assert "Status do Cerebro" in result
        assert "Session ID" in result

    def test_checkpoint_records_event(self, tmp_cerebro_dir):
        """Checkpoint registra evento"""
        cli = CerebroCLI(tmp_cerebro_dir)

        # Cria evento de teste
        event = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={},
            session_id="sess_record"
        )
        cli.raw_storage.append(event)

        cli.checkpoint("test-project", "sess_record", "test")

        # Verifica evento de checkpoint
        events = cli.raw_storage.read("test-project")
        checkpoint_events = [
            e for e in events
            if e.event_type == EventType.CHECKPOINT_CREATED
        ]

        assert len(checkpoint_events) == 1
        assert checkpoint_events[0].subtype == "manual"

    def test_promote_records_event(self, tmp_cerebro_dir):
        """Promoção registra evento"""
        cli = CerebroCLI(tmp_cerebro_dir)

        # Cria draft
        cli.working_storage.write_session("test-project", "sess_record", {
            "id": "sess_record",
            "type": "session",
            "summary": {"total_events": 5},
            "status": "draft"
        })

        cli.promote("test-project", "sess_record", "session", "decision")

        # Verifica evento de promoção
        events = cli.raw_storage.read("test-project")
        promotion_events = [
            e for e in events
            if e.event_type == EventType.PROMOTION_PERFORMED
        ]

        assert len(promotion_events) >= 1

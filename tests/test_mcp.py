"""Testes para MCP Server do Cerebro"""

import pytest
from pathlib import Path
from src.mcp.server import CerebroMCP
from src.core.event_schema import Event, EventType, EventOrigin


class TestCerebroMCP:

    def test_get_tools(self, tmp_cerebro_dir):
        """Retorna lista de ferramentas"""
        mcp = CerebroMCP(tmp_cerebro_dir)
        tools = mcp.get_tools()

        assert len(tools) == 5
        tool_names = [t.name for t in tools]
        assert "cerebro_memory" in tool_names
        assert "cerebro_search" in tool_names
        assert "cerebro_checkpoint" in tool_names
        assert "cerebro_promote" in tool_names
        assert "cerebro_status" in tool_names

    def test_memory_tool(self, tmp_cerebro_dir):
        """Ferramenta cerebro_memory"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        import asyncio
        result = asyncio.run(mcp.handle_tool("cerebro_memory", {"project": "test"}))

        assert len(result) == 1
        assert "# Cerebro - Memória Ativa" in result[0].text

    def test_search_tool_no_results(self, tmp_cerebro_dir):
        """Ferramenta cerebro_search sem resultados"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        import asyncio
        result = asyncio.run(mcp.handle_tool("cerebro_search", {"query": "inexistente"}))

        assert "Nenhum resultado encontrado" in result[0].text

    def test_checkpoint_tool(self, tmp_cerebro_dir):
        """Ferramenta cerebro_checkpoint"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        # Cria evento de teste
        event = Event(
            project="test-project",
            origin=EventOrigin.CLAUDE_CODE,
            event_type=EventType.TOOL_CALL,
            subtype="bash",
            payload={},
            session_id="sess_mcp"
        )
        mcp.raw_storage.append(event)

        import asyncio
        result = asyncio.run(mcp.handle_tool(
            "cerebro_checkpoint",
            {"project": "test-project", "session_id": "sess_mcp"}
        ))

        assert "Checkpoint criado" in result[0].text

    def test_checkpoint_tool_no_events(self, tmp_cerebro_dir):
        """Ferramenta cerebro_checkpoint sem eventos"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        import asyncio
        result = asyncio.run(mcp.handle_tool(
            "cerebro_checkpoint",
            {"project": "test", "session_id": "nonexistent"}
        ))

        assert "Nenhum evento encontrado" in result[0].text

    def test_promote_tool(self, tmp_cerebro_dir):
        """Ferramenta cerebro_promote"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        # Cria draft
        mcp.working_storage.write_session("test-project", "sess_promote", {
            "id": "sess_promote",
            "type": "session",
            "summary": {"total_events": 5},
            "status": "draft"
        })

        import asyncio
        result = asyncio.run(mcp.handle_tool(
            "cerebro_promote",
            {
                "project": "test-project",
                "draft_id": "sess_promote",
                "draft_type": "session",
                "promote_to": "decision"
            }
        ))

        assert "Promovido" in result[0].text

    def test_promote_tool_not_found(self, tmp_cerebro_dir):
        """Ferramenta cerebro_promote draft não encontrado"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        import asyncio
        result = asyncio.run(mcp.handle_tool(
            "cerebro_promote",
            {
                "project": "test",
                "draft_id": "nonexistent"
            }
        ))

        assert "não encontrado" in result[0].text

    def test_status_tool(self, tmp_cerebro_dir):
        """Ferramenta cerebro_status"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        import asyncio
        result = asyncio.run(mcp.handle_tool("cerebro_status", {}))

        assert "Status do Cerebro" in result[0].text
        assert "Session ID" in result[0].text

    def test_unknown_tool(self, tmp_cerebro_dir):
        """Ferramenta desconhecida"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        import asyncio
        result = asyncio.run(mcp.handle_tool("unknown_tool", {}))

        assert "Ferramenta desconhecida" in result[0].text

    def test_tool_error_handling(self, tmp_cerebro_dir):
        """Tratamento de erro em ferramenta"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        import asyncio
        # Argumentos inválidos para search
        result = asyncio.run(mcp.handle_tool("cerebro_search", {}))

        assert "Erro" in result[0].text or "Nenhum resultado" in result[0].text

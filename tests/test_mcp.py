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

        assert len(tools) == 10  # 7 originais + dream, remember, gc
        tool_names = [t.name for t in tools]
        assert "cerebro_memory" in tool_names
        assert "cerebro_search" in tool_names
        assert "cerebro_checkpoint" in tool_names
        assert "cerebro_promote" in tool_names
        assert "cerebro_status" in tool_names
        assert "cerebro_hooks" in tool_names
        assert "cerebro_diff" in tool_names
        assert "cerebro_dream" in tool_names
        assert "cerebro_remember" in tool_names
        assert "cerebro_gc" in tool_names

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

    def test_hooks_tool_list(self, tmp_cerebro_dir):
        """Ferramenta cerebro_hooks - list"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        import asyncio
        result = asyncio.run(mcp.handle_tool("cerebro_hooks", {"action": "list"}))

        # Sem hooks.yaml, deve retornar mensagem informativa
        assert "Nenhum hook" in result[0].text or "não configurados" in result[0].text.lower()

    def test_hooks_tool_with_config(self, tmp_path):
        """Ferramenta cerebro_hooks com configuração"""
        import yaml
        import asyncio

        # Cria hooks.yaml
        hooks_yaml = tmp_path / "hooks.yaml"
        hooks_yaml.write_text(yaml.dump({
            "hooks": [{
                "name": "test_hook",
                "event_type": "tool_call",
                "module_path": "hooks/test.py",
                "function": "execute",
                "config": {"key": "value"}
            }]
        }))

        # Cria estrutura cerebro completa
        cerebro_dir = tmp_path / ".cerebro"
        (cerebro_dir / "raw").mkdir(parents=True)
        (cerebro_dir / "working").mkdir(parents=True)
        (cerebro_dir / "official").mkdir(parents=True)
        (cerebro_dir / "index").mkdir(parents=True)

        mcp = CerebroMCP(cerebro_dir)
        result = asyncio.run(mcp.handle_tool("cerebro_hooks", {"action": "list"}))

        assert "test_hook" in result[0].text
        assert "tool_call" in result[0].text

    def test_diff_tool(self, tmp_cerebro_dir):
        """Ferramenta cerebro_diff"""
        mcp = CerebroMCP(tmp_cerebro_dir)

        import asyncio
        result = asyncio.run(mcp.handle_tool(
            "cerebro_diff",
            {"project": "test", "period_days": 7}
        ))

        assert "# Memory Diff Report" in result[0].text
        assert "Período" in result[0].text

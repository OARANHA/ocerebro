"""Geração de MEMORY.md a partir das camadas working/official"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .yaml_storage import YAMLStorage
    from ..official.markdown_storage import MarkdownStorage


class MemoryView:
    """
    Gera MEMORY.md como view de official + working.

    A memória ativa é uma visão consolidada das camadas:
    - Official Global (decisions, preferences, policies)
    - Official do Projeto (decisions, errors, preferences, state)
    - Working atual (sessions, features em progresso)
    """

    def __init__(self, cerebro_path: Path, official: "MarkdownStorage", working: "YAMLStorage"):
        """
        Inicializa o MemoryView.

        Args:
            cerebro_path: Diretório base do Cerebro
            official: Instância do MarkdownStorage
            working: Instância do YAMLStorage
        """
        self.cerebro_path = cerebro_path
        self.official = official
        self.working = working

    def generate(self, project: str) -> str:
        """
        Gera conteúdo do MEMORY.md para um projeto.

        Args:
            project: Nome do projeto

        Returns:
            Conteúdo Markdown do MEMORY.md
        """
        sections = ["# Cerebro - Memória Ativa", ""]

        # Official Global
        sections.append("## Official Global")
        sections.append("")
        global_items = self._list_global()
        if global_items:
            for item in global_items:
                sections.append(f"- [{item['title']}](global/{item['_type']}/{item['_file']})")
        else:
            sections.append("_Nenhuma memória global_")
        sections.append("")

        # Official do Projeto
        sections.append(f"## Official {project}")
        sections.append("")
        project_items = self._list_project(project)
        if project_items:
            for item in project_items:
                title = item.get('title', item['_file'])
                sections.append(f"- [{title}]({project}/{item['_type']}/{item['_file']})")
        else:
            sections.append("_Nenhuma memória oficial_")
        sections.append("")

        # Working atual
        sections.append("## Working atual")
        sections.append("")
        working_items = self._list_working(project)
        if working_items:
            for item in working_items:
                todo = item.get("todo", [])
                sections.append(f"- {item.get('id', 'unknown')}: {item.get('status', 'unknown')}")
                if todo:
                    todo_str = ', '.join(todo[:3])
                    sections.append(f"  - TODO: {todo_str}")
        else:
            sections.append("_Nenhuma sessão em progresso_")
        sections.append("")

        sections.append("---")
        sections.append("Outras memórias disponíveis via Cerebro (decisions, errors, preferences, state).")

        return "\n".join(sections)

    def _list_global(self) -> list:
        """
        Lista memórias globais.

        Returns:
            Lista de itens globais com metadados
        """
        items = []
        for subdir in ["decisions", "preferences", "policies"]:
            for item in self.official.list_official("global", subdir):
                item["_type"] = subdir
                items.append(item)
        return items

    def _list_project(self, project: str) -> list:
        """
        Lista memórias do projeto.

        Args:
            project: Nome do projeto

        Returns:
            Lista de itens do projeto com metadados
        """
        items = []
        for subdir in ["decisions", "errors", "preferences", "state"]:
            for item in self.official.list_official(project, subdir):
                item["_type"] = subdir
                items.append(item)
        return items

    def _list_working(self, project: str) -> list:
        """
        Lista working do projeto.

        Args:
            project: Nome do projeto

        Returns:
            Lista de sessões e features em progresso
        """
        items = []
        for session in self.working.list_sessions(project):
            items.append(session)
        for feature in self.working.list_features(project):
            items.append(feature)
        return items

    def write_to_file(self, project: str) -> Path:
        """
        Gera e escreve MEMORY.md no arquivo (dual-write: OCerebro + Claude Code nativo).

        Args:
            project: Nome do projeto

        Returns:
            Path do arquivo MEMORY.md criado
        """
        content = self.generate(project)

        # 1. Escreve em .ocerebro/MEMORY.md
        memory_file = self.cerebro_path / "MEMORY.md"
        memory_file.write_text(content, encoding="utf-8")

        # 2. Escreve em ~/.claude/projects/<slug>/memory/MEMORY.md (Claude Code nativo)
        try:
            from src.core.paths import get_auto_mem_path, get_memory_index
            auto_mem_dir = get_auto_mem_path()
            auto_mem_dir.mkdir(parents=True, exist_ok=True)
            index_path = get_memory_index(auto_mem_dir)

            # Gera conteúdo compatível com formato Claude Code
            claude_format_lines = ["# OCerebro - Memória Ativa", ""]
            claude_format_lines.append(f"## {project}")
            claude_format_lines.append("")

            for line in content.splitlines():
                if line.startswith("- ["):
                    claude_format_lines.append(line)

            claude_content = "\n".join(claude_format_lines)
            index_path.write_text(claude_content, encoding="utf-8")
        except Exception:
            pass  # Falha silenciosa

        return memory_file

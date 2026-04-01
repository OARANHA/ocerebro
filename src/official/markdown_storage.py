"""Armazenamento Markdown para camada Official"""

import yaml
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class MarkdownStorage:
    """
    Armazenamento Markdown para camada Official.

    Armazena decisões e erros em formato Markdown com frontmatter YAML.
    Organização:
    - official/{project}/decisions/{name}.md
    - official/{project}/errors/{name}.md
    """

    def __init__(self, base_path: Path):
        """
        Inicializa o armazenamento Markdown.

        Args:
            base_path: Diretório base para a pasta official/
        """
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _ensure_project_dir(self, project: str, subdir: str) -> Path:
        """
        Garante que diretório do projeto existe.

        Args:
            project: Nome do projeto
            subdir: Subdiretório (decisions ou errors)

        Returns:
            Path do diretório criado
        """
        dir_path = self.base_path / project / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _parse_frontmatter(self, content: str) -> Tuple[Dict[str, Any], str]:
        """
        Extrai frontmatter YAML do conteúdo Markdown.

        Args:
            content: Conteúdo completo do arquivo Markdown

        Returns:
            Tupla com (frontmatter, corpo)
        """
        match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)

        if not match:
            return {}, content

        frontmatter = yaml.safe_load(match.group(1))
        body = match.group(2)

        return frontmatter, body

    def _format_frontmatter(self, frontmatter: Dict[str, Any]) -> str:
        """
        Formata frontmatter YAML.

        Args:
            frontmatter: Dicionário com dados do frontmatter

        Returns:
            String formatada com delimitadores YAML
        """
        return f"---\n{yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)}---\n"

    def write_decision(self, project: str, name: str, frontmatter: Dict[str, Any], content: str) -> None:
        """
        Escreve decisão em Markdown.

        Args:
            project: Nome do projeto
            name: Nome da decisão
            frontmatter: Dados do frontmatter
            content: Corpo da decisão
        """
        dir_path = self._ensure_project_dir(project, "decisions")
        md_path = dir_path / f"{name}.md"

        frontmatter["type"] = "decision"
        full_content = self._format_frontmatter(frontmatter) + content

        md_path.write_text(full_content, encoding="utf-8")

    def read_decision(self, project: str, name: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Lê decisão de Markdown.

        Args:
            project: Nome do projeto
            name: Nome da decisão

        Returns:
            Tupla com (frontmatter, corpo) ou (None, None) se não existir
        """
        md_path = self.base_path / project / "decisions" / f"{name}.md"

        if not md_path.exists():
            return None, None

        content = md_path.read_text(encoding="utf-8")
        return self._parse_frontmatter(content)

    def write_error(self, project: str, name: str, frontmatter: Dict[str, Any], content: str) -> None:
        """
        Escreve erro em Markdown.

        Args:
            project: Nome do projeto
            name: Nome do erro
            frontmatter: Dados do frontmatter
            content: Corpo do post-mortem
        """
        dir_path = self._ensure_project_dir(project, "errors")
        md_path = dir_path / f"{name}.md"

        frontmatter["type"] = "error"
        full_content = self._format_frontmatter(frontmatter) + content

        md_path.write_text(full_content, encoding="utf-8")

    def read_error(self, project: str, name: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Lê erro de Markdown.

        Args:
            project: Nome do projeto
            name: Nome do erro

        Returns:
            Tupla com (frontmatter, corpo) ou (None, None) se não existir
        """
        md_path = self.base_path / project / "errors" / f"{name}.md"

        if not md_path.exists():
            return None, None

        content = md_path.read_text(encoding="utf-8")
        return self._parse_frontmatter(content)

    def list_official(self, project: str, subdir: str) -> List[Dict[str, Any]]:
        """
        Lista itens de um subdiretório official.

        Args:
            project: Nome do projeto
            subdir: Subdiretório (decisions ou errors)

        Returns:
            Lista de frontmatters com nome do arquivo
        """
        dir_path = self.base_path / project / subdir

        if not dir_path.exists():
            return []

        items = []
        for md_file in sorted(dir_path.glob("*.md")):
            frontmatter, _ = self._parse_frontmatter(md_file.read_text(encoding="utf-8"))
            if frontmatter:
                frontmatter["_file"] = md_file.name
                items.append(frontmatter)

        return items

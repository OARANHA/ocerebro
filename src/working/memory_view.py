"""Geração de MEMORY.md a partir das camadas working/official"""

from pathlib import Path
from typing import Optional


class MemoryView:
    """
    Gera visualização da memória ativa (MEMORY.md).

    Stub - será implementado no Task 7.
    """

    def __init__(self, working_path: Path, official_path: Path):
        self.working_path = working_path
        self.official_path = official_path

    def generate(self) -> str:
        """Gera conteúdo do MEMORY.md"""
        return "# MEMORY.md\n\nStub - será implementado no Task 7.\n"

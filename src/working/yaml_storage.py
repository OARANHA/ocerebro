"""Armazenamento YAML para camada Working"""

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


class YAMLStorage:
    """
    Armazenamento YAML para camada Working.

    Armazena sessões e features em formato YAML estruturado e editável.
    Organização:
    - working/{project}/sessions/{session_id}.yaml
    - working/{project}/features/{feature_name}.yaml
    """

    def __init__(self, base_path: Path):
        """
        Inicializa o armazenamento YAML.

        Args:
            base_path: Diretório base para a pasta working/
        """
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _ensure_project_dir(self, project: str, subdir: str) -> Path:
        """
        Garante que diretório do projeto existe.

        Args:
            project: Nome do projeto
            subdir: Subdiretório (sessions ou features)

        Returns:
            Path do diretório criado
        """
        dir_path = self.base_path / project / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def write_session(self, project: str, session_id: str, data: Dict[str, Any]) -> None:
        """
        Escreve sessão em YAML.

        Args:
            project: Nome do projeto
            session_id: ID da sessão
            data: Dados da sessão
        """
        dir_path = self._ensure_project_dir(project, "sessions")
        yaml_path = dir_path / f"{session_id}.yaml"

        content = {
            "id": session_id,
            "type": "session",
            **data
        }

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(content, f, allow_unicode=True, default_flow_style=False)

    def read_session(self, project: str, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Lê sessão de YAML.

        Args:
            project: Nome do projeto
            session_id: ID da sessão

        Returns:
            Dados da sessão ou None se não existir
        """
        yaml_path = self.base_path / project / "sessions" / f"{session_id}.yaml"

        if not yaml_path.exists():
            return None

        return yaml.safe_load(yaml_path.read_text())

    def list_sessions(self, project: str) -> List[Dict[str, Any]]:
        """
        Lista todas as sessões de um projeto.

        Args:
            project: Nome do projeto

        Returns:
            Lista de sessões
        """
        dir_path = self.base_path / project / "sessions"

        if not dir_path.exists():
            return []

        sessions = []
        for yaml_file in sorted(dir_path.glob("*.yaml")):
            sessions.append(yaml.safe_load(yaml_file.read_text()))

        return sessions

    def write_feature(self, project: str, feature_name: str, data: Dict[str, Any]) -> None:
        """
        Escreve feature em YAML.

        Args:
            project: Nome do projeto
            feature_name: Nome da feature
            data: Dados da feature
        """
        dir_path = self._ensure_project_dir(project, "features")
        yaml_path = dir_path / f"{feature_name}.yaml"

        content = {
            "id": feature_name,
            "type": "feature",
            **data
        }

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(content, f, allow_unicode=True, default_flow_style=False)

    def read_feature(self, project: str, feature_name: str) -> Optional[Dict[str, Any]]:
        """
        Lê feature de YAML.

        Args:
            project: Nome do projeto
            feature_name: Nome da feature

        Returns:
            Dados da feature ou None se não existir
        """
        yaml_path = self.base_path / project / "features" / f"{feature_name}.yaml"

        if not yaml_path.exists():
            return None

        return yaml.safe_load(yaml_path.read_text())

    def list_features(self, project: str) -> List[Dict[str, Any]]:
        """
        Lista todas as features de um projeto.

        Args:
            project: Nome do projeto

        Returns:
            Lista de features
        """
        dir_path = self.base_path / project / "features"

        if not dir_path.exists():
            return []

        features = []
        for yaml_file in sorted(dir_path.glob("*.yaml")):
            features.append(yaml.safe_load(yaml_file.read_text()))

        return features

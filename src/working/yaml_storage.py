"""Armazenamento YAML para camada Working"""

import yaml
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def _sanitize_name(name: str) -> str:
    """
    Remove caracteres inseguros de nomes de arquivo.

    SECURITY FIX: Previne path traversal e nomes problemáticos

    Args:
        name: Nome original

    Returns:
        Nome sanitizado
    """
    sanitized = re.sub(r'[^\w\-.]', '_', name)
    if sanitized != name:
        import sys
        print(f"[CEREBRO] Nome sanitizado: '{name}' → '{sanitized}'", file=sys.stderr)
    return sanitized


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
        # SECURITY FIX: Sanitiza nomes
        project = _sanitize_name(project)
        session_id = _sanitize_name(session_id)

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

        WINDOWS FIX: encoding="utf-8" explícito

        Args:
            project: Nome do projeto
            session_id: ID da sessão

        Returns:
            Dados da sessão ou None se não existir
        """
        # SECURITY FIX: Sanitiza nomes
        project = _sanitize_name(project)
        session_id = _sanitize_name(session_id)

        yaml_path = self.base_path / project / "sessions" / f"{session_id}.yaml"

        if not yaml_path.exists():
            return None

        # WINDOWS FIX: encoding="utf-8" explícito
        return yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    def list_sessions(self, project: str, limit: int = 200, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista todas as sessões de um projeto.

        PERFORMANCE FIX: Adiciona limit e status_filter para evitar carregar tudo

        Args:
            project: Nome do projeto
            limit: Limite de sessões (padrão: 200)
            status_filter: Filtrar por status (opcional)

        Returns:
            Lista de sessões
        """
        # SECURITY FIX: Sanitiza nome do projeto
        project = _sanitize_name(project)

        dir_path = self.base_path / project / "sessions"

        if not dir_path.exists():
            return []

        sessions = []
        # PERFORMANCE: reverse=True para pegar mais recentes primeiro
        for yaml_file in sorted(dir_path.glob("*.yaml"), reverse=True):
            # WINDOWS FIX: encoding="utf-8" explícito
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))

            if status_filter and data.get("status") != status_filter:
                continue

            sessions.append(data)
            if len(sessions) >= limit:
                break

        return sessions

    def write_feature(self, project: str, feature_name: str, data: Dict[str, Any]) -> None:
        """
        Escreve feature em YAML.

        Args:
            project: Nome do projeto
            feature_name: Nome da feature
            data: Dados da feature
        """
        # SECURITY FIX: Sanitiza nomes
        project = _sanitize_name(project)
        feature_name = _sanitize_name(feature_name)

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

        WINDOWS FIX: encoding="utf-8" explícito

        Args:
            project: Nome do projeto
            feature_name: Nome da feature

        Returns:
            Dados da feature ou None se não existir
        """
        # SECURITY FIX: Sanitiza nomes
        project = _sanitize_name(project)
        feature_name = _sanitize_name(feature_name)

        yaml_path = self.base_path / project / "features" / f"{feature_name}.yaml"

        if not yaml_path.exists():
            return None

        # WINDOWS FIX: encoding="utf-8" explícito
        return yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    def list_features(self, project: str, limit: int = 200, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista todas as features de um projeto.

        PERFORMANCE FIX: Adiciona limit e status_filter

        Args:
            project: Nome do projeto
            limit: Limite de features (padrão: 200)
            status_filter: Filtrar por status (opcional)

        Returns:
            Lista de features
        """
        # SECURITY FIX: Sanitiza nome do projeto
        project = _sanitize_name(project)

        dir_path = self.base_path / project / "features"

        if not dir_path.exists():
            return []

        features = []
        for yaml_file in sorted(dir_path.glob("*.yaml"), reverse=True):
            # WINDOWS FIX: encoding="utf-8" explícito
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))

            if status_filter and data.get("status") != status_filter:
                continue

            features.append(data)
            if len(features) >= limit:
                break

        return features

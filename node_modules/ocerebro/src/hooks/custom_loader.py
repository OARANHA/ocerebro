"""Carregador e executor de hooks customizados do Cerebro"""

import importlib.util
import yaml
import signal
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field

from src.core.event_schema import Event


@dataclass
class HookConfig:
    """Configuração de um hook"""
    name: str
    event_type: str
    event_subtype: Optional[str]
    module_path: str
    function: str
    config: Dict[str, Any] = None
    timeout: int = 5  # segundos - configurável por hook


class HooksLoader:
    """
    Carregador dinâmico de hooks customizados via YAML.

    Configuração em hooks.yaml:
    ```yaml
    hooks:
      - name: capture_test_coverage
        event_type: test_result
        module_path: hooks/coverage_hook.py
        function: on_test_result
        config:
          min_coverage: 80

      - name: track_llm_cost
        event_type: tool_call
        event_subtype: llm
        module_path: hooks/cost_hook.py
        function: on_llm_call
    ```
    """

    def __init__(self, config_path: Path):
        """
        Inicializa o HooksLoader.

        Args:
            config_path: Path para hooks.yaml
        """
        self.config_path = config_path
        self.hooks: List[HookConfig] = []
        self._loaded_modules: Dict[str, Any] = {}

        if config_path.exists():
            self._load_config()

    def _load_config(self) -> None:
        """Carrega configuração dos hooks"""
        config = yaml.safe_load(self.config_path.read_text())

        for hook_data in config.get("hooks", []):
            hook = HookConfig(
                name=hook_data.get("name", "unknown"),
                event_type=hook_data.get("event_type", "*"),
                event_subtype=hook_data.get("event_subtype"),
                module_path=hook_data.get("module_path", ""),
                function=hook_data.get("function", "execute"),
                config=hook_data.get("config", {})
            )
            self.hooks.append(hook)

    def _load_module(self, module_path: str) -> Optional[Any]:
        """
        Carrega módulo Python dinamicamente.

        SECURITY FIX: Valida path para evitar path traversal
        WINDOWS FIX: Suporte a paths com espaços

        Args:
            module_path: Path do módulo relativo ao projeto

        Returns:
            Módulo carregado ou None

        Raises:
            PermissionError: Se path estiver fora do diretório permitido
            ValueError: Se arquivo não for .py
        """
        if module_path in self._loaded_modules:
            return self._loaded_modules[module_path]

        # WINDOWS FIX: Usa resolve() para paths absolutos com espaços
        # SECURITY: Resolve path absoluto e verifica se está dentro do diretório permitido
        path = Path(module_path).resolve()
        allowed_root = self.config_path.parent.resolve()

        try:
            # Verifica se o path está dentro do diretório permitido (hooks.yaml location)
            path.relative_to(allowed_root)
        except ValueError:
            raise PermissionError(
                f"Hook path fora do diretório permitido: {path} "
                f"(permitido: {allowed_root})"
            )

        if not path.exists():
            return None

        # SECURITY: Só permite arquivos .py
        if path.suffix != ".py":
            raise ValueError(f"Hook deve ser arquivo .py: {path}")

        # WINDOWS FIX: Usa str(path) em vez de path direto para evitar issues
        spec = importlib.util.spec_from_file_location(
            f"hook_{path.stem}",
            str(path)  # Converte para string para evitar issues no Windows
        )

        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self._loaded_modules[module_path] = module
        return module

    def get_hooks_for_event(self, event: Event) -> List[HookConfig]:
        """
        Retorna hooks que devem ser executados para um evento.

        Args:
            event: Evento para filtrar hooks

        Returns:
            Lista de hooks configurados
        """
        matching = []

        for hook in self.hooks:
            # Filtra por tipo de evento
            if hook.event_type != "*" and hook.event_type != event.event_type.value:
                continue

            # Filtra por subtipo se especificado
            if hook.event_subtype and hook.event_subtype != event.subtype:
                continue

            matching.append(hook)

        return matching

    def load_hook_module(self, hook: HookConfig) -> Optional[Any]:
        """
        Carrega módulo de um hook específico.

        Args:
            hook: Configuração do hook

        Returns:
            Módulo carregado ou None
        """
        return self._load_module(hook.module_path)


class HookRunner:
    """
    Executor de hooks customizados.

    Executa hooks em resposta a eventos do Cerebro.
    """

    def __init__(self, loader: HooksLoader, context: Optional[Dict] = None):
        """
        Inicializa o HookRunner.

        Args:
            loader: HooksLoader configurado
            context: Contexto global para hooks
        """
        self.loader = loader
        self.context = context or {}

    def execute(
        self,
        event: Event,
        hooks: Optional[List[HookConfig]] = None
    ) -> Dict[str, Any]:
        """
        Executa hooks para um evento.

        Args:
            event: Evento que triggerou os hooks
            hooks: Lista específica de hooks (opcional, usa loader se None)

        Returns:
            Resultados de cada hook executado
        """
        if hooks is None:
            hooks = self.loader.get_hooks_for_event(event)

        results = {}

        for hook in hooks:
            try:
                result = self._execute_hook(hook, event)
                results[hook.name] = {
                    "success": True,
                    "result": result
                }
            except Exception as e:
                results[hook.name] = {
                    "success": False,
                    "error": str(e)
                }

        return results

    def _execute_hook(
        self,
        hook: HookConfig,
        event: Event
    ) -> Any:
        """
        Executa um hook específico com timeout.

        HIGH FIX: Adiciona timeout para evitar hooks travados

        Args:
            hook: Configuração do hook
            event: Evento para processar

        Returns:
            Resultado da execução

        Raises:
            TimeoutError: Se hook exceder timeout
        """
        module = self.loader.load_hook_module(hook)

        if module is None:
            raise FileNotFoundError(f"Módulo não encontrado: {hook.module_path}")

        func = getattr(module, hook.function, None)

        if func is None:
            raise AttributeError(
                f"Função {hook.function} não encontrada em {hook.module_path}"
            )

        # TIMEOUT FIX: Executa hook em thread com timeout
        timeout_seconds = (hook.config or {}).get("timeout", hook.timeout)
        result_container = [None]
        error_container = [None]

        def run_hook():
            try:
                result_container[0] = func(
                    event=event,
                    context=self.context,
                    config=hook.config or {}
                )
            except Exception as e:
                error_container[0] = e

        thread = threading.Thread(target=run_hook, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)

        if thread.is_alive():
            raise TimeoutError(
                f"Hook '{hook.name}' excedeu timeout de {timeout_seconds}s"
            )

        if error_container[0] is not None:
            raise error_container[0]

        return result_container[0]

    def register_callback(
        self,
        event_type: str,
        callback: Callable[[Event], Any],
        subtype: Optional[str] = None
    ) -> None:
        """
        Registra callback inline para um tipo de evento.

        Args:
            event_type: Tipo de evento
            callback: Função callback
            subtype: Subtipo de evento (opcional)
        """
        # Cria hook config temporário
        hook = HookConfig(
            name=f"callback_{event_type}",
            event_type=event_type,
            event_subtype=subtype,
            module_path="",
            function=""
        )

        # Adiciona ao loader
        self.loader.hooks.append(hook)

        # Registra callback diretamente
        self._callbacks = getattr(self, "_callbacks", {})
        key = f"{event_type}:{subtype or '*'}"
        self._callbacks[key] = callback

    def execute_callbacks(self, event: Event) -> Dict[str, Any]:
        """
        Executa callbacks registrados para um evento.

        Args:
            event: Evento para processar

        Returns:
            Resultados dos callbacks
        """
        results = {}
        callbacks = getattr(self, "_callbacks", {})

        for key, callback in callbacks.items():
            event_type, subtype = key.split(":")

            # Verifica se callback se aplica
            if event_type != "*" and event_type != event.event_type.value:
                continue
            if subtype != "*" and subtype != event.subtype:
                continue

            try:
                result = callback(event)
                results[key] = {"success": True, "result": result}
            except Exception as e:
                results[key] = {"success": False, "error": str(e)}

        return results


def create_sample_hooks_config(output_path: Path) -> None:
    """
    Cria arquivo de exemplo de configuração de hooks.

    Args:
        output_path: Path para salvar o arquivo
    """
    config = {
        "# Cerebro Hooks Configuration": None,
        "hooks": [
            {
                "name": "test_coverage_check",
                "event_type": "test_result",
                "module_path": "hooks/coverage_hook.py",
                "function": "on_test_result",
                "config": {
                    "min_coverage": 80,
                    "fail_below_threshold": False
                }
            },
            {
                "name": "expensive_operation_log",
                "event_type": "tool_call",
                "event_subtype": "bash",
                "module_path": "hooks/expensive_hook.py",
                "function": "on_expensive_operation",
                "config": {
                    "log_threshold_seconds": 5
                }
            },
            {
                "name": "error_notification",
                "event_type": "error",
                "module_path": "hooks/error_hook.py",
                "function": "on_error",
                "config": {
                    "notify_severity": ["critical", "high"],
                    "channel": "slack"
                }
            }
        ]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

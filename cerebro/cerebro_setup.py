"""Setup Automático do OCerebro

Detecta e configura o Claude Desktop e Claude Code automaticamente.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def find_all_claude_configs() -> dict:
    """Encontra todas as configurações do Claude (Desktop e Code).

    Returns:
        dict com chaves "desktop" e "code", cada uma contendo Path | None
    """
    result = {"desktop": None, "code": None}

    # Claude Desktop: claude_desktop.json
    desktop_locations = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        desktop_locations.extend([
            Path(appdata) / "Claude" / "claude_desktop.json",
            Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop.json",
            Path.home() / ".claude" / "claude_desktop.json",
        ])
    elif sys.platform == "darwin":
        desktop_locations.extend([
            Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop.json",
            Path.home() / ".claude" / "claude_desktop.json",
        ])
    elif sys.platform == "linux":
        xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        desktop_locations.extend([
            Path(xdg_config) / "Claude" / "claude_desktop.json",
            Path.home() / ".claude" / "claude_desktop.json",
        ])

    # Claude Code: settings.json
    code_locations = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        code_locations.extend([
            Path(appdata) / "Claude" / "settings.json",
            Path.home() / "AppData" / "Roaming" / "Claude" / "settings.json",
        ])
    elif sys.platform == "darwin":
        code_locations.extend([
            Path.home() / "Library" / "Application Support" / "Claude" / "settings.json",
        ])
    elif sys.platform == "linux":
        xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        code_locations.extend([
            Path(xdg_config) / "Claude" / "settings.json",
        ])

    # Universal (funciona para ambos)
    universal_claude = Path.home() / ".claude"
    if universal_claude.exists():
        if result["desktop"] is None and (universal_claude / "claude_desktop.json").exists():
            result["desktop"] = universal_claude / "claude_desktop.json"
        if result["code"] is None and (universal_claude / "settings.json").exists():
            result["code"] = universal_claude / "settings.json"

    # Encontra primeiro desktop que existe
    if result["desktop"] is None:
        for loc in desktop_locations:
            if loc.exists():
                result["desktop"] = loc
                break
        else:
            # Nenhum existe, retorna o primeiro para criar
            result["desktop"] = desktop_locations[0] if desktop_locations else None

    # Encontra primeiro code que existe
    if result["code"] is None:
        for loc in code_locations:
            if loc.exists():
                result["code"] = loc
                break
        else:
            # Nenhum existe, retorna o primeiro para criar
            result["code"] = code_locations[0] if code_locations else None

    return result


def find_claude_desktop_config() -> Path | None:
    """Encontra o arquivo claude_desktop.json em várias localizações.

    Legado: use find_all_claude_configs() para suporte completo.
    """
    configs = find_all_claude_configs()
    return configs.get("desktop")


def get_ocerebro_path() -> Path:
    """Retorna o caminho absoluto do OCerebro instalado"""
    # Tenta encontrar o package instalado via pip
    try:
        import cerebro
        cerebro_path = Path(cerebro.__file__).parent
        return cerebro_path.resolve()
    except ImportError:
        pass

    # Fallback: usa pip show para encontrar o Location
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "ocerebro"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Location:"):
                    return Path(line.split(":", 1)[1].strip())
    except Exception:
        pass

    # Último fallback: usa o path do próprio arquivo
    return Path(__file__).parent.resolve()


def generate_mcp_config(ocerebro_path: Path) -> dict:
    """Gera configuração MCP para o OCerebro com suporte robusto a paths.

    SECURITY: Não salva API keys no config file.
    As variáveis de ambiente são herdadas do sistema.
    Configure no seu shell: ~/.bashrc ou ~/.zshrc
    """

    # Determina o comando Python
    python_cmd = sys.executable

    # Estratégia 1: usa python -m ocerebro.mcp (robusto para pip install)
    mcp_config = {
        "command": python_cmd,
        "args": ["-m", "src.mcp.server"],
        "cwd": str(ocerebro_path.parent),
    }

    # Estratégia 2: path direto se arquivo existe
    mcp_server = ocerebro_path / "src" / "mcp" / "server.py"
    if not mcp_server.exists():
        mcp_server = ocerebro_path.parent / "src" / "mcp" / "server.py"

    if mcp_server.exists():
        mcp_config["args"] = [str(mcp_server)]

    # SECURITY: NÃO salvar API keys no config
    mcp_config["env"] = {}

    return {
        "mcpServers": {
            "ocerebro": mcp_config
        }
    }


def backup_config(config_path: Path) -> Path | None:
    """Cria backup do arquivo de configuração"""
    if not config_path.exists():
        return None

    backup_path = config_path.with_suffix(".json.bak")
    backup_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[OK] Backup criado: {backup_path}")
    return backup_path


def merge_configs(existing: dict, new: dict) -> dict:
    """Faz merge das configurações MCP"""
    result = existing.copy()

    if "mcpServers" not in result:
        result["mcpServers"] = {}

    if "mcpServers" in new:
        for name, config in new["mcpServers"].items():
            result["mcpServers"][name] = config

    return result


def setup_slash_commands(project_path: Path) -> bool:
    """Cria slash commands /cerebro no .claude/commands/ do projeto."""

    commands_dir = project_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    dream_cmd = commands_dir / "cerebro-dream.md"
    if not dream_cmd.exists():
        dream_cmd.write_text("""---
description: Extrair memórias da sessão atual
---
Execute: ocerebro dream --since 7 --apply
Mostre o relatório completo do que foi salvo.
""", encoding="utf-8")
        print(f"[OK] Slash command criado: {dream_cmd}")

    status_cmd = commands_dir / "cerebro-status.md"
    if not status_cmd.exists():
        status_cmd.write_text("""---
description: Ver status da memória do projeto
---
Execute: ocerebro status
Liste quantas memórias existem por tipo.
""", encoding="utf-8")
        print(f"[OK] Slash command criado: {status_cmd}")

    gc_cmd = commands_dir / "cerebro-gc.md"
    if not gc_cmd.exists():
        gc_cmd.write_text("""---
description: Limpeza de memórias antigas
---
Execute: ocerebro gc --threshold 30
Mostre o que será arquivado antes de confirmar.
""", encoding="utf-8")
        print(f"[OK] Slash command criado: {gc_cmd}")

    return True


def find_python_with_ocerebro() -> str:
    """Encontra o executável Python onde ocerebro está instalado."""
    candidates = []

    try:
        import ocerebro  # noqa: F401
        candidates.append(sys.executable)
    except ImportError:
        pass

    for cmd in ["python", "python3"]:
        try:
            result = subprocess.run(
                [cmd, "-c", "import ocerebro; print('ok')"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                result_path = subprocess.run(
                    [cmd, "-c", "import sys; print(sys.executable)"],
                    capture_output=True,
                    text=True
                )
                if result_path.returncode == 0:
                    candidates.append(result_path.stdout.strip())
        except Exception:
            continue

    return candidates[0] if candidates else sys.executable


def get_claude_code_settings_path() -> Path | None:
    """Encontra o settings.json do Claude Code."""
    home_settings = Path.home() / ".claude" / "settings.json"
    if home_settings.exists():
        return home_settings

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            appdata_settings = Path(appdata) / "Claude" / "settings.json"
            if appdata_settings.exists():
                return appdata_settings

    return home_settings


def get_claude_desktop_settings_path() -> Path | None:
    """Encontra o claude_desktop.json do Claude Desktop."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "Claude" / "claude_desktop.json"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop.json"
    return None


def setup_claude(auto: bool = True) -> bool:
    """Configura MCP Server automaticamente."""
    print("=" * 60)
    print("OCerebro - Configurando MCP Server")
    print("=" * 60)
    print()

    python_cmd = find_python_with_ocerebro()
    print(f"[1/5] Python detectado: {python_cmd}")

    mcp_config = {
        "command": python_cmd,
        "args": ["-m", "src.mcp.server"],
        "cwd": str(Path(python_cmd).parent / "Lib" / "site-packages"),
        "env": {}
    }
    print(f"[2/5] Configuração MCP gerada")

    configured = []
    errors = []

    claude_code_path = get_claude_code_settings_path()
    claude_desktop_path = get_claude_desktop_settings_path()

    if auto:
        targets = []
        if claude_code_path and claude_code_path.exists():
            targets.append(("code", claude_code_path))
        if claude_desktop_path and claude_desktop_path.exists():
            targets.append(("desktop", claude_desktop_path))
        if not targets:
            targets.append(("code", claude_code_path))
    else:
        print("Qual versão do Claude você usa?")
        print("  1. Claude Desktop")
        print("  2. Claude Code (claude.ai/code)")
        print("  3. Ambos")
        choice = input("\nEscolha [1/2/3] (padrão: 2): ").strip() or "2"

        targets = []
        if choice in ["1", "3"] and claude_desktop_path:
            targets.append(("desktop", claude_desktop_path))
        if choice in ["2", "3"] and claude_code_path:
            targets.append(("code", claude_code_path))
        if not targets:
            targets.append(("code", claude_code_path))

    for target_type, config_path in targets:
        print(f"[3/5] Configurando {target_type}...")

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)

            existing_config = {}
            if config_path.exists():
                try:
                    existing_config = json.loads(config_path.read_text(encoding="utf-8"))
                    backup_config(config_path)
                except json.JSONDecodeError:
                    print(f"  Aviso: Config existente inválida, criando nova")

            if "mcpServers" not in existing_config:
                existing_config["mcpServers"] = {}
            existing_config["mcpServers"]["ocerebro"] = mcp_config

            if "mcp" not in existing_config:
                existing_config["mcp"] = {}
            existing_config["mcp"]["enabled"] = True

            config_path.write_text(
                json.dumps(existing_config, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

            configured.append(target_type)
            print(f"  [OK] {target_type}: {config_path}")

        except Exception as e:
            errors.append(f"{target_type}: {e}")
            print(f"  [ERRO] {target_type}: {e}")

    print()
    print("=" * 60)
    print("SETUP CONCLUÍDO!")
    print("=" * 60)

    if configured:
        print(f"\n[OK] MCP Server configurado em: {', '.join(configured)}")
        print("\nPróximos passos:")
        print("  1. Reinicie o Claude (feche e abra novamente)")
        print("  2. As ferramentas estarão disponíveis:")
        for tool in ["cerebro_memory", "cerebro_search", "cerebro_checkpoint",
                     "cerebro_promote", "cerebro_status", "cerebro_hooks",
                     "cerebro_diff", "cerebro_dream", "cerebro_remember", "cerebro_gc"]:
            print(f"     - {tool}")
        print("\nPara testar, digite no Claude:")
        print("  /help  (deve mostrar cerebro_*)")
        print("  ou: Use cerebro_status")
    else:
        print("\n[ERRO] Não foi possível configurar automaticamente.")
        print("Configure manualmente adicionando ao seu settings.json:")
        print(json.dumps({"mcpServers": {"ocerebro": mcp_config}}, indent=2))

    if errors:
        print(f"\nErros encontrados: {len(errors)}")
        for err in errors:
            print(f"  - {err}")

    print()
    return len(configured) > 0


def setup_hooks(project_path: Path | None = None) -> bool:
    """Cria arquivo de exemplo hooks.yaml no projeto"""

    if project_path is None:
        project_path = Path.cwd()

    hooks_yaml = project_path / "hooks.yaml"

    if hooks_yaml.exists():
        print(f" hooks.yaml já existe em {project_path}")
        return False

    example_config = """# OCerebro Hooks Configuration
hooks:
  - name: error_notification
    event_type: error
    module_path: hooks/error_hook.py
    function: on_error
    config:
      notify_severity: [\"critical\", \"high\"]

  - name: llm_cost_tracker
    event_type: tool_call
    event_subtype: llm
    module_path: hooks/cost_hook.py
    function: on_llm_call
    config:
      monthly_budget: 100.0
      alert_at_percentage: 80
"""

    hooks_yaml.write_text(example_config, encoding="utf-8")

    hooks_dir = project_path / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "__init__.py").write_text('"""Hooks customizados do projeto"""', encoding="utf-8")

    print(f"[OK] hooks.yaml criado em {project_path}")
    print(f"[OK] Diretório hooks/ criado")

    return True


def setup_ocerebro_dir(project_path: Path | None = None) -> bool:
    """Cria diretório .ocerebro no projeto."""

    if project_path is None:
        project_path = Path.cwd()

    project_path = project_path.resolve()
    home = Path.home().resolve()
    cwd = Path.cwd().resolve()

    if not (str(project_path).startswith(str(home)) or
            str(project_path).startswith(str(cwd))):
        print(f"❌ Erro: path '{project_path}' fora do diretório permitido.")
        return False

    ocerebro_dir = project_path / ".ocerebro"

    if ocerebro_dir.exists():
        print(f"[OK] Diretório .ocerebro já existe")
        return True

    (ocerebro_dir / "raw").mkdir(parents=True)
    (ocerebro_dir / "working").mkdir(parents=True)
    (ocerebro_dir / "official").mkdir(parents=True)
    (ocerebro_dir / "index").mkdir(parents=True)
    (ocerebro_dir / "config").mkdir(parents=True)

    gitignore = ocerebro_dir / ".gitignore"
    gitignore.write_text("raw/\nworking/\nindex/\nconfig/local.yaml\n", encoding="utf-8")

    print(f"[OK] Diretório .ocerebro criado em {project_path}")
    print(f"   - raw/ (eventos brutos)")
    print(f"   - working/ (rascunhos)")
    print(f"   - official/ (memória permanente)")
    print(f"   - index/ (banco de dados)")
    print(f"   - config/ (configurações)")

    return True


def main():
    """Função principal de setup"""

    if len(sys.argv) > 1:
        subcommand = sys.argv[1]

        if subcommand == "claude":
            success = setup_claude(auto=True)
            sys.exit(0 if success else 1)

        elif subcommand == "hooks":
            project = Path(sys.argv[2]) if len(sys.argv) > 2 else None
            success = setup_hooks(project)
            sys.exit(0 if success else 1)

        elif subcommand == "init":
            project = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
            setup_ocerebro_dir(project)
            setup_hooks(project)
            setup_slash_commands(project)
            setup_claude(auto=True)
            sys.exit(0)

        else:
            print(f"Subcomando desconhecido: {subcommand}")
            sys.exit(1)

    print("Executando setup completo...")
    print()
    setup_ocerebro_dir()
    setup_hooks()
    setup_claude(auto=True)


if __name__ == "__main__":
    main()

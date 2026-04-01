"""Setup Automático do OCerebro

Detecta e configura o Claude Desktop e Claude Code automaticamente.
"""

import json
import os
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
    # Tenta encontrar o package instalado
    import ocerebro
    ocerebro_path = Path(ocerebro.__file__).parent
    return ocerebro_path.resolve()


def generate_mcp_config(ocerebro_path: Path) -> dict:
    """Gera configuração MCP para o OCerebro com suporte robusto a paths e env vars."""

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

    # Injeta variáveis de ambiente do usuário
    env_vars = {}
    for key in ["ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY",
                "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
                "CEREBRO_MODEL"]:
        val = os.environ.get(key)
        if val:
            env_vars[key] = val

    mcp_config["env"] = env_vars

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

    # Adiciona/Atualiza servidor ocerebro
    if "mcpServers" in new:
        for name, config in new["mcpServers"].items():
            result["mcpServers"][name] = config

    return result


def setup_slash_commands(project_path: Path) -> bool:
    """Cria slash commands /cerebro no .claude/commands/ do projeto."""

    commands_dir = project_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    # cerebro-dream.md
    dream_cmd = commands_dir / "cerebro-dream.md"
    if not dream_cmd.exists():
        dream_cmd.write_text("""---
description: Extrair memórias da sessão atual
---
Execute: ocerebro dream --since 7 --apply
Mostre o relatório completo do que foi salvo.
""", encoding="utf-8")
        print(f"[OK] Slash command criado: {dream_cmd}")

    # cerebro-status.md
    status_cmd = commands_dir / "cerebro-status.md"
    if not status_cmd.exists():
        status_cmd.write_text("""---
description: Ver status da memória do projeto
---
Execute: ocerebro status
Liste quantas memórias existem por tipo.
""", encoding="utf-8")
        print(f"[OK] Slash command criado: {status_cmd}")

    # cerebro-gc.md
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


def setup_claude_desktop() -> bool:
    """Configura o Claude Desktop ou Claude Code automaticamente."""

    print("=" * 60)
    print("OCerebro - Setup Automático")
    print("=" * 60)
    print()

    # Encontra todas as configurações
    configs = find_all_claude_configs()

    # Pergunta qual versão o usuário usa
    print("Qual versão do Claude você usa?")
    print("  1. Claude Desktop")
    print("  2. Claude Code (claude.ai/code)")
    print("  3. Ambos")
    choice = input("\nEscolha [1/2/3] (padrão: 2): ").strip() or "2"

    # Pega caminho do OCerebro
    ocerebro_path = get_ocerebro_path()
    print(f"\nOCerebro instalado: {ocerebro_path}")

    # Gera nova configuração
    new_config = generate_mcp_config(ocerebro_path)

    configured = []

    # Configura Claude Desktop se escolhido
    if choice in ["1", "3"]:
        config_path = configs.get("desktop")
        if config_path:
            print(f"\nConfig do Claude Desktop: {config_path}")
            config_path.parent.mkdir(parents=True, exist_ok=True)

            existing_config = {}
            if config_path.exists():
                print(f"Configuração existente encontrada")
                backup_config(config_path)
                try:
                    existing_config = json.loads(config_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as e:
                    print(f"Erro ao ler configuração existente: {e}")
                    existing_config = {}

            merged_config = merge_configs(existing_config, new_config)
            config_path.write_text(
                json.dumps(merged_config, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            configured.append("Claude Desktop")

    # Configura Claude Code se escolhido
    if choice in ["2", "3"]:
        config_path = configs.get("code")
        if config_path:
            print(f"\nConfig do Claude Code: {config_path}")
            config_path.parent.mkdir(parents=True, exist_ok=True)

            existing_config = {}
            if config_path.exists():
                print(f"Configuração existente encontrada")
                backup_config(config_path)
                try:
                    existing_config = json.loads(config_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as e:
                    print(f"Erro ao ler configuração existente: {e}")
                    existing_config = {}

            merged_config = merge_configs(existing_config, new_config)
            config_path.write_text(
                json.dumps(merged_config, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            configured.append("Claude Code")

    print()
    print("[OK] OCerebro configurado em:", ", ".join(configured) if configured else "Nenhum")
    print()
    print("Próximos passos:")
    print("  1. Reinicie o Claude (Desktop ou Code)")
    print("  2. As ferramentas do OCerebro estarão disponíveis:")
    print("     - ocerebro_memory")
    print("     - ocerebro_search")
    print("     - ocerebro_checkpoint")
    print("     - ocerebro_promote")
    print("     - ocerebro_status")
    print("     - ocerebro_hooks")
    print("     - ocerebro_diff")
    print("     - ocerebro_dream")
    print("     - ocerebro_remember")
    print("     - ocerebro_gc")
    print()
    print("=" * 60)

    return True


def setup_hooks(project_path: Path | None = None) -> bool:
    """Cria arquivo de exemplo hooks.yaml no projeto"""

    if project_path is None:
        project_path = Path.cwd()

    hooks_yaml = project_path / "hooks.yaml"

    if hooks_yaml.exists():
        print(f" hooks.yaml já existe em {project_path}")
        return False

    example_config = """# OCerebro Hooks Configuration
# Docs: https://github.com/OARANHA/ocerebro/blob/main/docs/HOOKS_GUIDE.md

hooks:
  # Exemplo: Notificação de erros críticos
  - name: error_notification
    event_type: error
    module_path: hooks/error_hook.py
    function: on_error
    config:
      notify_severity: ["critical", "high"]

  # Exemplo: Tracker de custo LLM
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

    # Cria diretório hooks/ com __init__.py
    hooks_dir = project_path / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "__init__.py").write_text('"""Hooks customizados do projeto"""', encoding="utf-8")

    print(f"[OK] hooks.yaml criado em {project_path}")
    print(f"[OK] Diretório hooks/ criado")

    return True


def setup_ocerebro_dir(project_path: Path | None = None) -> bool:
    """Cria diretório .ocerebro no projeto"""

    if project_path is None:
        project_path = Path.cwd()

    ocerebro_dir = project_path / ".ocerebro"

    if ocerebro_dir.exists():
        print(f"[OK] Diretório .ocerebro já existe")
        return True

    # Cria estrutura
    (ocerebro_dir / "raw").mkdir(parents=True)
    (ocerebro_dir / "working").mkdir(parents=True)
    (ocerebro_dir / "official").mkdir(parents=True)
    (ocerebro_dir / "index").mkdir(parents=True)
    (ocerebro_dir / "config").mkdir(parents=True)

    # Cria .gitignore dentro do .ocerebro
    gitignore = ocerebro_dir / ".gitignore"
    gitignore.write_text("""# Raw events (muito grandes)
raw/

# Working drafts (opcional sincronizar)
working/

# Index databases (regenerado automaticamente)
index/

# Config local
config/local.yaml
""", encoding="utf-8")

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
            success = setup_claude_desktop()
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
            print()
            print("Setup completo! Agora execute:")
            print("  ocerebro setup claude")
            sys.exit(0)

        else:
            print(f"Subcomando desconhecido: {subcommand}")
            sys.exit(1)

    # Setup completo padrão
    print("Executando setup completo...")
    print()

    setup_ocerebro_dir()
    setup_hooks()
    setup_claude_desktop()


if __name__ == "__main__":
    main()

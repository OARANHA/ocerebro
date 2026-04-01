"""Setup automtico do Cerebro

Detecta e configura o Claude Desktop automaticamente.
"""

import json
import os
import sys
from pathlib import Path


def find_claude_desktop_config() -> Path | None:
    """Encontra o arquivo claude_desktop.json em vrias localizaes"""

    locations = []

    # Windows
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        locations.extend([
            Path(appdata) / "Claude" / "claude_desktop.json",
            Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop.json",
            Path.home() / ".claude" / "claude_desktop.json",
        ])

    # macOS
    elif sys.platform == "darwin":
        locations.extend([
            Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop.json",
            Path.home() / ".claude" / "claude_desktop.json",
        ])

    # Linux
    elif sys.platform == "linux":
        xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        locations.extend([
            Path(xdg_config) / "Claude" / "claude_desktop.json",
            Path.home() / ".claude" / "claude_desktop.json",
        ])

    # Verifica qual existe
    for loc in locations:
        if loc.parent.exists():
            return loc

    # Retorna o primeiro mesmo se no existe (criamos o arquivo)
    return locations[0] if locations else None


def get_cerebro_path() -> Path:
    """Retorna o caminho absoluto do Cerebro instalado"""
    # Tenta encontrar o package instalado
    import cerebro
    cerebro_path = Path(cerebro.__file__).parent
    return cerebro_path.resolve()


def generate_mcp_config(cerebro_path: Path) -> dict:
    """Gera configurao MCP para o Cerebro"""

    # Determina o comando Python
    python_cmd = sys.executable

    # Caminho do servidor MCP
    mcp_server = cerebro_path / "src" / "mcp" / "server.py"

    if not mcp_server.exists():
        # Tenta encontrar em outras localizaes
        mcp_server = cerebro_path.parent / "src" / "mcp" / "server.py"

    return {
        "mcpServers": {
            "cerebro": {
                "command": python_cmd,
                "args": [str(mcp_server)],
                "cwd": str(cerebro_path.parent),
                "env": {}
            }
        }
    }


def backup_config(config_path: Path) -> Path | None:
    """Cria backup do arquivo de configurao"""
    if not config_path.exists():
        return None

    backup_path = config_path.with_suffix(".json.bak")
    backup_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[OK] Backup criado: {backup_path}")
    return backup_path


def merge_configs(existing: dict, new: dict) -> dict:
    """Faz merge das configuraes MCP"""
    result = existing.copy()

    if "mcpServers" not in result:
        result["mcpServers"] = {}

    # Adiciona/Atualiza servidor cerebro
    if "mcpServers" in new:
        for name, config in new["mcpServers"].items():
            result["mcpServers"][name] = config

    return result


def setup_claude_desktop() -> bool:
    """Configura o Claude Desktop automaticamente"""

    print("=" * 60)
    print("Cerebro - Setup Automtico")
    print("=" * 60)
    print()

    # Encontra configurao do Claude
    config_path = find_claude_desktop_config()

    if config_path is None:
        print(" No foi possvel localizar o Claude Desktop.")
        print()
        print("Por favor, instale o Claude Desktop primeiro:")
        print("  https://claude.ai/download")
        return False

    print(f" Config do Claude: {config_path}")

    # Garante que o diretrio existe
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Pega caminho do Cerebro
    cerebro_path = get_cerebro_path()
    print(f" Cerebro instalado: {cerebro_path}")

    # Gera nova configurao
    new_config = generate_mcp_config(cerebro_path)

    # L configurao existente se houver
    existing_config = {}
    if config_path.exists():
        print(f" Configurao existente encontrada")
        backup_config(config_path)
        try:
            existing_config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f" Erro ao ler configurao existente: {e}")
            existing_config = {}

    # Faz merge
    merged_config = merge_configs(existing_config, new_config)

    # Escreve nova configurao
    config_path.write_text(
        json.dumps(merged_config, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print()
    print("[OK] Cerebro configurado no Claude Desktop!")
    print()
    print("Prximos passos:")
    print("  1. Reinicie o Claude Desktop")
    print("  2. As ferramentas do Cerebro estaro disponveis:")
    print("     - cerebro_memory")
    print("     - cerebro_search")
    print("     - cerebro_checkpoint")
    print("     - cerebro_promote")
    print("     - cerebro_status")
    print("     - cerebro_hooks")
    print()
    print("=" * 60)

    return True


def setup_hooks(project_path: Path | None = None) -> bool:
    """Cria arquivo de exemplo hooks.yaml no projeto"""

    if project_path is None:
        project_path = Path.cwd()

    hooks_yaml = project_path / "hooks.yaml"

    if hooks_yaml.exists():
        print(f" hooks.yaml j existe em {project_path}")
        return False

    example_config = """# Cerebro Hooks Configuration
# Docs: https://github.com/OARANHA/cerebro/blob/main/docs/HOOKS_GUIDE.md

hooks:
  # Exemplo: Notificao de erros crticos
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

    # Cria diretrio hooks/ com __init__.py
    hooks_dir = project_path / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "__init__.py").write_text('"""Hooks customizados do projeto"""', encoding="utf-8")

    print(f"[OK] hooks.yaml criado em {project_path}")
    print(f"[OK] Diretrio hooks/ criado")

    return True


def setup_cerebro_dir(project_path: Path | None = None) -> bool:
    """Cria diretrio .cerebro no projeto"""

    if project_path is None:
        project_path = Path.cwd()

    cerebro_dir = project_path / ".cerebro"

    if cerebro_dir.exists():
        print(f"[OK] Diretrio .cerebro j existe")
        return True

    # Cria estrutura
    (cerebro_dir / "raw").mkdir(parents=True)
    (cerebro_dir / "working").mkdir(parents=True)
    (cerebro_dir / "official").mkdir(parents=True)
    (cerebro_dir / "index").mkdir(parents=True)
    (cerebro_dir / "config").mkdir(parents=True)

    # Cria .gitignore dentro do .cerebro
    gitignore = cerebro_dir / ".gitignore"
    gitignore.write_text("""# Raw events (muito grandes)
raw/

# Working drafts (opcional sincronizar)
working/

# Index databases (regenerado automaticamente)
index/

# Config local
config/local.yaml
""", encoding="utf-8")

    print(f"[OK] Diretrio .cerebro criado em {project_path}")
    print(f"   - raw/ (eventos brutos)")
    print(f"   - working/ (rascunhos)")
    print(f"   - official/ (memria permanente)")
    print(f"   - index/ (banco de dados)")
    print(f"   - config/ (configuraes)")

    return True


def main():
    """Funo principal de setup"""

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
            setup_cerebro_dir(project)
            setup_hooks(project)
            print()
            print("Setup completo! Agora execute:")
            print("  cerebro setup claude")
            sys.exit(0)

        else:
            print(f"Subcomando desconhecido: {subcommand}")
            sys.exit(1)

    # Setup completo padro
    print("Executando setup completo...")
    print()

    setup_cerebro_dir()
    setup_hooks()
    setup_claude_desktop()


if __name__ == "__main__":
    main()

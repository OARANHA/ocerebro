"""Setup Automático do OCerebro — zero-fricção.

Fluxo:
  ocerebro init        → cria .ocerebro/ + hooks.yaml + registra MCP
  ocerebro setup claude → só registra MCP (Claude Desktop e/ou Code)
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional


# ── Detecta Python em uso ─────────────────────────────────────────────────────

def get_python_executable() -> str:
    """Retorna o executável Python correto (mesmo usado pelo pip install)."""
    return sys.executable


# ── Localiza configs do Claude ────────────────────────────────────────────────

def find_claude_configs() -> dict:
    """Encontra todos os arquivos de config do Claude no sistema.

    Ordem de prioridade:
      1. ~/.claude.json          ← Claude Code (principal)
      2. ~/.claude/settings.json ← Claude Code (alternativo)
      3. %APPDATA%/Claude/claude_desktop_config.json  ← Claude Desktop (Win)
      4. ~/Library/.../claude_desktop_config.json     ← Claude Desktop (Mac)
    """
    result = {"code": None, "desktop": None}

    home = Path.home()

    # Claude Code — ~/.claude.json (formato principal atual)
    claude_json = home / ".claude.json"
    if claude_json.exists():
        result["code"] = claude_json

    # Claude Code — ~/.claude/settings.json (alternativo)
    if result["code"] is None:
        settings = home / ".claude" / "settings.json"
        if settings.exists():
            result["code"] = settings

    # Claude Code — fallback: cria ~/.claude.json se nenhum existe
    if result["code"] is None:
        result["code"] = claude_json  # vai criar depois

    # Claude Desktop
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        desktop = Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "darwin":
        desktop = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
        desktop = Path(xdg) / "Claude" / "claude_desktop_config.json"

    if desktop.exists():
        result["desktop"] = desktop

    return result


# ── Gera bloco MCP ────────────────────────────────────────────────────────────

def generate_mcp_entry() -> dict:
    """Gera a entrada MCP usando o Python ATUAL (sys.executable).

    Isso garante que Claude Code usa o mesmo Python onde ocerebro está instalado,
    independente de C:\\Python313 ou PATH.
    """
    python_exe = get_python_executable()

    # Tenta encontrar o server.py instalado
    try:
        import src.mcp.server as _s
        server_path = str(Path(_s.__file__).resolve())
        args = [server_path]
    except ImportError:
        # Fallback: usa -m
        args = ["-m", "src.mcp.server"]

    return {
        "command": python_exe,
        "args": args,
        "env": {}
    }


# ── Merge seguro de JSON ──────────────────────────────────────────────────────

def read_json_safe(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"⚠️  {path} com JSON inválido — será sobrescrito.")
        return {}


def write_mcp_config(config_path: Path, mcp_entry: dict) -> bool:
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing = read_json_safe(config_path)

    if "mcpServers" not in existing:
        existing["mcpServers"] = {}

    existing["mcpServers"]["ocerebro"] = mcp_entry

    # Backup se já existia
    if config_path.exists():
        bak = config_path.with_suffix(".bak")
        bak.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")

    config_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return True


# ── Setup principal ───────────────────────────────────────────────────────────

def setup_claude_desktop(silent: bool = False) -> bool:
    """Registra OCerebro como MCP em Claude Code e/ou Desktop.

    Detecta automaticamente quais configs existem.
    Se nenhuma existir, cria ~/.claude.json para Claude Code.
    """
    configs = find_claude_configs()
    mcp_entry = generate_mcp_entry()
    registered = []

    # Sempre configura Claude Code
    code_path = configs["code"]
    if code_path:
        write_mcp_config(code_path, mcp_entry)
        registered.append(f"Claude Code ({code_path})")

    # Configura Claude Desktop se existir
    if configs["desktop"]:
        write_mcp_config(configs["desktop"], mcp_entry)
        registered.append(f"Claude Desktop ({configs['desktop']})")

    if not silent:
        print()
        for r in registered:
            print(f"[OK] MCP registrado: {r}")
        print()
        print(f"[OK] Python usado: {get_python_executable()}")
        print()
        print("⚠️  Reinicie o Claude Code para ativar as ferramentas.")
        print()
        print("Ferramentas disponíveis após reiniciar:")
        tools = [
            "ocerebro_memory   → lê memória do projeto",
            "ocerebro_search   → busca semântica",
            "ocerebro_checkpoint → salva checkpoint",
            "ocerebro_status   → status do sistema",
            "ocerebro_dream    → extrai memórias da sessão",
            "ocerebro_gc       → garbage collection",
        ]
        for t in tools:
            print(f"  • {t}")

    return True


def setup_hooks(project_path: Optional[Path] = None) -> bool:
    if project_path is None:
        project_path = Path.cwd()

    hooks_yaml = project_path / "hooks.yaml"
    if hooks_yaml.exists():
        return False

    hooks_yaml.write_text("""\
# OCerebro Hooks Configuration
hooks:
  - name: error_notification
    event_type: error
    module_path: hooks/error_hook.py
    function: on_error
    config:
      notify_severity: ["critical", "high"]

  - name: llm_cost_tracker
    event_type: tool_call
    event_subtype: llm
    module_path: hooks/cost_hook.py
    function: on_llm_call
    config:
      monthly_budget: 100.0
      alert_at_percentage: 80
""", encoding="utf-8")

    hooks_dir = project_path / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "__init__.py").write_text('"""Hooks customizados do projeto"""', encoding="utf-8")

    print(f"[OK] hooks.yaml criado em {project_path}")
    print(f"[OK] Diretório hooks/ criado")
    return True


def setup_cerebro_dir(project_path: Optional[Path] = None) -> bool:
    if project_path is None:
        project_path = Path.cwd()

    project_path = project_path.resolve()
    ocerebro_dir = project_path / ".ocerebro"

    if ocerebro_dir.exists():
        print(f"[OK] Diretório .ocerebro já existe")
        return True

    for sub in ["raw", "working", "official", "index", "config"]:
        (ocerebro_dir / sub).mkdir(parents=True)

    (ocerebro_dir / ".gitignore").write_text(
        "raw/\nworking/\nindex/\nconfig/local.yaml\n",
        encoding="utf-8"
    )

    print(f"[OK] Diretório .ocerebro criado em {project_path}")
    print(f"   - raw/ (eventos brutos)")
    print(f"   - working/ (rascunhos)")
    print(f"   - official/ (memória permanente)")
    print(f"   - index/ (banco de dados)")
    print(f"   - config/ (configurações)")
    return True


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    sub = sys.argv[1] if len(sys.argv) > 1 else None
    project = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if sub == "claude":
        setup_claude_desktop()
    elif sub == "hooks":
        setup_hooks(project)
    elif sub == "init" or sub is None:
        setup_cerebro_dir(project or Path.cwd())
        setup_hooks(project or Path.cwd())
        setup_claude_desktop(silent=False)
    else:
        print(f"Subcomando desconhecido: {sub}")
        sys.exit(1)


if __name__ == "__main__":
    main()

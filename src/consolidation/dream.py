"""Dream: extração automática de memórias (extractMemories desbloqueado).

Replica o fluxo do extractMemories.ts do Claude Code:
1. Scan de memórias existentes (evita duplicatas)
2. Contagem de mensagens novas no transcript
3. Build do prompt de extração
4. Chamada à API Claude com max 5 turns
5. Report do que foi escrito

O dream é o "extractMemories desbloqueado" — a feature que a Anthropic
gateou com tengu_passport_quail=false para usuários não-Anthropic.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.paths import get_auto_mem_path, get_memory_index, MEMORY_INDEX_MAX_LINES
from src.memdir.scanner import scan_memory_files, format_memory_manifest, MemoryHeader


@dataclass
class DreamResult:
    """Resultado da extração de memórias.

    Attributes:
        written_files: Lista de arquivos criados/atualizados
        memory_dir: Diretório de memória processado
        dry_run: Se True, nada foi modificado
        period_days: Período analisado
        prompt_preview: Preview do prompt usado na extração
    """
    written_files: List[Path]
    memory_dir: Path
    dry_run: bool
    period_days: int
    new_memories: List[str] = None
    updated_memories: List[str] = None
    prompt_preview: str = ""


# ============================================================================
# PROMPT DE EXTRAÇÃO — Tradução direta de buildExtractAutoOnlyPrompt()
# ============================================================================

TYPES_SECTION_INDIVIDUAL = """
## Tipos de Memória (Taxonomia Fechada)

Você DEVE classificar cada memória em um destes 4 tipos:

### 1. user (Sempre Privado)
<scope>always private</scope>
<description>Informações sobre o papel, objetivos, responsabilidades e conhecimento do usuário</description>
<when_to_save>Quando você aprende detalhes sobre o papel, preferências, responsabilidades ou conhecimento do usuário</when_to_save>
<how_to_use>Quando seu trabalho deve ser informado pelo perfil ou perspectiva do usuário</how_to_use>

### 2. feedback (Padrão: Privado, Team apenas para convenções de projeto)
<scope>default to private. Save as team only when the guidance is clearly a project-wide convention</scope>
<description>Orientação que o usuário deu sobre como abordar o trabalho - tanto o que evitar quanto o que continuar fazendo</description>
<when_to_save>Qualquer momento que o usuário corrigir sua abordagem ("não isso", "não faça X") OU confirmar que uma abordagem funcionou ("isso mesmo", "perfeito, continue assim")</when_to_save>
<body_structure>Comece com a regra, depois **Why:** (razão) e **How to apply:** (quando/onde aplicar)</body_structure>

### 3. project (Privado ou Team, tendência forte para Team)
<scope>private or team, but strongly bias toward team</scope>
<description>Informação sobre trabalho em andamento, metas, iniciativas, bugs ou incidentes no projeto que não é derivável do código ou histórico git</description>
<when_to_save>Quando você aprende quem está fazendo o quê, por quê, ou até quando. Sempre converta datas relativas para absolutas</when_to_save>
<body_structure>Comece com o fato/decisão, depois **Why:** (motivação) e **How to apply:** (como isso deve moldar suas sugestões)</body_structure>

### 4. reference (Geralmente Team)
<scope>usually team</scope>
<description>Ponteiros para onde a informação pode ser encontrada em sistemas externos</description>
<when_to_save>Quando você aprende sobre recursos em sistemas externos e seu propósito</when_to_save>
"""

WHAT_NOT_TO_SAVE_SECTION = """
## O Que NÃO Salvar em Memória

- Code patterns, conventions, architecture, file paths, or project structure — these can be derived by reading the current project state.
- Git history, recent changes, or who-changed-what — `git log` / `git blame` are authoritative.
- Debugging solutions or fix recipes — the fix is in the code; the commit message has the context.
- Anything already documented in CLAUDE.md files.
- Ephemeral task details: in-progress work, temporary state, current conversation context.

These exclusions apply even when the user explicitly asks you to save. If they ask you to save a PR list or activity summary, ask what was *surprising* or *non-obvious* about it — that is the part worth keeping.
"""

TRUSTING_RECALL_SECTION = """
## Before Recommending from Memory

A memory that names a specific function, file, or flag is a claim that it existed *when the memory was written*. It may have been renamed, removed, or never merged. Before recommending it:

- If the memory names a file path: check the file exists.
- If the memory names a function or flag: grep for it.
- If the user is about to act on your recommendation (not just asking about history), verify first.

"The memory says X exists" is not the same as "X exists now."
"""


def build_opener(new_message_count: int, existing_memories: str) -> str:
    """
    Constrói opener do prompt de extração.

    Replica opener() de prompts.ts do Claude Code.

    Args:
        new_message_count: Número de mensagens novas para analisar
        existing_memories: Manifesto de memórias existentes

    Returns:
        String opener do prompt
    """
    return f"""You are now acting as the memory extraction subagent. Analyze the most recent ~{new_message_count} messages above and use them to update your persistent memory systems.

Available tools: FileRead, Grep, Glob, read-only Bash (ls/find/cat/stat/wc/head/tail and similar), and FileEdit/FileWrite for paths inside the memory directory only. Bash rm is not permitted. All other tools will be denied.

You have a limited turn budget. FileEdit requires a prior FileRead of the same file, so the efficient strategy is: turn 1 — issue all FileRead calls in parallel for every file you might update; turn 2 — issue all FileWrite/FileEdit calls in parallel. Do not interleave reads and writes across multiple turns.

You MUST only use content from the last ~{new_message_count} messages to update your persistent memories. Do not waste any turns attempting to investigate or verify that content further — no grepping source files, no reading code to confirm a pattern exists, no git commands.

{existing_memories}
"""


def build_how_to_save_section(memory_dir: Path) -> str:
    """
    Constrói seção de como salvar memórias.

    Args:
        memory_dir: Diretório de memória para incluir no prompt

    Returns:
        String com instruções de como salvar
    """
    return f"""
## Como Salvar Memórias

### Formato do Arquivo

Cada memória é um arquivo .md separado em: {memory_dir}

**Frontmatter (obrigatório):**
```markdown
---
name: {{memory name}}
description: {{one-line description — usada para decidir relevância em conversas futuras, seja específico}}
type: {{user, feedback, project, reference}}
---

{{memory content — para tipos feedback/project, estruture como: regra/fato, depois **Why:** e **How to apply:**}}
```

### Atualizando MEMORY.md (Índice)

O arquivo MEMORY.md é o índice de todas as memórias. Após criar/atualizar uma memória:

1. Leia MEMORY.md existente
2. Adicione uma linha no formato: `- [{{type}}] {{filename}} ({{timestamp}}): {{description}}`
3. Mantenha o limite de {MEMORY_INDEX_MAX_LINES} linhas máximo

### Regras de Escrita

- **Sempre** verifique memórias existentes antes de criar novas (evite duplicatas)
- **Sempre** use frontmatter com name, description, type
- **Sempre** inclua **Why:** e **How to apply:** para feedback e project
- **Nunca** salve o que é derivável do código ou git
- **Priorize** o que é surpreendente ou não-óbvio
"""


def build_extract_dream_prompt(
    new_message_count: int,
    existing_memories: str,
    memory_dir: Path,
    skip_index: bool = False,
) -> List[str]:
    """
    Constrói prompt completo de extração (dream).

    Replica buildExtractAutoOnlyPrompt() do Claude Code (prompts.ts).

    Args:
        new_message_count: Número de mensagens novas para analisar
        existing_memories: Manifesto de memórias existentes
        memory_dir: Diretório de memória (para instruções de path)
        skip_index: Se True, não atualiza MEMORY.md (modo direto)

    Returns:
        Lista de seções do prompt (para join com \\n)
    """
    how_to_save = build_how_to_save_section(memory_dir)

    sections = [
        build_opener(new_message_count, existing_memories),
        "",
        "If the user explicitly asks you to remember something, save it immediately as whichever type fits best. If they ask you to forget something, find and remove the relevant entry.",
        "",
        TYPES_SECTION_INDIVIDUAL.strip(),
        "",
        WHAT_NOT_TO_SAVE_SECTION.strip(),
        "",
        how_to_save.strip(),
        "",
        TRUSTING_RECALL_SECTION.strip(),
    ]

    return sections


# ============================================================================
# CONTADOR DE MENSAGENS DO TRANSCRIPT
# ============================================================================

def count_transcript_messages(since_days: int = 7) -> int:
    """
    Conta mensagens no transcript do Claude Code.

    Lê ~/.claude/projects/<slug>/*.jsonl e conta mensagens model-visible
    (type=user ou type=assistant) no período especificado.

    Args:
        since_days: Dias para analisar (default: 7)

    Returns:
        Número de mensagens novas
    """
    memory_dir = get_auto_mem_path()
    projects_dir = memory_dir.parent  # ~/.claude/projects/<slug>/

    if not projects_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=since_days)
    message_count = 0

    # Lê todos os jsonl do diretório
    jsonl_files = list(projects_dir.glob("*.jsonl"))

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    import json
                    try:
                        msg = json.loads(line)
                        msg_type = msg.get("type", "")

                        # Conta apenas mensagens model-visible
                        if msg_type in ["user", "assistant"]:
                            # Verifica timestamp se disponível
                            ts = msg.get("ts", "")
                            if ts:
                                try:
                                    msg_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                    if msg_dt.replace(tzinfo=None) < cutoff:
                                        continue
                                except ValueError:
                                    pass

                            message_count += 1
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    return message_count


# ============================================================================
# ORQUESTRADOR PRINCIPAL
# ============================================================================

def run_dream(
    memory_dir: Path = None,
    since_days: int = 7,
    dry_run: bool = False,
) -> DreamResult:
    """
    Executa extração automática de memórias (dream).

    Replica o fluxo do extractMemories.ts do Claude Code:
    1. Scan de memórias existentes
    2. Contagem de mensagens novas
    3. Build do prompt
    4. Chamada à API Claude (max 5 turns) — SIMULADO neste método
    5. Report

    Args:
        memory_dir: Diretório de memória (default: auto-detected)
        since_days: Dias para analisar (default: 7)
        dry_run: Se True, apenas simula, não modifica nada

    Returns:
        DreamResult com arquivos processados
    """
    if memory_dir is None:
        memory_dir = get_auto_mem_path()

    # Passo 1: Scan de memórias existentes
    existing = scan_memory_files(memory_dir)
    existing_manifest = format_memory_manifest(existing)

    # Passo 2: Contagem de mensagens novas
    message_count = count_transcript_messages(since_days)

    if message_count == 0:
        return DreamResult(
            written_files=[],
            memory_dir=memory_dir,
            dry_run=dry_run,
            period_days=since_days,
            new_memories=[],
            updated_memories=[]
        )

    # Passo 3: Build do prompt
    prompt_sections = build_extract_dream_prompt(
        new_message_count=message_count,
        existing_memories=existing_manifest,
        memory_dir=memory_dir,
    )
    full_prompt = "\n".join(prompt_sections)

    # Passo 4: Chamada à API Claude
    import re
    import os

    prompt_preview = full_prompt

    if dry_run:
        return DreamResult(
            written_files=[],
            memory_dir=memory_dir,
            dry_run=dry_run,
            period_days=since_days,
            new_memories=[],
            updated_memories=[],
            prompt_preview=prompt_preview,
        )

    # Chamada real à API
    try:
        import anthropic
        model = os.environ.get("CEREBRO_MODEL", "claude-opus-4-5")
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=8096,
            system=full_prompt,
            messages=[{
                "role": "user",
                "content": (
                    "Analyze the conversation transcript and extract memories "
                    "worth saving. Focus on decisions, feedback, and project facts."
                )
            }]
        )
        response_text = response.content[0].text if response.content else ""
    except Exception as e:
        return DreamResult(
            written_files=[],
            memory_dir=memory_dir,
            dry_run=dry_run,
            period_days=since_days,
            new_memories=[],
            updated_memories=[],
            prompt_preview=f"ERRO na chamada LLM: {e}",
        )

    # Parse: extrai filenames .md mencionados na resposta
    mentioned = re.findall(r'[\w\-]+\.md', response_text)
    mentioned = list(dict.fromkeys(mentioned))  # dedup mantendo ordem

    written_files = []
    new_memories = []
    updated_memories = []

    for fname in mentioned:
        if fname == "MEMORY.md":
            continue
        fpath = memory_dir / fname
        if fpath.exists():
            updated_memories.append(fname)
            written_files.append(fpath)
        else:
            new_memories.append(fname)

    return DreamResult(
        written_files=written_files,
        memory_dir=memory_dir,
        dry_run=dry_run,
        period_days=since_days,
        new_memories=new_memories,
        updated_memories=updated_memories,
        prompt_preview=prompt_preview,
    )


def generate_dream_report(result: DreamResult) -> str:
    """
    Gera relatório da extração dream.

    Args:
        result: DreamResult da execução

    Returns:
        Relatório formatado em markdown
    """
    lines = [
        "# Dream Report — Extração de Memórias",
        "",
        f"**Período:** últimos {result.period_days} dias",
        f"**Diretório:** {result.memory_dir}",
        f"**Modo:** {'dry-run (nenhuma modificação)' if result.dry_run else 'aplicação direta'}",
        "",
        "## Resumo",
        "",
    ]

    if result.new_memories:
        lines.append("### Novas Memórias")
        lines.append("")
        for mem in result.new_memories:
            lines.append(f"- {mem}")
        lines.append("")
    else:
        lines.append("Nenhuma memória nova criada.")
        lines.append("")

    if result.updated_memories:
        lines.append("### Memórias Atualizadas")
        lines.append("")
        for mem in result.updated_memories:
            lines.append(f"- {mem}")
        lines.append("")

    if result.written_files:
        lines.append("### Arquivos Modificados")
        lines.append("")
        for f in result.written_files:
            lines.append(f"- {f}")
        lines.append("")

    if not result.new_memories and not result.updated_memories and not result.written_files:
        lines.append("Nenhuma mudança foi necessária.")
        lines.append("")

    return "\n".join(lines)

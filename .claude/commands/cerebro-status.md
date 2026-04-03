---
description: Ver status da memória do projeto
---

Execute **APENAS** a ferramenta MCP `cerebro_status` (sem argumentos).

A ferramenta retorna:
- Session ID
- Path do .ocerebro
- Contagem de memórias por tipo com ícones

**EXEMPLO DE OUTPUT:**

```
╔══════════════════════════════════════════════════════════════╗
║                    🧠 OCEREBRO STATUS                        ║
╚══════════════════════════════════════════════════════════════╝

Session ID: sess_abc123
Path: /projeto/.ocerebro

📊 Memórias: 12 total

Por tipo:
  📂 PROJECT: 2
  🏷️ TAG: 5
  💬 FEEDBACK: 3
  ✅ DECISION: 2

Storages:
  📁 Raw: /projeto/.ocerebro/raw
  📝 Working: /projeto/.ocerebro/working
  📋 Official: /projeto/.ocerebro/official
```

**NÃO use Bash.** Use **APENAS** `cerebro_status`.

Apresente o resultado de forma visual e clara.
---
title: Cerebro - Sistema de Memória para Agentes de Código
date: 2026-03-31
status: approved
---

# Cerebro - Sistema de Memória para Agentes de Código

## Visão Geral

Cerebro é um "segundo cérebro" para agentes de código (Claude Code, Gemini CLI), implementando um sistema de memória em camadas que persiste contexto entre sessões, rastreia mudanças, e evita alucinações através de verificação contra fonte de verdade.

## Objetivos

1. **Memória de longo prazo** - Persistir decisões, preferências e contexto entre sessões
2. **Rastreamento de mudanças** - Registrar o que foi feito, quando e por quê
3. **Estado verificável** - Snapshot do estado atual para evitar alucinações
4. **Lições de erro** - Capturar erros e evitar repetição

---

## 1. Arquitetura Lógica (3 Camadas)

### Camada Bruta (Raw Events)

**Formato:** JSONL append-only
**Propósito:** Event log imutável, auditável, base para replay e análise

```
raw/{project}/events.jsonl
```

Características:
- Append-only, sem modificação
- Rotação opcional por mês: `events-2026-03.jsonl`
- Inclui `checkpoint.created` para marcar ranges consolidados

### Camada Trabalhando (Working/Episódica)

**Formato:** YAML estruturado
**Propósito:** Contexto de curto/médio prazo, editável, sessões em progresso

```
working/{project}/
├── sessions/{session_id}.yaml
├── features/{feature_name}.yaml
├── drafts/{draft_id}.yaml
└── scratch/                     # notas soltas, nunca vão para oficial
```

Características:
- Drafts de decisões, lições candidatas
- Estado de tarefas em progresso
- Rotacionado com base em idade da sessão

### Camada Oficial (Long-term/Checkpointed)

**Formato:** Markdown com YAML frontmatter
**Propósito:** Conhecimento durável, versionável, semântico

```
official/
├── global/                      # memórias跨-projetos
│   ├── decisions/
│   ├── preferences/
│   └── policies/
└── {project}/
    ├── decisions/
    ├── errors/
    ├── preferences/
    └── state/
```

Características:
- Deduplicação, sanitização, agregação aplicadas
- Guard rails: never_delete para itens críticos
- Git-friendly, revisável por humanos

### Fluxo de Promoção

```
Hooks → Bruta (append automático)
         ↓
    Checkpoint (trigger)
         ↓
    Regras heurísticas + LLM
         ↓
    Working (drafts)
         ↓
    Scoring + LLM (casos ambíguos)
         ↓
    Official (promoção automática ou supervisão humana)
```

---

## 2. Sistema de Captura (Hooks)

### Core Obrigatório

| Evento | Type | Subtype | Payload |
|--------|------|---------|---------|
| Tool call | tool_call | read/write/edit/bash/search/test/format | `{tool, file/command, result_summary, duration}` |
| Git event | git_event | commit/branch_change/merge/checkout | `{action, branch, commit_hash, message}` |
| Test result | test_result | unit/integration/e2e | `{test_name, status, duration, error_if_fail}` |
| Error | error | command_failure/test_fail/runtime | `{error_type, message, context}` |

### Schema de Evento Bruto

```json
{
  "event_id": "uuid",
  "ts": "2026-03-31T17:30:00Z",
  "project": "retro-barber",
  "session_id": "sess_abc123",
  "origin": "claude-code|user|ci|hook",
  "type": "tool_call|git_event|test_result|error|checkpoint.created",
  "subtype": "bash|commit|unit|...",
  "payload": {...},
  "tags": ["feature", "auth-module"]
}
```

### Evento Especial: checkpoint.created

```json
{
  "type": "checkpoint.created",
  "payload": {
    "range": {
      "from_event_id": "evt_00123",
      "to_event_id": "evt_00456"
    },
    "reason": "feature_done|session_end|manual",
    "label": "feat-new-booking-flow"
  }
}
```

### Hooks Customizados

**Arquivo:** `hooks/hooks.yaml`

```yaml
hooks:
  - id: record-deploy
    trigger: deploy.finished
    filter:
      environment: production
    priority: 10
    handler:
      type: script
      path: ./hooks/post_deploy.sh

  - id: ci-failure-alert
    trigger: ci_status
    filter:
      status: failed
    priority: 5
    handler:
      type: script
      path: ./hooks/on_ci_fail.py
```

---

## 3. Pipeline de Consolidação

### Triggers de Checkpoint

- **Automáticos:** feature_done (testes passando), session_end, error_critical
- **Manual:** `/checkpoint` para revisão profunda

### Fase 1: Extração (Raw → Working)

Regras heurísticas filtram eventos relevantes.
LLM resume sessão/feature → gera draft em working/

Output:
- `{session_id}.yaml` ou `{feature}.yaml`
- Inclui `events_range: {from_event_id, to_event_id}` para amarrar com raw

### Fase 2: Consolidação (Working → Candidates)

Scoring automático calculado e armazenado no índice:
- recency_score, frequency_score, importance_score, links_score, total_score

Decay temporal aplicado.

LLM chamado apenas para:
- Itens perto do threshold
- Itens "estranhos" (antigos mas linkados)

Itens rejeitados → estado stale no índice

### Fase 3: Promoção (→ Official)

Supisão humana: apenas decisões arquiteturais críticas
Demais itens: promoção automática

Output:
- Markdown com frontmatter em `official/{type}/{project}/`
- Evento `promotion.performed` registrado no raw

---

## 4. Consumo de Memória

### Carga Padrão (ao abrir projeto)

1. **Official global:** preferências, políticas cross-projetos
2. **Official do projeto:** decisões consolidadas, lições importantes
3. **Working do projeto:** sessão/feature em andamento, TODO, últimas mudanças

Priorização:
- Working > Official (short-term prioritário)
- Corte de tamanho: últimas N decisões, últimas M lições
- Índice como roteador: carga focada no módulo atual

### Índice Leve (metadados, não conteúdo)

IDs, títulos, tags, escopo, timestamps, importance, embedding_id

### Consulta Sob Demanda

```
Query: "bugs de deadlock nesse módulo"
  → Busca índice por tags + semântica
  → Recupera 3-5 itens mais relevantes
  → Filtro pós-retrieval

Inteligência por contexto:
  → Bug → prioriza: errors, incidents, post-mortems
  → Feature → prioriza: decisions, design docs, constraints
```

---

## 5. Lições de Erro (Post-Mortem Estruturado)

### Template

```yaml
---
id: err_abc123
type: error
status: resolved|mitigated|open
severity: low|medium|high|critical
impact: low|medium|high|critical
category: bug|config|architecture|security|performance
area: auth-module|database|api|frontend|infra|pipeline
project: retro-barber
created: 2026-03-31T17:30:00Z
tags: [deadlock, connection-pool, postgres]
related_to: [err_042, dec_connection_pool]
similar_to: []
---

# Erro Original
Descrição do erro ocorrido.

# Causa Raiz
Análise da causa.

# Solução Aplicada
Como foi resolvido.

# Prevenção Futura (opcional)
Como evitar recorrência.
```

### Classificação Automática

LLM preenche automaticamente:
- severity, impact, category, area

Links:
- `related_to`: causalidade e dependência
- `similar_to`: clusterização de famílias de bugs

---

## 6. Forgetting (Decay + Poda)

### Scoring RFM Adaptado

```
score = w_r·R + w_f·F + w_i·I + w_l·L

R = recency (último acesso/atualização)
F = frequency (quantas vezes recuperado)
I = importance (severity, impacto arquitetural)
L = links (quantos related_to/similar_to)
```

### Decay Diferencial por Tipo

| Tipo | Decay |
|------|-------|
| Decisões arquiteturais | Lento |
| Lições de erro críticas | Quase zero |
| Notas de sessão | Rápido |

### Limiar → Zona de Esquecimento

score baixo + tempo → candidatos a arquivar/mesclar

LLM arbitra casos ambíguos:
- Erro antigo mas relevante → manter
- Decisão sobre tech obsoleta → arquivar/mesclar

### Guard Rails

```yaml
never_delete:
  - decisions.critical
  - errors.severity=high
  - errors.impact=critical

always_archive:
  - raw: 30d
  - working: 90d (sem updates)
```

### Log de Poda

Evento `memory.gc` no raw:
```json
{
  "type": "memory.gc",
  "payload": {
    "archived": ["id1", "id2"],
    "merged": [{"from": ["id3", "id4"], "to": "id5"}],
    "reason": "low_score_decay"
  }
}
```

---

## 7. Índice SQLite + Embeddings Híbrido

### metadata.db Schema

```sql
CREATE TABLE memories (
  id TEXT PRIMARY KEY,
  type TEXT,              -- decision|error|preference|state|session|feature
  project TEXT,
  title TEXT,
  tags TEXT,              -- JSON array
  severity TEXT,
  impact TEXT,
  importance_score REAL,
  recency_score REAL,
  frequency_score REAL,
  links_score REAL,
  total_score REAL,
  created_at TEXT,
  updated_at TEXT,
  last_accessed TEXT,
  access_count INTEGER,
  path TEXT,
  layer TEXT,             -- raw|working|official
  content_hash TEXT
);

CREATE VIRTUAL TABLE memories_fts USING fts5(
  id UNINDEXED,
  title,
  content,
  tags,
  project
);
```

### embeddings.db Schema

```sql
CREATE TABLE embeddings (
  id TEXT,
  model TEXT,
  embedding BLOB,
  created_at TEXT,
  PRIMARY KEY (id, model)
);
```

### Queries Típicas

```sql
-- Por metadados/tags
SELECT * FROM memories
WHERE project='retro-barber' AND type='error'
ORDER BY total_score DESC;

-- FTS textual
SELECT m.* FROM memories m
JOIN memories_fts f ON f.id = m.id
WHERE f MATCH 'deadlock connection'
ORDER BY m.total_score DESC;

-- Semântica (via embeddings)
SELECT m.*, cosine_similarity(e.embedding, query_vec) as score
FROM memories m JOIN embeddings e ON m.id = e.id
ORDER BY score DESC LIMIT 5;
```

---

## 8. Organização Física de Diretórios

```
cerebro/
├── raw/
│   └── {project}/
│       └── events.jsonl          # ou events-2026-03.jsonl
│
├── working/
│   └── {project}/
│       ├── sessions/
│       ├── features/
│       ├── drafts/
│       └── scratch/
│
├── official/
│   ├── global/
│   │   ├── decisions/
│   │   ├── preferences/
│   │   └── policies/
│   └── {project}/
│       ├── decisions/
│       ├── errors/
│       ├── preferences/
│       └── state/
│
├── index/
│   ├── metadata.db
│   └── embeddings.db
│
├── hooks/
│   └── hooks.yaml
│
└── config/
    └── cerebro.yaml
```

### Versionamento Git

| Diretório | Git |
|-----------|-----|
| working/ | Sim |
| official/ | Sim |
| hooks/ | Sim |
| config/ | Sim |
| index/ | Não (reconstruível) |
| raw/ | Opcional (alto volume) |

---

## 9. Integração com Claude Code

### Localização

- **Global:** `~/.claude/cerebro`
- **Por projeto:** `.claude/` contendo:
  - `MEMORY.md` (gerado)
  - `cerebro-project.yaml` (project_id/name)

### MEMORY.md como View

Gerado dinamicamente a partir de official + working:

```markdown
# Cerebro - Memória Ativa

## Official Global
- [Convenções de código](global/preferences/code-style.md)
- [Políticas de commit](global/policies/commit-style.md)

## Official retro-barber
- [Decisão: PostgreSQL vs MongoDB](official/decisions/retro-barber/db-choice.md)
- [Erro: deadlock connection pool](official/errors/retro-barber/deadlock-pool.md)

## Working atual
- Sessão: feat-new-booking-flow
- TODO: finalizar testes de integração
- Últimas mudanças: auth-module refactor

---
Outras memórias disponíveis via Cerebro (decisions, errors, preferences, state).
```

### settings.json

```json
{
  "cerebro": {
    "enabled": true,
    "path": "~/.claude/cerebro",
    "auto_checkpoint": ["feature_done", "session_end", "error_critical"],
    "checkpoint_command": "/checkpoint"
  }
}
```

---

## 10. Configuração Global

### cerebro.yaml

```yaml
# Guard rails
never_delete:
  - decisions.critical
  - errors.severity=high
  - errors.impact=critical

always_archive:
  raw: 30d
  working: 90d

# Score weights
score_weights:
  recency: 0.3
  frequency: 0.2
  importance: 0.3
  links: 0.2

# Decay rates por tipo
decay_rates:
  decisions: 0.01      # lento
  errors_critical: 0.001  # quase zero
  sessions: 0.05       # rápido

# Embeddings
embedding_model: sentence-transformers/all-MiniLM-L6-v2
embedding_dimensions: 384
```

---

## Decisões de Design

### Por que 3 camadas?

Eventos brutos precisam ser auditáveis mas são alto volume. Working permite edição e drafts. Official é o conhecimento durável. Separar por propósito permite políticas diferentes por camada.

### Por que SQLite + FTS + embeddings?

Metadados precisam de queries rápidas (SQLite). Texto precisa de busca lexical (FTS). Semântica precisa de vetores (embeddings). Híbrido dá cada ferramenta para seu propósito.

### Por que score + LLM híbrido?

Scoring automático escala bem. LLM só para casos ambíguos é custo-eficiente. Guard rails evitam erros catastróficos.

### Por que JSONL/YAML/Markdown diferentes?

JSONL append-only é ideal para logs. YAML é editável e estruturado. Markdown é legível e git-friendly. Cada formato para seu propósito.

---

## Próximos Passos

1. Implementar captura de hooks core
2. Implementar índice SQLite + embeddings
3. Implementar pipeline de consolidação
4. Implementar consumo/carga padrão
5. Implementar forgetting/scoring
6. Integrar com Claude Code via settings.json
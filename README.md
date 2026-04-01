# OCerebro 🧠

**Sistema de Memória para Agentes (Claude Code/MCP)**

OCerebro dá memória persistente e capacidade de aprendizado para o Claude Code. Ele captura automaticamente todo o contexto das sessões, consolida em memória estruturada e permite busca semântica com sqlite-vec.

---

## ✨ Funcionalidades

- 📦 **Memória Automática 3 Camadas**: Raw → Working → Official
- 🔍 **Busca Híbrida**: Texto (FTS5) + Semântica (sqlite-vec ANN)
- 🤖 **MCP Server**: 6 ferramentas para Claude Code
- 🎣 **Hooks Customizáveis**: Extensível via YAML
- 📊 **RFM Scoring**: Relevância temporal e importância
- 🛡️ **Guard Rails**: Proteções para não deletar importante
- 💾 **SQLite Nativo**: Zero dependências externas, zero infra

---

## 🚀 Instalação Rápida

### Pré-requisitos

- Python 3.10+
- Claude Desktop (opcional, para integração MCP)

### Passo 1: Instalar

```bash
pip install ocerebro
```

Ou instale localmente:

```bash
git clone https://github.com/OARANHA/ocerebro.git
cd ocerebro
pip install .
```

### Passo 2: Setup Automático

```bash
# Em seu projeto
ocerebro init

# Configura Claude Desktop automaticamente
ocerebro setup claude
```

**Pronto!** Reinicie o Claude Desktop e as ferramentas estarão disponíveis.

---

## 📖 Uso

### No Terminal

```bash
# Ver status do sistema
ocerebro status

# Ver memória de um projeto
ocerebro memory meu-projeto

# Buscar por texto
ocerebro search "autenticação JWT"

# Criar checkpoint manual
ocerebro checkpoint meu-projeto --reason "antes de refatorar"

# Promover decisão para official
ocerebro promote meu-projeto sess_abc123
```

### No Claude Code (MCP)

Com o MCP Server configurado, você tem acesso a:

| Ferramenta | Descrição |
|------------|-----------|
| `ocerebro_memory` | Gera MEMORY.md do projeto |
| `ocerebro_search` | Busca memórias por texto/embedding |
| `ocerebro_checkpoint` | Cria checkpoint da sessão atual |
| `ocerebro_promote` | Promove draft para decisão official |
| `ocerebro_status` | Status do sistema |
| `ocerebro_hooks` | Gerencia hooks customizados |

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Claude Code                          │
│                         ↓                               │
│                    MCP Server                           │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│                      OCerebro                           │
│                                                         │
│  Raw (JSONL) → Working (YAML) → Official (Markdown)    │
│       ↓              ↓              ↓                   │
│  Eventos →  Extração →  Rascunhos →  Memória          │
│                  ↓              ↓                       │
│           sqlite-vec ←  Busca Híbrida                  │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 Estrutura do Projeto

No seu projeto, o OCerebro cria:

```
meu-projeto/
  .ocerebro/
    raw/           ← Eventos brutos (JSONL)
    working/       ← Rascunhos YAML
    official/      ← Memória permanente (Markdown)
    index/         ← Banco de dados (metadata + embeddings)
    config/        ← Configurações
    MEMORY.md      ← Memória ativa (gerado automaticamente)
```

---

## 🎣 Hooks Customizados

Crie automações com hooks:

### Exemplo: `hooks.yaml`

```yaml
hooks:
  - name: notificar_erro
    event_type: error
    module_path: hooks/error_hook.py
    function: on_error
    config:
      notify_severity: ["critical", "high"]

  - name: track_custo_llm
    event_type: tool_call
    event_subtype: llm
    module_path: hooks/cost_hook.py
    function: on_llm_call
    config:
      monthly_budget: 100.0
```

**Documentação completa:** [docs/HOOKS_GUIDE.md](docs/HOOKS_GUIDE.md)

---

## 🔧 Configuração Manual (MCP)

Se o setup automático não funcionar, edite `claude_desktop.json`:

### Windows
```
%APPDATA%\Claude\claude_desktop.json
```

### macOS
```
~/Library/Application Support/Claude/claude_desktop.json
```

### Linux
```
~/.config/Claude/claude_desktop.json
```

**Conteúdo:**

```json
{
  "mcpServers": {
    "ocerebro": {
      "command": "python",
      "args": ["/caminho/para/ocerebro/src/mcp/server.py"],
      "cwd": "/caminho/para/ocerebro"
    }
  }
}
```

---

## 🧪 Testes

```bash
# Instalar dependências de teste
pip install -e ".[test]"

# Rodar testes
pytest

# Com coverage
pytest --cov=src
```

**Status:** 133 testes passando ✅

---

## 📊 Estatísticas

| Métrica | Valor |
|---------|-------|
| Testes | 133 passing |
| Linhas de código | ~7.700 |
| Commits | 25+ |
| Ferramentas MCP | 6 |
| Tipos de evento | 8+ |

---

## 🤝 Contribuindo

1. Fork o repositório
2. Crie uma branch (`git checkout -b feature/minha-feature`)
3. Commit (`git commit -m 'feat: adiciona nova feature'`)
4. Push (`git push origin feature/minha-feature`)
5. Abra um Pull Request

---

## 📝 Changelog

### v0.1.0 (2026-04-01)

- ✅ Arquitetura 3 camadas (Raw → Working → Official)
- ✅ Extractor e Promoter
- ✅ EmbeddingsDB + QueryEngine (busca híbrida com sqlite-vec)
- ✅ CLI completa
- ✅ MCP Server (6 ferramentas)
- ✅ Hooks customizados via YAML
- ✅ 133 testes passing

---

## 📚 Documentação

- [Guia de Hooks](docs/HOOKS_GUIDE.md)
- [Spec de Design](docs/superpowers/specs/2026-03-31-cerebro-design.md)
- [Plano de Implementação](docs/superpowers/plans/2026-03-31-cerebro-implementacao.md)

---

## 🙋 FAQ

**O OCerebro funciona sem o Claude Desktop?**
Sim! A CLI funciona independentemente. O MCP Server é opcional.

**Posso sincronizar memória entre computadores?**
Sim! Use Git para sincronizar `official/` e `config/`.

**O que acontece se deletar `.ocerebro/`?**
Você perde a memória local. Se tiver `official/` em backup, pode recuperar.

**Funciona em Linux/Mac/Windows?**
Sim! Testado em todas as plataformas.

---

## 📄 Licença

MIT License - veja [LICENSE](LICENSE) para detalhes.

---

## 🌟 Créditos

Criado por [@OARANHA](https://github.com/OARANHA)

Feito com ❤️ para a comunidade Claude Code.

---

**Stars:** ⭐ 0 | **Forks:** 🍴 0

[Reportar bug](https://github.com/OARANHA/ocerebro/issues) • [Pedir feature](https://github.com/OARANHA/ocerebro/issues)

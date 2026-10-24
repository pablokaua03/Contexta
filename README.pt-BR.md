<div align="center">

# Contexta

**Engine de contexto AI-native para codebases. Serve contexto inteligente para Claude Code, Cursor, Windsurf e qualquer ferramenta compatível com MCP — ou gera packs de contexto curados para uso manual.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Plataforma](https://img.shields.io/badge/Plataforma-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![Versão](https://img.shields.io/badge/Vers%C3%A3o-2.1.0-purple)]()
[![MCP](https://img.shields.io/badge/MCP-Compatível-orange)]()

<br>

[<img src="https://img.shields.io/badge/pip%20install%20contexta--ai-3776AB?style=for-the-badge&logo=pypi&logoColor=white" height="42">](https://pypi.org/project/contexta-ai/)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/Download%20para%20Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta.exe)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/Download%20para%20Linux-E95420?style=for-the-badge&logo=linux&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta-linux.tar.gz)

> Instale via pip, baixe o executável portátil ou rode direto do código-fonte.

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/white.png">
  <img alt="Preview da interface do Contexta" src="assets/dark.png">
</picture>

</div>

---

## O que é o Contexta

O Contexta analisa codebases e serve contexto inteligente e curado para ferramentas de IA. Em vez de despejar arquivos cegamente, ele entende a estrutura do projeto, detecta frameworks, ranqueia arquivos por importância e entrega exatamente o que a IA precisa.

**Três formas de usar:**

| Modo | Comando | O que faz |
|---|---|---|
| **MCP Server** | `contexta serve` | Roda como servidor de ferramentas — Claude Code, Cursor, Windsurf chamam automaticamente |
| **CLI** | `contexta ./projeto --pack onboarding` | Gera um arquivo Markdown com o context pack |
| **GUI** | `contexta` | App desktop com controles visuais |

---

## MCP Server (recomendado)

O MCP server é a forma principal de usar o Contexta. Assistentes de IA o chamam como ferramenta para entender seu projeto — sem copiar e colar.

### Configuração

Adicione à configuração MCP do seu editor (Claude Code, Cursor, Windsurf, etc.):

```json
{
  "mcpServers": {
    "contexta": {
      "command": "contexta",
      "args": ["serve"]
    }
  }
}
```

Ou rodando do código-fonte:

```json
{
  "mcpServers": {
    "contexta": {
      "command": "python",
      "args": ["/caminho/para/contexta_mcp.py"]
    }
  }
}
```

### Ferramentas disponíveis

| Ferramenta | O que faz |
|---|---|
| `scan_project` | Fingerprint rápido — tipo, linguagem, frameworks, deps, entry points |
| `get_architecture` | Relações entre módulos, estrutura de pastas, riscos, padrões |
| `generate_context` | Context pack completo com todas as opções de preset |
| `find_files` | Busca arquivos por nome, extensão ou palavra-chave |
| `read_files` | Lê conteúdo de arquivos específicos |
| `list_packs` | Lista presets disponíveis |
| `cache_status` | Mostra estatísticas de cache (hits/misses) |
| `refresh_cache` | Força atualização do cache |

### Cache inteligente

Resultados ficam em memória com invalidação automática. A primeira chamada analisa o projeto (~700ms), as seguintes retornam em ~2ms até que arquivos mudem no disco. O cache monitora mtimes e arquivos de manifesto — quando você edita código, a próxima chamada recomputa automaticamente.

---

## Instalação

### Opção A: pip (recomendado)

```bash
pip install contexta-ai
# ou, para um CLI isolado:
pipx install contexta-ai
contexta --help
```

Integrações opcionais com APIs de IA:

```bash
pip install contexta-ai[claude]    # API do Claude
pip install contexta-ai[gemini]    # API do Gemini
pip install contexta-ai[openai]    # API do OpenAI
pip install contexta-ai[all-ai]    # Todos os três
```

### Opção B: Executáveis portáteis

- **Windows**: baixe [`contexta.exe`](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta.exe)
  > **Windows 11:** clique com botão direito no `.exe` baixado → Propriedades → marque **Desbloquear** → OK antes de executar.
- **Linux**: baixe [`contexta-linux.tar.gz`](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta-linux.tar.gz)

### Opção C: Código-fonte

```bash
git clone https://github.com/pablokaua03/Contexta.git
cd Contexta
pip install -r requirements.txt
python contexta.py
```

---

## Uso via CLI

```bash
# Gerar context packs
contexta .                                                   # pack padrão, ou contexta.toml
contexta . --pack onboarding --copy                         # entender um repo e colar no chat
contexta . --pack bugfix --focus "login timeout"            # corrigir um bug com um agente
contexta . --pack pr_review --base main --stdout            # revisar o branch contra main
contexta . --pack refactor --format json -o pack.json       # pack de refactor em JSON
contexta . --pack raw_files                                 # dump limpo de caminho + conteúdo

# Configuração inicial do projeto
contexta --init                                              # cria contexta.toml e .contextaignore

# Integração com API de IA — envia contexto + pergunta direto para uma IA
contexta . --ask "quais são os principais riscos de segurança?"
contexta . --ask "explique a arquitetura" --provider claude

# Configurar chaves de API
contexta --configure-ai
```

### Flags do CLI

| Flag | Descrição |
|---|---|
| `--pack` | Preset: `custom`, `chatgpt`, `onboarding`, `pr_review`, `risk_review`, `debug`, `bugfix`, `backend`, `frontend`, `changes_related`, `refactor`, `raw_files` |
| `--mode` | Modo: `full`, `debug`, `feature`, `diff`, `onboarding`, `refactor` |
| `--compression` | `full`, `balanced`, `focused`, `signatures`, `lean` |
| `--ai` | Perfil usado no orçamento de tokens: `generic`, `chatgpt`, `claude`, `gemini`, `copilot` |
| `--task` | Tarefa: `general`, `ai_handoff`, `bug_report`, `code_review`, `explain_project`, `risk_analysis`, `refactor_request`, `pr_summary`, `write_tests`, `find_dead_code` |
| `--focus` | Direciona scoring para um tópico (ex: `"auth flow"`, `"database"`) |
| `--diff` / `--staged` | Usa mudanças do git como contexto |
| `--base` | Compara com uma ref git, como `main` ou `origin/main` |
| `--max-tokens` | Aperta a compressão até a estimativa caber nesse orçamento |
| `--format` | `md` (padrão) ou `json` |
| `--stdout` | Escreve o pack na stdout. Também acontece quando a stdout está em pipe |
| `--redact` / `--no-redact` | Redação de segredos ligada por padrão |
| `--init` | Cria `contexta.toml` e `.contextaignore` se ainda não existirem |
| `--ask` | Envia context pack + prompt para uma API de IA |
| `--provider` | Provedor: `claude`, `gemini`, `openai` |
| `--api-key` | Chave da API (também lê `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`) |
| `--configure-ai` | Setup interativo de API de IA |
| `-c` / `--copy` | Copia saída para o clipboard |
| `-o` / `--output` | Caminho de saída. Use `-` para stdout |

Flags do CLI vencem o `contexta.toml`, que vence `~/.contexta/config.toml`. Uma flag explícita também vence o preset, então `--pack pr_review --compression lean` continua lean.

O rodapé do pack diz se o export cabe no perfil escolhido. Segredos comuns (chaves de API, tokens, chaves privadas e senhas em connection strings) viram `[REDACTED]` antes da escrita. `contexta --init` cria a config e o `.contextaignore`. O `.gitignore` continua valendo; o `.contextaignore` e a lista `ignore` excluem arquivos só do pack. Exemplo em [`docs/contexta.toml.example`](docs/contexta.toml.example).

---

## Packs de contexto

| Pack | Melhor para |
|---|---|
| `onboarding` | Entender um codebase novo rapidamente |
| `pr_review` | Code review com contexto de mudanças |
| `risk_review` | Hotspots de regressão, cobertura faltante, módulos de alto impacto |
| `debug` | Bug hunting com arquivos suspeitos priorizados |
| `bugfix` | Handoff diário de bugfix para um agente de código |
| `refactor` | Módulos a mudar e os arquivos ligados a eles |
| `backend` / `frontend` | Foco em um lado da aplicação |
| `changes_related` | Mudanças do git + arquivos relevantes próximos |
| `raw_files` | Dump limpo dos arquivos importantes — caminho + conteúdo, sem análise |
| `chatgpt` | Preset geral para ChatGPT |
| `custom` | Controle manual total |

---

## O que o Contexta exporta

Dependendo do pack, modo e tarefa, a saída pode incluir:

- Resumo do projeto com stack detectada, entry points, propósito e módulos centrais
- Caminho "leia isso primeiro" pelo repositório
- Narrativa do fluxo principal de execução
- Arquivos centrais, de apoio, testes relacionados e contexto de arquivos alterados
- Mapas de relacionamento e notas de risco
- Breakdown de scores explicando por que cada arquivo foi selecionado
- Payload Markdown curado pronto para qualquer ferramenta de IA

---

## Principais recursos

| Recurso | Detalhe |
|---|---|
| **MCP Server** | `contexta serve` — ferramentas de IA chamam como servidor com cache inteligente |
| **Integração com API de IA** | `--ask` envia contexto direto para Claude, Gemini ou OpenAI |
| **Cache inteligente** | Respostas em ~2ms com invalidação automática por mtime |
| **Raw files pack** | Dump limpo caminho + conteúdo para workflows simples |
| **GUI + CLI** | App desktop para uso visual, CLI para automação |
| **Fingerprinting** | Detecta stack, frameworks, domínio e tipo de projeto automaticamente |
| **Análise syntax-aware** | tree-sitter + fallback heurístico para extração de símbolos |
| **Multi-linguagem** | Python, JS/TS, Go, Rust, PHP, Java, C#, Kotlin, Swift, C++ e mais |
| **Orçamento de tokens** | Relatório fits / tight / over por perfil, com `--max-tokens` |
| **Redação de segredos** | Credenciais comuns são removidas antes do export Markdown ou JSON |
| **Diff de PR** | `--base main` inclui o que mudou desde o merge-base, mais o trabalho local |
| **Config do projeto** | `contexta.toml`, `.contextaignore` e `~/.contexta/config.toml` opcional |
| **Export JSON** | `--format json` embrulha o mesmo pack para outras ferramentas |
| **Proteção contra blobs** | Colapsa literais base64/binários automaticamente |
| **Pacote PyPI** | `pip install contexta-ai` com extras opcionais de IA |

---

## Build a partir do código

```bash
# Windows (requer Visual Studio C++ Build Tools)
.\build.bat

# Linux / macOS
chmod +x build.sh && ./build.sh
```

Saídas: `dist/contexta.exe` (Windows), `dist/contexta` (Linux/macOS), `dist/contexta-linux.tar.gz` (bundle Linux).

---

## Testes

```bash
python -m pytest tests/ -k "not test_relation_score"
```

---

## Segurança e comportamento

- Read-only: o Contexta não modifica o projeto analisado
- Sem telemetria ou necessidade de rede (exceto `--ask` opcional)
- Limites de scan evitam exports descontrolados
- Payloads binários/base64 suprimidos automaticamente
- Segredos prováveis são redatados nos exports e no `read_files` do MCP, a menos que `--no-redact` seja usado
- Chaves de API ficam em `~/.contexta/ai_config.json` quando usando `--configure-ai`

---

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md)

## Changelog

Veja [CHANGELOG.md](CHANGELOG.md)

## Licença

[MIT](LICENSE) © [pablokaua03](https://github.com/pablokaua03)

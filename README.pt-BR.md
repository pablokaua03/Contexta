<div align="center">

<img src="assets/logo.svg" width="88" alt="Contexta">

# Contexta

**O contexto certo, dentro do seu orçamento de tokens, seguro por padrão.**

O Contexta lê o código, fica com os arquivos que importam para a tarefa, encaixa tudo no orçamento de tokens que você definir e remove prováveis segredos antes de qualquer coisa sair da sua máquina. Cole o pack em qualquer assistente, ou sirva por MCP para Claude Code, Cursor e Windsurf.

[![Python](https://img.shields.io/badge/python-3.11%2B-12211c?style=flat-square)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-12211c?style=flat-square)](LICENSE)
[![Plataforma](https://img.shields.io/badge/plataforma-Windows%20%7C%20macOS%20%7C%20Linux-12211c?style=flat-square)]()
[![Versão](https://img.shields.io/badge/vers%C3%A3o-2.1.0-12211c?style=flat-square)]()
[![MCP](https://img.shields.io/badge/MCP-compat%C3%ADvel-12211c?style=flat-square)]()

<br>

[Instalar com pip](https://pypi.org/project/contexta-ai/)
·
[Build para Windows](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta.exe)
·
[Build para Linux](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta-linux.tar.gz)

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/white.png">
  <img alt="App desktop do Contexta no tema escuro, com um projeto de exemplo e uma prévia legível do pack" src="assets/dark.png" width="960">
</picture>

</div>

---

## O que o Contexta faz

Jogar o repositório inteiro no chat gasta tokens e vaza coisa. O Contexta faz três trabalhos:

| Trabalho | Como |
|---|---|
| **Escolher os arquivos certos** | Ranqueia por papel, imports, testes e pela sua tarefa, e descarta o resto |
| **Respeitar o orçamento** | `--budget 20000` mantém os melhores arquivos que cabem e lista o que ficou de fora |
| **Ser seguro** | Redação ligada por padrão, arquivos de credencial nunca são lidos e o servidor MCP só lê dentro da pasta permitida |

Números reais no [Flask](https://github.com/pallets/flask), na mesma máquina:

| Comando | Resultado |
|---|---|
| `contexta flask` | 0,7 s (antes 2,9 s). FastAPI, 2000 arquivos: 5 s (antes 69 s) |
| `contexta flask --focus "session cookie signing"` | 8 arquivos, cerca de 17k tokens, `sessions.py` primeiro (antes o repo todo, cerca de 165k) |
| `contexta flask --budget 8000` | cerca de 7,9k tokens, 15 arquivos, o resto listado como deixado de fora |

**Três formas de usar:**

| Modo | Comando | O que faz |
|---|---|---|
| **MCP Server** | `contexta serve --root ~/code` | Servidor de ferramentas para Claude Code, Cursor e Windsurf. Lê só dentro de `--root` |
| **CLI** | `contexta ./projeto --pack onboarding --budget 20000` | Gera um context pack |
| **GUI** | `contexta` | App desktop com prévia ao vivo |

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
      "args": ["serve", "--root", "/caminho/do/seu/codigo"]
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

O servidor lê só dentro das pastas passadas com `--root` (repita a flag para mais de uma), ou `CONTEXTA_ROOT`, ou a pasta onde foi iniciado. Caminhos fora delas, escapes com `..`, symlinks que saem do projeto e arquivos de credencial como `.env` ou `id_rsa` são recusados. `generate_context` aceita o argumento `budget`.

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
contexta . --budget 20000                                   # melhores arquivos que cabem em 20k tokens
contexta . --focus "session cookie signing" --budget 8000  # pack pequeno sobre um tópico
contexta . --dry-run                                        # lista o que seria redatado, não escreve nada

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
| `--focus` | Filtra e ranqueia por um tópico (ex: `"auth flow"`). Mantém os melhores resultados, com testes e imports, não o repo todo |
| `--diff` / `--staged` | Usa mudanças do git como contexto |
| `--base` | Compara com uma ref git, como `main` ou `origin/main` |
| `--budget N` (alias `--max-tokens`) | Mantém os arquivos de maior score até o pack caber em N tokens, aperta a compressão se precisar e lista o que ficou de fora |
| `--max-files N` | Limite de arquivos do scan (padrão 2000, também `max_files` no `contexta.toml` ou `CONTEXTA_MAX_FILES`) |
| `--format` | `md` (padrão) ou `json` |
| `--stdout` | Escreve o pack na stdout. Também acontece quando a stdout está em pipe |
| `--redact` / `--no-redact` | Redação de segredos ligada por padrão. As duas flags não podem ser combinadas |
| `--dry-run` | Mostra arquivo, linha e regra de cada valor que seria redatado (nunca o valor) e não escreve o pack. Funciona com `--format json` |
| `--init` | Cria `contexta.toml` e `.contextaignore` se ainda não existirem |
| `--ask` | Envia context pack + prompt para uma API de IA |
| `--provider` | Provedor: `claude`, `gemini`, `openai` |
| `--api-key` | Chave da API (também lê `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`) |
| `--configure-ai` | Setup interativo de API de IA |
| `-c` / `--copy` | Copia saída para o clipboard |
| `-o` / `--output` | Caminho de saída. Use `-` para stdout |

Flags do CLI vencem o `contexta.toml`, que vence `~/.contexta/config.toml`. Uma flag explícita também vence o preset, então `--pack pr_review --compression lean` continua lean.

O rodapé do pack diz se o export cabe no perfil escolhido. Segredos prováveis (chaves de API, tokens, chaves privadas, senhas em URLs, linhas `password: ...` em JSON e YAML e strings aleatórias sob nomes de segredo) viram `[REDACTED]` antes da escrita. Use `--dry-run` para ver o que mudaria. Para manter um valor, liste em `redact_allow` no `contexta.toml` ou ponha `contexta:allow` na linha. Arquivos como `.env`, chaves privadas, `.npmrc` e `.netrc` nunca são lidos. Com `--budget`, o pack ganha uma seção "Token Budget" dizendo o que ficou de fora. `contexta --init` cria a config e o `.contextaignore`. O `.gitignore` continua valendo; o `.contextaignore` e a lista `ignore` excluem arquivos só do pack. Exemplo em [`docs/contexta.toml.example`](docs/contexta.toml.example).

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
| **Orçamento de tokens** | `--budget N` escolhe arquivos por score até caber e diz o que descartou |
| **Focus** | `--focus "tópico"` filtra e ranqueia, em vez de só dar um empurrão no score |
| **Redação de segredos** | Formatos conhecidos de token mais checagem de alta entropia, com dry run e allowlist |
| **MCP seguro** | Confinado a `--root`, sem escape por symlink, sem arquivos de credencial |
| **Rápido** | Um repo de 2000 arquivos escaneia em cerca de 5 s; a checagem de testes era quadrática |
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
- Limite de 2000 arquivos por padrão, ajustável com `--max-files`
- Payloads binários/base64 suprimidos automaticamente
- Segredos prováveis são redatados nos exports e no `read_files` do MCP, a menos que `--no-redact` seja usado. `--dry-run` mostra o que seria redatado
- Arquivos de credencial (`.env`, chaves privadas, credenciais de nuvem e gerenciadores de pacote) são ignorados no scan e recusados pelo MCP
- O servidor MCP lê só dentro de `--root` / `CONTEXTA_ROOT` / seu diretório de trabalho
- Symlinks que apontam para fora do projeto não são seguidos
- Chaves de API ficam em `~/.contexta/ai_config.json` quando usando `--configure-ai`

---

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md)

## Changelog

Veja [CHANGELOG.md](CHANGELOG.md)

## Licença

[MIT](LICENSE) © [pablokaua03](https://github.com/pablokaua03)

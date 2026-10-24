<div align="center">

<img src="assets/logo.svg" width="88" alt="Contexta">

# Contexta

**The right context, inside your token budget, safe by default.**

Contexta reads a codebase, keeps the files that matter for the task, fits them into the token budget you set, and strips likely secrets before anything leaves your machine. Paste the pack into any assistant, or serve it over MCP to Claude Code, Cursor, and Windsurf.

[![Python](https://img.shields.io/badge/python-3.11%2B-12211c?style=flat-square)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-12211c?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-12211c?style=flat-square)]()
[![Version](https://img.shields.io/badge/version-2.2.0-12211c?style=flat-square)]()
[![MCP](https://img.shields.io/badge/MCP-compatible-12211c?style=flat-square)]()

<br>

[Install with pip](https://pypi.org/project/contexta-ai/)
·
[Windows build](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta.exe)
·
[Linux build](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta-linux.tar.gz)

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/white.png">
  <img alt="Contexta desktop app in dark theme, with a sample project selected and a readable pack preview" src="assets/dark.png" width="960">
</picture>

</div>

---

## What Contexta does

Dumping a whole repo into a chat wastes tokens and leaks things. Contexta does three jobs instead:

| Job | How |
|---|---|
| **Pick the right files** | Ranks files by role, imports, tests and your task, then drops the rest |
| **Respect your budget** | `--budget 20000` keeps the best files that fit and lists what it left out |
| **Stay safe** | Redaction is on by default, credential files are never read, and the MCP server only reads inside the folder you allow |

Measured on pinned commits of [Flask](https://github.com/pallets/flask), [Requests](https://github.com/psf/requests) and [FastAPI](https://github.com/fastapi/fastapi), against Repomix and Gitingest ([`benchmarks/`](benchmarks/README.md), reproducible with one command):

| Command | Result |
|---|---|
| `contexta flask --budget 20000 --focus "session cookie signing"` | 8.4k tokens, 0.6 s warm. Repomix and Gitingest dump 229k to 402k tokens |
| `contexta fastapi --budget 20000 --focus "dependency injection solving"` | 17.7k tokens in 1.4 s warm (3.6 s with `--no-graph`). The same repo is 4.4M to 8.9M tokens as a full dump |
| Files needed for the task, found in the packs that fit 128k | Contexta 3/4, 4/4, 2/5. Repomix `--compress --include <package>` 3/4, 2/4, 2/5 |

It loses on raw speed (the unbudgeted FastAPI pack takes 9 s, Repomix 1.3 s), an unbudgeted pack is
still 168k tokens on Flask, and focus matching is by keyword, so it misses `class Depends` for "dependency injection". The [full table](benchmarks/README.md) shows all of it.

**Three ways to use it:**

| Mode | Command | What it does |
|---|---|---|
| **MCP Server** | `contexta serve --root ~/code` | Tool server for Claude Code, Cursor and Windsurf. Reads only inside `--root` |
| **GitHub Action** | `uses: pablokaua03/contexta@main` | PR context (diff, impacted tests, redacted, within budget) as an artifact and a comment. [Docs](docs/github-action.md) |
| **CLI** | `contexta ./project --pack onboarding --budget 20000` | Writes a context pack |
| **GUI** | `contexta` | Desktop app with a live preview |

---

## MCP Server (recommended)

The MCP server is the primary way to use Contexta. AI coding assistants call it as a tool to understand your project — no copy-paste needed.

### Setup

Add to your MCP configuration (Claude Code, Cursor, Windsurf, etc.):

```json
{
  "mcpServers": {
    "contexta": {
      "command": "contexta",
      "args": ["serve", "--root", "/path/to/your/code"]
    }
  }
}
```

Or if running from source:

```json
{
  "mcpServers": {
    "contexta": {
      "command": "python",
      "args": ["/path/to/contexta_mcp.py"]
    }
  }
}
```

The server reads only inside the folders you pass with `--root` (repeat the flag for more), or `CONTEXTA_ROOT`, or the folder it was started in. Paths outside, `..` escapes, symlinks that leave the project, and credential files such as `.env` or `id_rsa` are refused. `generate_context` accepts a `budget` argument.

### Available tools

| Tool | What it does |
|---|---|
| `scan_project` | Quick fingerprint — type, language, frameworks, deps, entry points |
| `get_architecture` | Module relationships, folder structure, risks, key patterns |
| `generate_context` | Full AI-optimized context pack with all preset options |
| `find_files` | Search files by name, extension, keyword, or file content and symbol names |
| `repo_map` | Ranked map of the important files and symbols in a small token budget (`budget`, `focus`) |
| `search_symbols` | Find a class, function or method by name |
| `impacted_tests` | Which tests to run for a change, and what else it reaches |
| `graph_query` | Dependents, dependencies, impact, changed-since, hot files from the [project graph](docs/graph.md) |
| `context_for` | A pack for a `task` within a `budget`: the files ranked for it plus the tests that cover them |
| `read_files` | Read specific file contents |
| `list_packs` | List available pack presets |
| `cache_status` | Show cache hit/miss statistics |
| `refresh_cache` | Force-refresh cached analysis |

### Agent setup in one command

```bash
contexta install cursor      # .cursor/rules/contexta.mdc
contexta install claude      # a managed block in CLAUDE.md
contexta install copilot     # a managed block in .github/copilot-instructions.md
contexta install mcp         # .mcp.json (--client cursor|vscode for the other editors)
```

<p align="center">
  <img alt="Terminal output of contexta install cursor and contexta install mcp creating the Cursor rule and .mcp.json, then a second run reporting ok" src="assets/install.png" width="860">
</p>

Safe to run twice: identical content is left alone, existing files are never overwritten without `--force`, and a file that already has other content only gets the Contexta block appended. `--dry-run` shows what would change.

### Smart cache

Results are cached in memory with automatic invalidation. First call analyzes the project (~700ms), subsequent calls return in ~2ms until files change on disk. The cache monitors file mtimes and manifest files — when you edit code, the next call recomputes automatically.

---

## Install

### Option A: pip (recommended)

```bash
pip install contexta-ai
# or, for a clean isolated CLI:
pipx install contexta-ai
contexta --help
```

Optional extras:

```bash
pip install "contexta-ai[syntax]"  # tree-sitter symbol maps for JS/TS/Go/Rust (a regex fallback is used without it)
pip install "contexta-ai[gui]"     # the same, for desktop users. Tk itself comes with Python (apt install python3-tk)
```

Optional AI API integrations:

```bash
pip install contexta-ai[claude]    # Claude API
pip install contexta-ai[gemini]    # Gemini API
pip install contexta-ai[openai]    # OpenAI API
pip install contexta-ai[all-ai]    # All three
```

### Option B: Portable executables

- **Windows**: download [`contexta.exe`](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta.exe)
  > **Windows 11:** right-click the downloaded `.exe` → Properties → check **Unblock** → OK before running.
- **Linux**: download [`contexta-linux.tar.gz`](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta-linux.tar.gz)

### Option C: From source

```bash
git clone https://github.com/pablokaua03/Contexta.git
cd Contexta
pip install -r requirements.txt
python contexta.py
```

---

## CLI usage

```bash
# Generate context packs
contexta .                                                   # default pack, or contexta.toml
contexta . --for onboard --copy                              # understand a repo, then paste it
contexta . --for review --stdout                             # this branch against main, with impacted tests
contexta . --for bugfix --focus "login timeout" --budget 20000
contexta graph impact src/app.py                             # what a change touches, and which tests to run
contexta install cursor                                      # agent rules for this project
contexta . --pack onboarding --copy                         # same as --for onboard
contexta . --pack bugfix --focus "login timeout"            # fix a bug with a coding agent
contexta . --pack pr_review --base main --stdout            # review this branch against main
contexta . --pack refactor --format json -o pack.json       # hand a refactor pack to another tool
contexta . --pack raw_files                                 # clean path + content dump
contexta . --budget 20000                                   # best files that fit 20k tokens
contexta . --focus "session cookie signing" --budget 8000  # a small pack about one topic
contexta . --dry-run                                        # list what would be redacted, write nothing

# First-time project setup
contexta --init                                              # writes contexta.toml and .contextaignore

# AI API integration — send context + question directly to an AI
contexta . --ask "what are the main security risks?"
contexta . --ask "explain the architecture" --provider claude

# Configure AI API keys
contexta --configure-ai
```

### CLI flags

| Flag | Description |
|---|---|
| `--for` | `bugfix`, `review` (against main), `onboard` or `refactor`. Picks the pack for you |
| `--no-graph` | Do not read or write `.contexta/graph.db` (also `graph = false` in `contexta.toml`) |
| `--pack` | Preset: `custom`, `chatgpt`, `onboarding`, `pr_review`, `risk_review`, `debug`, `bugfix`, `backend`, `frontend`, `changes_related`, `refactor`, `raw_files` |
| `--mode` | Context mode: `full`, `debug`, `feature`, `diff`, `onboarding`, `refactor` |
| `--compression` | `full`, `balanced`, `focused`, `signatures`, `lean` |
| `--ai` | Target AI profile used for budget guidance: `generic`, `chatgpt`, `claude`, `gemini`, `copilot` |
| `--task` | Task profile: `general`, `ai_handoff`, `bug_report`, `code_review`, `explain_project`, `risk_analysis`, `refactor_request`, `pr_summary`, `write_tests`, `find_dead_code` |
| `--focus` | Filter and rank by a topic (e.g. `"auth flow"`). Keeps the best matches and their tests and imports, not the whole repo |
| `--diff` / `--staged` | Use git changes as context |
| `--base` | Compare against a git ref such as `main` or `origin/main` (merge-base diff plus uncommitted work) |
| `--budget N` (alias `--max-tokens`) | Keep the highest-scoring files until the pack fits N tokens, tighten compression if needed, and list what was left out |
| `--max-files N` | File cap for the scan (default 2000, also `max_files` in `contexta.toml` or `CONTEXTA_MAX_FILES`) |
| `--format` | `md` (default) or `json` |
| `--stdout` | Write the pack to stdout. Also happens automatically when stdout is piped |
| `--redact` / `--no-redact` | Secret redaction is on by default. The two flags cannot be combined |
| `--dry-run` | Print file, line and rule of every value that would be redacted (never the value) and write no pack. Works with `--format json` |
| `--init` | Write `contexta.toml` and `.contextaignore` if they are missing |
| `--ask` | Send context pack + prompt to an AI API |
| `--provider` | AI provider: `claude`, `gemini`, `openai` |
| `--api-key` | API key (also reads `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`) |
| `--configure-ai` | Interactive AI API setup |
| `-c` / `--copy` | Copy output to clipboard |
| `-o` / `--output` | Custom output path. Use `-` for stdout |

CLI flags override `contexta.toml`, which overrides `~/.contexta/config.toml`. An explicit flag also wins over a pack preset, so `--pack pr_review --compression lean` stays lean.

### Daily handoff

| You are about to... | Command |
|---|---|
| Paste a project tour into a chat | `contexta . --pack onboarding --copy` |
| Fix a bug with Cursor, Claude Code, or Copilot | `contexta . --pack bugfix --focus "checkout error"` |
| Review the current branch against main | `contexta . --pack pr_review --base main --stdout` |
| Plan a refactor | `contexta . --pack refactor` |

The pack footer reports whether the export fits the selected profile. Planning windows include GPT-4o (128k), GPT-4.1 (about 1M), Claude Sonnet and Opus (200k), Gemini Flash and Pro (about 1M), and Copilot Chat / coding agent (64k / 128k). Contexta reserves 20% of each window for the question and the reply. These are planning numbers, not a provider quota.

Set `max_tokens` in `contexta.toml`, or pass `--budget`, and Contexta ranks the files, keeps the best ones that fit, and tightens compression only if it must. The pack gets a "Token Budget" section naming what was left out.

Before the pack is written, likely secrets are replaced with `[REDACTED]`: API keys, private keys, known token prefixes, bearer tokens, passwords in URLs, `password: ...` lines in JSON and YAML, and random-looking strings under secret-like names. Placeholders such as `your-api-key` are kept. Run `--dry-run` to see what would change. To keep a value, list it in `redact_allow` in `contexta.toml`, or put `contexta:allow` on its line. Files such as `.env`, private keys, `.npmrc` and `.netrc` are never read at all. This is best-effort and does not replace keeping secrets out of the tree. `--no-redact` disables redaction.

`contexta --init` writes a starter `contexta.toml` and `.contextaignore`. `.gitignore` is always applied. `.contextaignore` and the config `ignore` list add pack-only exclusions, using gitignore syntax, without changing what git tracks. A sample project file lives at [`docs/contexta.toml.example`](docs/contexta.toml.example).

---

## Project graph

Contexta keeps a local SQLite index of files, symbols, tests and how they connect (imports, calls, tests, git co-change) in `.contexta/graph.db`. It updates incrementally while it reads your project and answers questions the files alone cannot: who uses this function, what does this change reach, which tests should I run, which files change the most.

```bash
contexta graph impact src/app/session.py     # impacted files, plus tests to run
contexta graph map --budget 1500             # ranked repo map in about 1.5k tokens
contexta graph export -o graph.json          # JSON, JSONL or Markdown for other tools
```

Packs use it: with `--budget`, files the project depends on most are kept first, and on repos over 800 files a budgeted or focused run analyses the highest-ranked files instead of all of them. It never stores file contents, credential files or authors, and it is gitignored by default. Details in [docs/graph.md](docs/graph.md).

<p align="center">
  <img alt="Terminal output of contexta graph update, graph impact for a session file listing impacted files and tests to run, and graph hot listing the most changed files" src="assets/graph.png" width="860">
</p>

### In the pull request

The GitHub Action posts one comment per PR with the changed files, the tests worth running and what the change reaches, plus a redacted context pack within your token budget as an artifact. The comment is edited in place on later runs and lists paths only, never source. Details in [docs/github-action.md](docs/github-action.md).

<p align="center">
  <img alt="Pull request comment from the Contexta Action: 3 changed files, 4 tests to run, 3 files reached, about 2.8k tokens of a 24k budget, secrets redacted" src="assets/action.png" width="860">
</p>

---

## Context packs

| Pack | Best for |
|---|---|
| `onboarding` | Understanding a new codebase fast |
| `pr_review` | Code review with change context |
| `risk_review` | Regression hotspots, missing coverage, broad-impact modules |
| `debug` | Bug hunting with changed/suspicious files prioritized |
| `bugfix` | Daily bug-fix handoff for a coding agent |
| `refactor` | Modules to change plus the files connected to them |
| `backend` / `frontend` | Bias toward one side of the app |
| `changes_related` | Git changes + nearby relevant files |
| `raw_files` | Clean dump of important files — path + full content, no analysis |
| `chatgpt` | General-purpose ChatGPT preset |
| `custom` | Full manual control |

---

## What Contexta exports

Depending on pack, mode, and task, the output can include:

- Project summary with detected technologies, entry points, purpose, and central modules
- Read-this-first path through the repository
- Main execution flow narrative
- Core files, supporting files, related tests, and changed-file context
- Relationship maps and risk notes
- Score breakdown explaining why each file was selected
- Curated Markdown payload ready for any AI tool

---

## Main features

| Feature | Detail |
|---|---|
| **MCP Server** | `contexta serve` — AI tools call it as a tool server with smart caching |
| **AI API integration** | `--ask` sends context directly to Claude, Gemini, or OpenAI |
| **Smart cache** | ~2ms cached responses with automatic mtime-based invalidation |
| **Raw files pack** | Clean path + content dump for simple AI workflows |
| **GUI + CLI** | Desktop app for visual use, CLI for scripting and automation |
| **Project fingerprinting** | Detects stack, frameworks, domain, and project type automatically |
| **Syntax-aware analysis** | tree-sitter + heuristic fallback for symbol extraction |
| **Multi-language** | Python, JS/TS, Go, Rust, PHP, Java, C#, Kotlin, Swift, C++ and more |
| **Token budgets** | `--budget N` picks files by score until the pack fits, and reports what it dropped |
| **Focus** | `--focus "topic"` filters and ranks instead of only nudging scores |
| **Secret redaction** | Known token formats plus a high-entropy check, with a dry run and an allowlist |
| **Safe MCP** | Confined to `--root`, no symlink escapes, no credential files |
| **Fast** | A 2000-file repo scans in about 5 s; the old test-matching pass was quadratic |
| **PR base diff** | `--base main` packs the branch since the merge-base, plus uncommitted work |
| **Project config** | `contexta.toml`, `.contextaignore`, and optional `~/.contexta/config.toml` |
| **JSON export** | `--format json` wraps the same pack for tools that want structured input |
| **Inline blob protection** | Collapses base64/binary literals automatically |
| **PyPI package** | `pip install contexta-ai` with optional AI extras |

---

## Build from source

```bash
# Windows (requires Visual Studio C++ Build Tools)
.\build.bat

# Linux / macOS
chmod +x build.sh && ./build.sh
```

Build outputs: `dist/contexta.exe` (Windows), `dist/contexta` (Linux/macOS), `dist/contexta-linux.tar.gz` (Linux bundle).

---

## Run tests

```bash
python -m pytest tests/ -k "not test_relation_score"
```

---

## Security and behavior

- Read-only, with one exception: Contexta never modifies your files. It does keep its project graph in `.contexta/` (names, signatures and relations, never file contents; it ignores itself with a `*` `.gitignore`). Turn it off with `--no-graph` or `graph = false`, move it with `CONTEXTA_GRAPH_DIR`
- No runtime telemetry or network requirement (except optional `--ask` AI calls)
- Scan limit of 2000 files by default, raised with `--max-files`
- Embedded binary/blob payloads are suppressed automatically
- Likely secrets are redacted in exports and in MCP `read_files` unless `--no-redact` is set. `--dry-run` shows what would be redacted
- Credential files (`.env`, private keys, cloud and package-manager credentials) are skipped by the scan and refused by MCP
- The MCP server reads only inside `--root` / `CONTEXTA_ROOT` / its working directory
- Symlinks that point outside the project are not followed
- AI API keys are stored locally in `~/.contexta/ai_config.json` when using `--configure-ai`

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

## License

[MIT](LICENSE) © [pablokaua03](https://github.com/pablokaua03)

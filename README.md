<div align="center">

<img src="assets/logo.svg" width="88" alt="Contexta">

# Contexta

**Curated context packs for debugging, reviews, onboarding, and AI handoffs.**

Contexta reads a codebase, keeps the files that matter, and writes a Markdown pack you can paste into any assistant — or serve over MCP to Claude Code, Cursor, and Windsurf.

[![Python](https://img.shields.io/badge/python-3.11%2B-12211c?style=flat-square)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-12211c?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-12211c?style=flat-square)]()
[![Version](https://img.shields.io/badge/version-2.0.0-12211c?style=flat-square)]()
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

<sub>Dark and light share one layout, one type stack, and one mint accent.</sub>

</div>

---

## Before and after

The previous window was a single scrolling form: the same explanation appeared three times, secondary buttons looked disabled, and the preview was a wall of text. The current app is a split view. Controls stay on the left. The pack you are about to create stays on the right.

| Before | After |
| --- | --- |
| <img alt="Previous Contexta window: long form, flat preview, olive secondary buttons" src="docs/images/before-dark.png" width="460"> | <img alt="Current Contexta window: split layout, metric chips, and a structured preview" src="assets/dark.png" width="460"> |

Light theme, same structure:

| Before | After |
| --- | --- |
| <img alt="Previous light theme" src="docs/images/before-light.png" width="460"> | <img alt="Current light theme" src="assets/white.png" width="460"> |

---

## Install

### pip

```bash
pip install contexta-ai
```

Optional model SDKs, only if you use `--ask`:

```bash
pip install contexta-ai[claude]    # Claude
pip install contexta-ai[gemini]    # Gemini
pip install contexta-ai[openai]    # OpenAI
pip install contexta-ai[all-ai]    # all three
```

### Portable builds

- **Windows:** [`contexta.exe`](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta.exe). On Windows 11, right-click the file, open Properties, check **Unblock**, then run it.
- **Linux:** [`contexta-linux.tar.gz`](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta-linux.tar.gz)

### From source

```bash
git clone https://github.com/pablokaua03/Contexta.git
cd Contexta
pip install -r requirements.txt
python contexta.py
```

---

## Quickstart

```bash
contexta                                  # open the desktop app
contexta ./project --pack onboarding     # write a Markdown pack
contexta serve                            # MCP server for your editor
```

Three ways in:

| | Command | What you get |
| --- | --- | --- |
| **GUI** | `contexta` | Pick a folder, choose a pack, read the result in the window |
| **CLI** | `contexta ./project --pack onboarding` | A Markdown file on your desktop, or at `-o` |
| **MCP** | `contexta serve` | Tools your editor can call. No copy-paste |

---

## The desktop app

First launch asks for a folder and nothing else. The onboarding pack is already selected.

<img alt="Empty state: choose a project folder, then a pack, then create" src="assets/empty.png" width="960">

After a pack is written, the Result tab renders the Markdown with headings and code set apart from the prose. Activity under the preview records the scan. Errors show up in a banner you can dismiss, with the status chip switching to Error.

<img alt="Result view of a generated context pack for the sample-app project" src="assets/result.png" width="960">

---

## CLI

Interactive terminals get a short header, a mark on each progress line, and a `saved` line. Piped output stays plain text: no color, no extra prefix, same `Saved:` line as before. Set `NO_COLOR=1` or `CONTEXTA_COLOR=never` to force plain text. `CONTEXTA_COLOR=always` forces color.

<img alt="Terminal session running contexta on sample-app with the onboarding pack" src="assets/cli.png" width="760">

```bash
contexta ./project
contexta ./project --pack onboarding
contexta ./project --pack raw_files
contexta ./project --pack pr_review --diff --copy
contexta ./project --mode debug --focus "auth flow"

contexta ./project --ask "what are the main security risks?"
contexta ./project --ask "explain the architecture" --provider claude
contexta --configure-ai
```

### Flags

| Flag | Description |
| --- | --- |
| `--pack` | Preset: `custom`, `chatgpt`, `onboarding`, `pr_review`, `risk_review`, `debug`, `backend`, `frontend`, `changes_related`, `raw_files` |
| `--mode` | `full`, `debug`, `feature`, `diff`, `onboarding`, `refactor` |
| `--compression` | `full`, `balanced`, `focused`, `signatures`, `lean` |
| `--ai` | `generic`, `chatgpt`, `claude`, `gemini`, `copilot` |
| `--task` | `general`, `ai_handoff`, `bug_report`, `code_review`, `explain_project`, `risk_analysis`, `refactor_request`, `pr_summary`, `write_tests`, `find_dead_code` |
| `--focus` | Bias scoring around a topic, such as `"auth flow"` or `"database"` |
| `--diff` / `--staged` | Use git changes as context |
| `--ask` | Send the pack and a prompt to an AI API |
| `--provider` | `claude`, `gemini`, or `openai` |
| `--api-key` | API key. Also reads `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY` |
| `--configure-ai` | Save provider, key, and model under `~/.contexta/` |
| `-c` / `--copy` | Copy the pack to the clipboard |
| `-o` / `--output` | Write to this path instead of the desktop |

---

## Packs

| Pack | Best for |
| --- | --- |
| `onboarding` | A first pass through a new codebase |
| `pr_review` | Review with the change in view |
| `risk_review` | Hotspots, missing coverage, broad-impact modules |
| `debug` | Bug hunting, with changed and suspicious files first |
| `backend` / `frontend` | One side of the app |
| `changes_related` | Git changes plus the files next to them |
| `raw_files` | Path and full content, no analysis |
| `chatgpt` | A general ChatGPT preset |
| `custom` | Every control left as you set it |

Depending on pack, mode, and task, a pack can include a project summary, a read-this-first path, the main flow, core files, related tests, a relationship map, risk notes, and a score for why each file was kept.

---

## MCP server

Add this to Claude Code, Cursor, Windsurf, or any other MCP client:

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

From a source checkout:

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

| Tool | What it does |
| --- | --- |
| `scan_project` | Fingerprint: type, language, frameworks, dependencies, entry points |
| `get_architecture` | Modules, folders, risks, patterns |
| `generate_context` | A full pack, with the same presets as the CLI |
| `find_files` | Search by name, extension, or keyword |
| `read_files` | Read specific files |
| `list_packs` | List pack presets |
| `cache_status` | Cache hit and miss counts |
| `refresh_cache` | Force the next call to recompute |

The first call analyzes the project. Later calls reuse memory until a file or manifest changes on disk.

---

## What it does

| | |
| --- | --- |
| **GUI and CLI** | The same packs, one visual and one scriptable |
| **MCP server** | `contexta serve`, with a short-lived analysis cache |
| **AI APIs** | `--ask` sends a pack to Claude, Gemini, or OpenAI |
| **Fingerprints** | Stack, frameworks, domain, and project type |
| **Syntax** | tree-sitter, with a heuristic fallback |
| **Languages** | Python, JS/TS, Go, Rust, PHP, Java, C#, Kotlin, Swift, C++, and more |
| **Tokens** | tiktoken estimates so you can see the size before you paste |
| **Blobs** | Base64 and binary literals are collapsed instead of pasted |

Contexta does not modify the project it scans. It does not phone home. Network access is only the optional `--ask` call. API keys saved with `--configure-ai` stay in `~/.contexta/ai_config.json`.

---

## Build

```bash
# Windows, with the Visual Studio C++ build tools
.\build.bat

# Linux or macOS
chmod +x build.sh && ./build.sh
```

Outputs: `dist/contexta.exe` on Windows, `dist/contexta` on Linux and macOS, and `dist/contexta-linux.tar.gz` for the Linux bundle.

---

## Tests

```bash
python -m pytest tests/ -k "not test_relation_score"
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Changelog: [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE) © [pablokaua03](https://github.com/pablokaua03)

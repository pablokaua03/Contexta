<div align="center">

# Contexta

**Curated context packs for debugging, onboarding, reviews, refactors, and AI handoffs. Contexta analyzes the project first, then exports the most useful context for the job.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![Runtime Dependencies](https://img.shields.io/badge/Runtime%20Dependencies-Contexta%201.6-blue)]()
[![Version](https://img.shields.io/badge/Version-1.6.0-purple)]()

<br>

[<img src="https://img.shields.io/badge/Download%20for%20Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta.exe)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/Download%20for%20Linux-E95420?style=for-the-badge&logo=linux&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta-linux.tar.gz)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/All%20Releases-333?style=for-the-badge&logo=github&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest)

> Portable on Windows, installable on Linux, and runnable from source with Python.

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/white.png">
  <img alt="Contexta interface preview" src="assets/dark.png">
</picture>

</div>

---

## What Contexta exports

Contexta builds a context pack instead of dumping files blindly. Depending on pack, mode, and task, the output can include:

- A project summary with detected technologies, entry points, likely purpose, and central modules
- A read-this-first path through the repository
- A main execution flow narrative for the most relevant runtime path
- Core files, supporting files, related tests, and changed-file context
- Relationship maps and hotspot/risk notes
- A curated Markdown payload ready to paste into ChatGPT, Claude, Gemini, Copilot, or another coding assistant

Full mode still preserves raw code payloads. The intelligence is added around the payload, not instead of it.

---

## Why it is useful

Contexta is designed for the annoying part of AI-assisted coding: deciding what the model actually needs to see.

Use it when you want to:

- explain a project quickly to another developer or model
- review a change set with nearby context
- debug with changed files and likely hotspots already grouped
- onboard into an unfamiliar codebase
- hand off work between AI tools without rebuilding context from scratch

---

## Main features

| Feature | Detail |
|---|---|
| GUI + CLI | Desktop workflow for everyday use, plus command-line usage for scripting |
| Context packs | `custom`, `chatgpt`, `onboarding`, `pr_review`, `risk_review`, `debug`, `backend`, `frontend`, `changes_related` |
| Context modes | `full`, `debug`, `feature`, `diff`, `onboarding`, `refactor` |
| Compression modes | `full`, `balanced`, `focused`, `signatures`, `lean` |
| Task-aware output | Shapes the export for explanation, bug reports, code review, risk analysis, refactors, tests, dead-code hunting, or AI handoff |
| Project fingerprinting | Detects stack, frameworks, and project type before selecting files |
| Relationship map | Highlights local dependencies and likely related tests |
| Changed Files + Context | Pulls changed files up and expands into nearby relevant code |
| Selection reasons | Explains why each file was included in the payload |
| Read This First + Main Flow | Makes the pack easier for humans and models to navigate |
| Token guidance | Uses `tiktoken`-backed estimates for tighter compression and safer pack sizing |
| Inline blob protection | Automatically collapses base64/binary literals in all compression modes — no more 15 000-char icon blobs polluting the export |
| Syntax-aware analysis | Uses tree-sitter plus heuristic fallback to extract symbols across multiple languages |
| Multi-language detection | Recognizes Django, Kotlin Android, Spring Boot, Flutter, Rails, React, and more from project structure and import patterns |
| Build pipeline | Uses Nuitka for Windows and PyInstaller plus a Linux install bundle for Unix builds |

---

## Packs, modes, and compression

### Context packs

- `onboarding`: start here when you need to understand a project fast
- `pr_review`: emphasizes review-oriented context and recent changes
- `risk_review`: highlights likely regression hotspots, broad-impact modules, missing coverage, and maintenance weak spots
- `debug`: pushes suspicious and changed areas upward
- `backend` / `frontend`: bias selection toward that side of the app
- `changes_related`: starts from git changes and expands outward
- `custom`: leaves all fine-tuning to you

### Context modes

- `full`: fastest orientation plus the full selected code payload
- `debug`: favors hotspots, changed files, and likely failure paths
- `feature`: biases selection around the focus query
- `diff`: starts from git changes and nearby context
- `onboarding`: richer explanatory structure for first-time reading
- `refactor`: emphasizes central modules and connected files

### Compression modes

- `full`: keeps fuller file bodies and prioritizes fidelity (inline blobs still collapsed)
- `balanced`: mixes narrative, excerpts, and full payloads for important files
- `focused`: trims aggressively around the current task/focus
- `signatures`: structural overview for quick scanning
- `lean`: minimum token usage — metadata and up to 5 signatures per file (~65 tokens/file)

---

## Quickstart

### Option A: Windows executable

1. Download `contexta.exe` or `contexta-setup.exe`
2. Run it
3. Pick a project folder
4. Choose a pack, mode, task, and compression level
5. Create the pack and paste the Markdown into your AI tool

> Windows SmartScreen can still warn on unsigned open-source executables.

### Option B: Linux executable

1. Download `contexta-linux.tar.gz`
2. Extract it
3. Run `./install.sh` for a user-local install, or launch the bundled `contexta` binary directly

> Some Linux environments may require `python3-tk` if running from source instead.

### Option C: Run from source

```bash
git clone https://github.com/pablokaua03/Contexta.git
cd Contexta
python contexta.py
```

From source, install the runtime dependencies first:

```bash
python -m pip install -r requirements.txt
```

Some Linux environments may still require a separate `tkinter` system package such as `python3-tk`.

---

## CLI examples

```bash
python contexta.py /path/to/project
python contexta.py /path/to/project --pack onboarding
python contexta.py /path/to/project --pack risk_review
python contexta.py /path/to/project --mode debug --task bug_report --focus "auth flow"
python contexta.py /path/to/project --pack pr_review --diff --copy
python contexta.py /path/to/project --task ai_handoff --compression balanced --focus "theme"
```

### CLI options

| Flag | Description |
|---|---|
| `--hidden` | Include hidden folders/files |
| `--unknown` | Include files with unrecognized extensions |
| `--diff` | Prefer git diff context |
| `--staged` | Use staged changes only |
| `-p / --prompt` | Add a custom instruction or goal |
| `--focus` | Bias scoring, ordering, excerpts, and related context around a topic |
| `--mode` | Context selection mode |
| `--ai` | AI target profile |
| `--task` | Task profile |
| `--compression` | Compression strategy |
| `--pack` | Preset context pack |
| `-c / --copy` | Copy output to clipboard |
| `-o / --output` | Custom output path |
| `--version` | Print version |

---

## Prompting tips by AI target

### Generic LLM
- Usually works well: clear task, explicit output format
- Usually avoid: vague goals with no definition of done

### ChatGPT
- Usually works well: concise but precise instructions, short examples when helpful
- Usually avoid: mixing architecture analysis and implementation without priority

### Claude
- Usually works well: structured requests, architecture context plus a scoped goal
- Usually avoid: broad prompts with no prioritization

### Gemini
- Usually works well: broader context with explicit priorities, clear formatting instructions
- Usually avoid: assuming long context removes the need for structure

### Copilot / coding agents
- Usually works well: explicit files, constraints, and expected final state
- Usually avoid: open-ended requests with no target behavior

---

## Token guidance

| Rough size | Heuristic |
|---|---|
| `< 8k` | Usually manageable for most chat and coding tools |
| `8k - 32k` | Often comfortable for mainstream model sessions |
| `32k - 128k` | Better suited to larger-context sessions |
| `> 128k` | Consider long-context workflows or a tighter export |

---

## Build from source

```bash
# Windows
.\build.bat

# Linux / macOS
chmod +x build.sh && ./build.sh
```

Important:
- Build the Windows executable on Windows and the Linux package on Linux.
- Windows builds use Nuitka and require Visual Studio C++ Build Tools.
- Linux builds create both `dist/contexta` and `dist/contexta-linux.tar.gz`.
- On Debian/Ubuntu, install `python3-tk` before building.

Build outputs:
- Windows: `dist/contexta.exe`
- Windows installer: `dist/contexta-setup.exe` when Inno Setup is installed
- Linux / macOS: `dist/contexta`
- Linux install bundle: `dist/contexta-linux.tar.gz`

If you want the Linux package without setting up Linux locally, run the GitHub Actions workflow `.github/workflows/build-linux.yml` and download the `contexta-linux` artifact.

---

## Run tests

```bash
python -m unittest discover tests/
```

Current suite: run `python -m unittest discover tests/` to see the latest total.

---

## Security and behavior

- Read-only: Contexta does not modify the scanned project
- No runtime telemetry or network requirement in the app itself
- Scan limits prevent runaway exports
- Embedded binary/blob payloads are intentionally suppressed in focused excerpts
- Runtime dependencies are local analysis helpers (`pathspec`, `charset-normalizer`, `tiktoken`, `tree-sitter`, and `rapidfuzz`), not cloud services

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

## License

[MIT](LICENSE) © [pablokaua03](https://github.com/pablokaua03)

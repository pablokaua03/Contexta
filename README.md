<div align="center">

# Contexta

**Curated context packs for debugging, onboarding, reviews, refactors, and AI handoffs. Contexta analyzes the project first, then exports the most useful context for the job.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![Zero Runtime Dependencies](https://img.shields.io/badge/Runtime%20Dependencies-Zero-brightgreen)]()
[![Version](https://img.shields.io/badge/Version-1.4.0-purple)]()

<br>

[<img src="https://img.shields.io/badge/Download%20for%20Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta.exe)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/All%20Releases-333?style=for-the-badge&logo=github&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest)

> No installation needed. Download and run, or launch from source with Python.

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
| Context packs | `custom`, `chatgpt`, `onboarding`, `pr_review`, `debug`, `backend`, `frontend`, `changes_related` |
| Context modes | `full`, `debug`, `feature`, `diff`, `onboarding`, `refactor` |
| Compression modes | `full`, `balanced`, `focused`, `signatures` |
| Task-aware output | Shapes the export for explanation, bug reports, code review, refactors, tests, dead-code hunting, or AI handoff |
| Relationship map | Highlights local dependencies and likely related tests |
| Changed Files + Context | Pulls changed files up and expands into nearby relevant code |
| Selection reasons | Explains why each file was included in the payload |
| Read This First + Main Flow | Makes the pack easier for humans and models to navigate |
| Token guidance | Adds rough token estimates for planning, not exact promises |
| PyInstaller builds | Ships `contexta.exe` and `contexta-safe` build outputs |

---

## Packs, modes, and compression

### Context packs

- `onboarding`: start here when you need to understand a project fast
- `pr_review`: emphasizes review-oriented context and recent changes
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

- `full`: keeps fuller file bodies and prioritizes fidelity
- `balanced`: mixes narrative, excerpts, and full payloads for important files
- `focused`: trims aggressively around the current task/focus
- `signatures`: structural overview for quick scanning

---

## Quickstart

### Option A: Windows executable

1. Download `contexta.exe`
2. Run it
3. Pick a project folder
4. Choose a pack, mode, task, and compression level
5. Create the pack and paste the Markdown into your AI tool

> Windows SmartScreen can warn on unsigned open-source executables. If that happens, the `dist/contexta-safe/` onedir build is usually less troublesome.

### Option B: Run from source

```bash
git clone https://github.com/pablokaua03/Contexta.git
cd Contexta
python contexta.py
```

Contexta itself uses only the Python standard library at runtime. Some Linux environments may require a separate `tkinter` system package such as `python3-tk`.

---

## CLI examples

```bash
python contexta.py /path/to/project
python contexta.py /path/to/project --pack onboarding
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

Build outputs:
- `dist/contexta.exe`
- `dist/contexta-safe/contexta-safe.exe`

---

## Run tests

```bash
python -m unittest discover tests/
```

Current suite: **61 automated tests**

---

## Security and behavior

- Read-only: Contexta does not modify the scanned project
- No runtime telemetry or network requirement in the app itself
- Scan limits prevent runaway exports
- Embedded binary/blob payloads are intentionally suppressed in focused excerpts

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

## License

[MIT](LICENSE) © [pablokaua03](https://github.com/pablokaua03)
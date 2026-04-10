<div align="center">

# ⚡ mdcodebrief

**Scan any project folder and generate a structured `.md` file with full code context, ready to paste into AI chat interfaces. Zero dependencies, GUI + CLI.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero-brightgreen)]()
[![Version](https://img.shields.io/badge/Version-1.3.0-purple)]()

<br>

[<img src="https://img.shields.io/badge/⬇%20Download%20for%20Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" height="42">](https://github.com/pablokaua03/mdcodebrief/releases/latest/download/mdcodebrief.exe)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/All%20Releases-333?style=for-the-badge&logo=github&logoColor=white" height="42">](https://github.com/pablokaua03/mdcodebrief/releases/latest)

> No installation needed. Just download and run.

<br>

![mdcodebrief screenshot](assets/assets/screenshot.png)

</div>

---

## What is it?

`mdcodebrief` is a lightweight desktop tool that recursively scans a project folder and produces a single, well-structured Markdown file containing:

- A **visual directory tree** of the entire project
- Every **source file** with syntax-highlighted code blocks
- Relative paths, file sizes, and automatic truncation for large files

The output is designed to be **pasted directly into AI chat interfaces** (ChatGPT, Claude, Gemini, etc.) so the model has complete, unambiguous context about your project — no copy-pasting individual files.

---

## Features

| Feature | Detail |
|---|---|
| 🖥️ **Visual GUI** | Clean interface with dark/light theme toggle |
| ⌨️ **CLI mode** | Run headless for scripting or CI pipelines |
| 🌳 **Directory tree** | ASCII tree view at the top of every output file |
| 🎨 **Syntax highlighting** | 50+ extensions mapped to correct Markdown fences |
| 🔒 **Smart filtering** | Skips `node_modules`, `__pycache__`, `.git`, build dirs, lock files, binaries |
| 📋 **Native `.gitignore` support** | Reads and respects the project's `.gitignore` automatically |
| 📋 **Copy to clipboard** | One click (GUI) or `--copy` flag (CLI) |
| 🧮 **Token estimation** | Shows `~Xk tokens` with model recommendations |
| 🔀 **Git diff mode** | `--diff` — only scan files changed since last commit |
| 🤖 **AI instruction injection** | Prepend a custom prompt to the output |
| 🌗 **Dark / Light theme** | Toggle in the header — instant switch |
| 📏 **Safety limits** | Files truncated at 1 000 lines; scan stops at 2 000 files |
| 🌍 **Cross-platform** | Windows, macOS, Linux |
| 📦 **Zero dependencies** | Only Python standard library required |

---

## Quickstart

### Option A — Download the executable (no Python needed)

1. Download `mdcodebrief.exe` from the button above
2. Double-click to run

> ⚠️ **Windows SmartScreen warning:** Click **"More info"** → **"Run anyway"**. This is normal for open-source tools without a paid code signing certificate. You can also run directly from source with `python mdcodebrief.py`.

### Option B — Run from source

```bash
git clone https://github.com/pablokaua03/mdcodebrief.git
cd mdcodebrief
python mdcodebrief.py
```

### CLI mode

```bash
python mdcodebrief.py /path/to/project
python mdcodebrief.py /path/to/project -p "Find the memory leak"
python mdcodebrief.py /path/to/project --diff --copy
python mdcodebrief.py /path/to/project --diff --copy -p "Review this PR"
```

---

## CLI options

| Flag | Description |
|---|---|
| `--hidden` | Include hidden folders/files |
| `--unknown` | Include files with unrecognised extensions |
| `--diff` | Git diff mode — changed files only |
| `--staged` | Staged files only (`git diff --cached`) |
| `-p / --prompt` | Inject an AI instruction at the top |
| `-c / --copy` | Copy output to clipboard |
| `-o / --output` | Custom output path |
| `--version` | Print version |

---

## Token estimation guide

| Tokens | Recommended models |
|---|---|
| < 8k | Most models |
| 8k – 32k | GPT-4o · Claude Sonnet · Gemini Flash |
| 32k – 128k | Claude 200k · Gemini 1.5 Pro |
| > 128k | Gemini 1.5 Pro 1M |

---

## Build from source

```bash
# Windows
.\build.bat

# Linux / macOS
chmod +x build.sh && ./build.sh
```

---

## Security

- **Read-only** — never modifies your project files
- No network access, no telemetry, no external dependencies
- Hard limits prevent runaway scans

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

---

## License

[MIT](LICENSE) © [pablokaua03](https://github.com/pablokaua03)

# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

---

## [2.2.0] - 2026-10-24

Contexta now remembers your project. A local graph of files, symbols, tests and git history answers
"what does this change touch" and makes budgeted packs faster and better aimed.

### Added
- **Project graph** (`.contexta/graph.db`, SQLite, gitignored by default). Files, symbols and tests, with `imports`, `calls`, `tests` and git `cochange` edges. Updated incrementally by mtime and hash. Never stores file contents, credential files or authors, and signatures are redacted. `contexta graph update|status|clear|dependents|dependencies|impact|changed|hot|symbols|map|export`. Export as JSON (`contexta.graph.v1`), JSONL or Markdown. See [docs/graph.md](docs/graph.md)
- **Graph-aware packs.** With `--budget`, graph rank and churn raise a file's priority. With `--focus`, the tests that cover the matching files come along. On repos over 800 files, a budgeted or focused run analyses the 400 highest-ranked source files plus their tests instead of all of them: FastAPI at `--budget 20000` takes 1.4 s warm instead of 3.6 s. `--no-graph` or `graph = false` turns it off, `CONTEXTA_GRAPH_DIR` moves it
- **MCP v2 tools:** `repo_map`, `search_symbols`, `impacted_tests`, `graph_query` and `context_for(task, budget)`. `find_files` also searches file contents and symbol names, with redacted matches. All confined to the server roots
- **Repo map.** A ranked map of files and symbols inside a token budget. Python uses `ast`; JavaScript, TypeScript, Go and Rust use tree-sitter when installed, with a regex fallback
- **`contexta install cursor|claude|copilot|mcp`** writes agent rules or MCP config. Idempotent, merge-safe for existing JSON, never overwrites without `--force`, `--dry-run`
- **`--for bugfix|review|onboard|refactor`** picks the pack. `review` compares against `origin/main`, `main`, `origin/master` or `master`, whichever exists. `--help` is regrouped, with a short usage line and examples
- **GitHub Action** (`action.yml`): PR context with the diff, impacted tests and a redacted pack inside a token budget, as an artifact and an optional comment that updates in place. See [docs/github-action.md](docs/github-action.md)
- **Benchmark** against Repomix and Gitingest on Flask, Requests and FastAPI: tokens, time and recall, with the places Contexta loses. `python benchmarks/bench.py`
- **Project memory card** in the desktop app: status for the selected project (files, symbols, edges, last update) and **Update memory** (background thread), **Hot files**, **Symbols**, **Impact** and **Open map**. Answers show in a new **Memory** tab. Handles no project, an empty project, a missing `graph.db` (offers to build it) and unreadable files, in plain words
- **Per-analysis memory control.** A **Save this analysis to Contexta memory** toggle (on by default; off means the run may read an existing memory but never writes it) and a memory selector: this project's memory, another folder's memory (Browse), or none. Remembered between launches in `~/.contexta/gui.json`
- CLI: `--no-memory` (same as `--no-graph`), `--memory PATH` and `--memory-read-only`; config keys `memory_path` and `memory_save`
- A memory kept outside `.contexta/` is stamped with its project. A run never overwrites a memory that belongs to another project: it reads it, read-only, and says so
- `assets/memory.png`; `packaging/gui_screenshots.py` regenerates it

### Changed
- `tree-sitter` is now optional: `pip install "contexta-ai[syntax]"`. Without it, non-Python languages use a regex scanner. The `gui` extra installs the same parsers (Tk ships with Python and cannot come from pip). `contexta` without Tk now explains how to install it instead of failing with a traceback
- **Engine split.** `context_engine.py` (about 5,000 lines) is now `contexta_app/engine/`, 16 cohesive modules, and a facade that keeps every public name. Output is byte-identical
- When the file cap is hit, application code is scanned first, then tests, then `docs` and `examples`. On FastAPI the 2,000-file cap used to cut off the `fastapi/` package and pack `docs_src` instead
- When a file has more definitions than fit in a pack, the signature list keeps focus matches, then classes, then top-level functions, instead of the first 18 in file order. Focus stemming also matches `dependency` with `dependencies`
- Contexta writes `.contexta/` in the project (it ignores itself) unless `--no-graph` or `graph = false` is set. It still never modifies your files
- The desktop app now builds the project graph during an analysis by default (it used to skip it), so "save to memory" does what it says. Turn it off with the toggle or choose **None**. The Project card now says "Your files are never modified"
- Worker threads in the app no longer touch Tk widgets or call `after` from outside the UI thread

### Fixed
- "Scanning directory: assets/assets" repeated the folder name in the scan log
- The pack date used a fixed Brazilian format. It is ISO now (`2026-10-24 15:29:18`)
- The file-limit warning was printed once per folder on the way back up. It prints once

## [2.1.0] - 2026-10-24

This is a security and quality release. If you run the 2.0.0 MCP server, upgrade.

### Security
- **MCP root confinement** — the MCP server in 2.0.0 accepted any absolute path and could read any file the user could. Tools now read only inside `--root` (repeatable), `CONTEXTA_ROOT`, or the folder the server started in. Paths outside, `..` escapes, and symlinks that leave the project are refused. **Behavior change:** `contexta serve` without `--root` is limited to its working directory
- **Credential files are never read** — `.env*`, private keys, `.npmrc`, `.netrc`, cloud and package-manager credential files are skipped by the scan and refused by `read_files`. `.env.example` style templates still work
- **Redaction is complete** — 2.0.0 had no redaction in MCP `read_files` or in packs. Now a span-based engine covers known token formats, `password: ...` lines in JSON and YAML, and random-looking strings (high-entropy check, tuned for no false positives on Flask, Requests and FastAPI)
- **`--dry-run`** lists file, line and rule of every value that would be redacted, never the value. `--format json` is supported
- **Allowlist** — `redact_allow` in `contexta.toml`, or a `contexta:allow` / `pragma: allowlist secret` marker on the line
- `--redact` and `--no-redact` now share one option and cannot be combined
- The scanner no longer follows symlinks that point outside the project

### Added
- **`--budget N`** (alias `--max-tokens`) — picks files by score until the pack fits N tokens and lists what was left out in a "Token Budget" section. MCP `generate_context` takes `budget`
- **`--focus` filters and ranks** — `--focus "session cookie signing"` on Flask returns 8 files (about 17k tokens) with `sessions.py` first, instead of the whole repo (about 165k)
- **`--max-files`** — the 2000-file cap is configurable (also `max_files` in `contexta.toml`, `CONTEXTA_MAX_FILES`)
- Banner, colors and status lines go to stderr, so `--stdout` carries only the pack
- **Model token budgets** — every pack reports whether it fits the selected AI profile (GPT-4o, GPT-4.1, Claude Sonnet, Claude Opus, Gemini, Copilot Chat, and a generic long-context fallback)
- **PR-aware diffs** — `--base main` (or `origin/main`) selects files changed since the merge-base, including uncommitted work
- **Daily presets** — `bugfix` and `refactor` packs join the existing onboarding and PR review presets
- **Project config** — `contexta.toml` / `.contexta.toml` for defaults, plus `.contextaignore` and an `ignore` list on top of `.gitignore`. `contexta --init` writes starters. User defaults live in `~/.contexta/config.toml`
- **CLI handoff** — `--stdout` (and automatic stdout when piped), `--format json`, clipboard fallbacks for Wayland and X11, and errors that say what to run next

### Fixed
- **Wrong project descriptions** — a scanned project got Contexta's own text (Flask was "feeds, profiles, messaging", `cli.py` described Contexta's CLI). Descriptions now come from the project's own pyproject, package.json, Cargo.toml, composer.json, pubspec.yaml, or README
- **Performance** — the related-test matching compared every file with every other. FastAPI went from 69 s to 5 s, Flask from 2.9 s to 0.7 s, with identical selection
- GUI section subtitles were clipped on narrow cards
- `python -m contexta_app.cli` now runs the CLI
- Engine tests no longer need Tk; the production helper `test_relation_score` is now `related_test_score` (the old name remains as an alias) so pytest stops collecting it

### Changed
- Explicit CLI flags and project config now override pack presets. `--pack pr_review --compression lean` stays lean
- The README now leads with "the right context, inside your token budget, safe by default"

---

## [2.0.0] - 2026-07-11

### Added
- **MCP server** — `contexta serve` exposes `scan_project`, `get_architecture`, `generate_context`, `find_files`, `read_files`, `list_packs`, `cache_status`, and `refresh_cache` to Claude Code, Cursor, Windsurf, and other MCP clients
- **AI API integration** — `--ask` sends the pack and a question to Claude, Gemini, or OpenAI; `--configure-ai` stores keys locally
- **Smart cache** — in-memory analysis cache with mtime-based invalidation (~2 ms on a hit)
- **Raw files pack** — `raw_files` preset dumps path and content with no analysis
- **PyPI package** — `pip install contexta-ai`, with a trusted-publisher release workflow

---

## [1.6.0] - 2026-04-19

### Added
- **Token-Lean compression mode** - new `lean` option exports only file metadata and up to 5 signatures per file (~65 tokens/file). Best for quick orientation or tight API budget constraints
- **Inline blob sanitization** - any line longer than 400 chars that looks like a base64/binary payload (e.g. embedded icons, encoded assets) is automatically collapsed into a one-line placeholder comment in every compression mode, including Full Content. A 15 000-char base64 constant adds zero review value to any export
- **Multi-language project detection** - engine now correctly identifies Django (from imports alone, without `manage.py`), Kotlin Android, Spring Boot with Gradle, and more; fixes a long-standing bias where many projects were misclassified as PHP CRUD
- **Kotlin, Swift, C++, C, Scala, Lua, R, Nim, Zig** - added to language weights and tech labels; Kotlin/Java JVM detection unified so Kotlin-only Android projects are recognized correctly
- **Domain detection from directory names** - `boards/`, `sprints/`, `patients/`, `products/` and similar folder names now boost the domain classification without requiring manifest files
- **Syntax-aware parsing foundation** - Contexta now ships with `tree-sitter` and a dedicated syntax layer for stronger multi-language symbol extraction
- **Foundation runtime dependencies** - `pathspec`, `charset-normalizer`, `tiktoken`, and `rapidfuzz` are now part of the runtime analysis stack
- **Linux install bundle** - Linux builds now ship as `contexta-linux.tar.gz` with an `install.sh` helper for user-local installs
- **Optional Windows installer support** - `build.bat` now emits `contexta-setup.exe` whenever Inno Setup is available locally

### Changed
- **Gitignore handling** - scan filtering now uses Git-style pattern matching via `pathspec` instead of relying only on hand-rolled glob rules
- **File decoding** - file reading now prefers `charset-normalizer` before strict encoding fallbacks, improving support for real-world mixed encodings
- **Token estimation** - renderer token sizing now uses `tiktoken` instead of character heuristics alone when available
- **Test relationship scoring** - related-test detection now uses stronger fuzzy matching instead of substring checks alone
- **Windows build pipeline** - official Windows builds now use Nuitka onefile output
- **Linux build pipeline** - Unix builds now package both a portable binary and an installable tarball bundle
- **File role descriptions** - `requirements.txt`, `build.bat`, `build.sh` now show generic descriptions by default; project-specific text only appears when Contexta analyzes itself
- **XML file roles** - `AndroidManifest.xml`, `beans.xml`, `web.xml`, `docker-compose.yml`, `logback.xml`, and CI/CD workflow files now get accurate role descriptions

### Fixed
- **Scope vs insights bug** - `compute_project_type_signals` and `detect_domain_label` were accidentally receiving test and doc files in their input, causing wrong project type scores; now correctly filtered to runtime files only
- **Multi-language symbol extraction** - added better extraction coverage for Java, C#, Go, and Rust, plus tree-sitter-backed paths for supported languages
- **Scanner robustness** - unreadable files and legacy encodings now fall back more gracefully instead of being discarded too early

---

## [1.3.1] - 2026-04-11

### Changed
- **Compact, resizable interface** - reduced the default window size, added proper resize behavior, and tightened spacing so the app feels lighter on smaller screens
- **App branding refresh** - the GUI now uses the bundled `icon.ico` as the real window/app icon instead of the default feather-style fallback
- **Safer diff flow** - diff mode now behaves more predictably when there are no changed files, instead of surprising the user with a full-project export

### Added
- **36 unit tests** - expanded coverage for hidden-file filtering, diff behavior, renderer output, and related safety cases

### Fixed
- **Hidden file filtering** - dotfiles such as `.env` stay excluded by default when hidden files are not enabled
- **Git diff detection** - changed-file exports now better reflect staged, unstaged, and new-file workflows
- **Clipboard reliability** - clipboard writes now happen on the Tk main thread to avoid intermittent GUI issues

---

## [1.3.0] - 2025-04-10

### Changed
- **Modular architecture** - split into `scanner.py`, `renderer.py`, `theme.py`, `ui.py`, `cli.py`; `mdcodebrief.py` is now a clean 20-line entry point
- **Improved `.gitignore` parser** - now supports negation (`!`), rooted patterns (`/build`), directory-only patterns (`dist/`), and `**` wildcards
- **Version consistency** - `__version__` unified across all modules

### Added
- **33 unit tests** - covering scanner, renderer, gitignore parser, token estimation, and tree building (`unittest`, zero extra dependencies)
- Screenshot added to README with download button

### Fixed
- Windows SmartScreen false positive - removed `--add-data` from build scripts (`--noupx` retained)

---

## [1.2.0] - 2025-04-10

### Added
- Dark / Light theme toggle (instant switch, no rebuild)
- Pill-style toggle switches replacing checkboxes
- Two-column layout (AI Instruction + Options side by side)
- Status pill indicator (shows Scanning... / Done / Error)

### Fixed
- White Entry field on Windows (readonly state color bug)
- Progress bar style name incompatible with Python 3.14

---

## [1.1.0] - 2025-04-10

### Added
- Native `.gitignore` support
- Copy to clipboard - GUI button + `--copy` / `-c` CLI flag
- Token estimation with model hints in log and footer
- Git diff mode - `--diff` and `--staged` flags
- AI instruction injection - GUI text field + `-p / --prompt` CLI flag
- Build scripts (`build.bat`, `build.sh`)

---

## [1.0.0] - 2025-04-10

### Added
- GUI with dark theme (tkinter, zero dependencies)
- CLI mode
- Recursive project scanner with smart filtering
- ASCII directory tree
- Syntax-highlighted code blocks for 50+ extensions
- Multi-encoding file reader (UTF-8, latin-1, cp1252, UTF-16)
- Safety limits: 1 000 lines/file, 2 000 files/scan
- Cross-platform Desktop path detection
- MIT License

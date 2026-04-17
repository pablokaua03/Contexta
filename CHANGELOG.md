# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

---

## [1.5.0] - 2026-04-12

### Changed
- **Project fingerprinting** - Contexta now builds a stronger project fingerprint before the summary, using stack-defining files and explicit ecosystem rules
- **Stack-aware summaries** - project summaries now separate primary language, frameworks, and supporting technologies instead of leaning on extension counts alone
- **Identity-aware scoring** - dependency manifests, framework configs, and build files now influence file importance much more directly

### Fixed
- **Onboarding balance** - onboarding now keeps tests lighter in the payload and prefers shorter, more explanatory excerpts
- **Bundled icon loading** - the packaged executable now ships the runtime `icon.ico` so the window and in-app branding can load it consistently

---

## [1.5.0] - 2026-04-11

### Changed
- **Contexta rebrand** - the app now ships as `Contexta`, with refreshed green branding, a new window title, and build output renamed to `contexta`
- **Premium daily-use interface** - redesigned the GUI around packs, context modes, AI targets, task presets, compression controls, and a live pack preview
- **Curated export pipeline** - exports now start with structural analysis instead of jumping straight into raw file dumps

### Added
- **Project Summary** - every pack now opens with detected technologies, likely entry points, important files, architecture notes, and likely purpose
- **Smart context modes** - added `full`, `debug`, `feature`, `diff`, `onboarding`, and `refactor` selection strategies
- **Relationship map** - Contexta now infers local dependencies and likely related test files
- **Task + AI profiles** - exports can be shaped for ChatGPT, Claude, Gemini, Copilot, or a generic LLM, plus review/debug/refactor/test-focused tasks
- **Context compression** - added balanced, focused, and signatures-only modes to reduce wasted tokens
- **More renderer coverage** - tests now cover the new summary sections and compression behavior

### Fixed
- **Theme toggle polish** - restored real sun/moon visuals in the header instead of literal fallback text
- **Executable naming** - build scripts now generate `contexta.exe`

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

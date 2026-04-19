# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

---

## [1.6.0] - 2026-04-17

### Added
- **Syntax-aware parsing foundation** - Contexta now ships with `tree-sitter` and a dedicated syntax layer for stronger multi-language symbol extraction
- **Foundation runtime dependencies** - `pathspec`, `charset-normalizer`, `tiktoken`, and `rapidfuzz` are now part of the runtime analysis stack
- **Linux install bundle** - Linux builds now ship as `contexta-linux.tar.gz` with an `install.sh` helper for user-local installs
- **Optional Windows installer support** - `build.bat` now emits `contexta-setup.exe` whenever Inno Setup is available locally

### Changed
- **Version upgrade** - repository version markers, packaged metadata, and docs now target `1.6.0`
- **Gitignore handling** - scan filtering now uses Git-style pattern matching via `pathspec` instead of relying only on hand-rolled glob rules
- **File decoding** - file reading now prefers `charset-normalizer` before strict encoding fallbacks, improving support for real-world mixed encodings
- **Token estimation** - renderer token sizing now uses `tiktoken` instead of character heuristics alone when available
- **Test relationship scoring** - related-test detection now uses stronger fuzzy matching instead of substring checks alone
- **Windows build pipeline** - official Windows builds now use Nuitka onefile output
- **Linux build pipeline** - Unix builds now package both a portable binary and an installable tarball bundle
- **Project positioning** - docs and contribution rules now describe Contexta as syntax-aware and stack-aware instead of a zero-dependency tool

### Fixed
- **Multi-language symbol extraction** - added better extraction coverage for Java, C#, Go, and Rust, plus tree-sitter-backed paths for supported languages
- **Scanner robustness** - unreadable files and legacy encodings now fall back more gracefully instead of being discarded too early
- **Version drift** - stale pre-1.6 markers and legacy packaging artifacts were cleaned up from the active release surface

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

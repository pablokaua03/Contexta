"""
scanner.py — Project scanning, filtering, .gitignore support, git diff.
"""

import fnmatch
import subprocess
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

CODE_EXTENSIONS: dict[str, str] = {
    ".html": "html", ".htm": "html", ".css": "css", ".scss": "scss",
    ".sass": "sass", ".less": "less", ".js": "javascript", ".jsx": "jsx",
    ".ts": "typescript", ".tsx": "tsx", ".vue": "vue", ".svelte": "svelte",
    ".py": "python", ".rb": "ruby", ".php": "php", ".java": "java",
    ".cs": "csharp", ".csproj": "xml", ".go": "go", ".rs": "rust", ".cpp": "cpp",
    ".c": "c", ".h": "c", ".hpp": "cpp", ".swift": "swift",
    ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash", ".fish": "fish",
    ".ps1": "powershell", ".bat": "bat", ".cmd": "bat",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".properties": "ini",
    ".ini": "ini", ".cfg": "ini", ".env": "dotenv",
    ".xml": "xml", ".graphql": "graphql", ".proto": "protobuf",
    ".md": "markdown", ".mdx": "mdx", ".rst": "rst", ".txt": "text",
    ".sql": "sql", ".tf": "hcl", ".hcl": "hcl",
    "dockerfile": "dockerfile", ".dockerfile": "dockerfile",
    "go.mod": "text", "build.gradle": "text", "settings.gradle": "text",
    "gemfile": "ruby", "mix.exs": "elixir", "mix.lock": "text",
    "angular.json": "json", "pubspec.yaml": "yaml", "pubspec.yml": "yaml",
    "nuxt.config.ts": "typescript", "nuxt.config.js": "javascript",
    "astro.config.mjs": "javascript", "astro.config.ts": "typescript",
    "remix.config.js": "javascript", "remix.config.ts": "typescript",
    ".r": "r", ".lua": "lua", ".ex": "elixir", ".exs": "elixir",
    ".dart": "dart", ".nim": "nim", ".zig": "zig",
}

IGNORE_DIRS: set[str] = {
    ".git", ".svn", ".hg", ".bzr",
    "node_modules", ".npm", ".yarn", ".pnp",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "venv", ".venv", "env", ".env",
    ".tox", ".nox",
    "dist", "build", ".build", "out",
    ".next", ".nuxt", ".svelte-kit", ".astro",
    "coverage", ".coverage", "htmlcov",
    ".idea", ".vscode", ".vs",
    "*.egg-info", ".eggs",
    "target", "vendor", ".terraform",
    "tmp", "temp", ".tmp", ".temp",
    "logs", ".logs", "cache", ".cache",
}

IGNORE_FILES: set[str] = {
    ".DS_Store", "Thumbs.db", "desktop.ini",
    ".gitignore", ".gitattributes", ".gitmodules",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile.lock", "poetry.lock", "composer.lock", "Cargo.lock",
}

IGNORE_SUFFIXES: tuple[str, ...] = (
    ".pyc", ".pyo", ".pyd", ".class",
    ".o", ".obj", ".a", ".lib", ".so", ".dll", ".dylib",
    ".exe", ".bin", ".wasm", ".log", ".map",
    ".min.js", ".min.css",
)

MAX_FILE_LINES  = 1_000
MAX_TOTAL_FILES = 2_000


# ─────────────────────────────────────────────────────────────────────────────
# LANGUAGE DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def get_language(filepath: Path) -> str | None:
    name_lower = filepath.name.lower()
    if name_lower in CODE_EXTENSIONS:
        return CODE_EXTENSIONS[name_lower]
    return CODE_EXTENSIONS.get(filepath.suffix.lower())


# ─────────────────────────────────────────────────────────────────────────────
# GITIGNORE PARSER  — supports negation (!) and directory patterns
# ─────────────────────────────────────────────────────────────────────────────

def load_gitignore_patterns(root: Path) -> list[str]:
    """Read .gitignore at project root and return list of raw patterns."""
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return []
    patterns: list[str] = []
    try:
        for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    except Exception:
        pass
    return patterns


def matches_gitignore(path: Path, root: Path, patterns: list[str]) -> bool:
    """
    Check whether *path* is ignored by the given gitignore patterns.

    Supports:
    - Simple glob patterns       e.g.  *.log
    - Directory-only patterns    e.g.  dist/
    - Rooted patterns            e.g.  /build
    - Recursive wildcards        e.g.  **/logs
    - Negation patterns          e.g.  !important.log  (re-includes previously ignored files)
    """
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False

    name    = path.name
    ignored = False

    for pattern in patterns:
        negate = pattern.startswith("!")
        p      = pattern.lstrip("!").strip()
        if not p:
            continue

        dir_only = p.endswith("/")
        p = p.rstrip("/")

        # Rooted pattern (starts with /)
        if p.startswith("/"):
            p = p.lstrip("/")
            matched = fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p + "/*")
        elif "**" in p:
            # Handle ** wildcard
            matched = fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p)
        elif "/" in p:
            # Pattern with slash — match against full relative path
            matched = fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p + "/*")
        else:
            # Simple pattern — match name or any path segment
            matched = (
                fnmatch.fnmatch(name, p)
                or fnmatch.fnmatch(rel, p)
                or fnmatch.fnmatch(rel, f"**/{p}")
                or fnmatch.fnmatch(rel, p + "/*")
            )

        if dir_only and not path.is_dir():
            matched = False

        if matched:
            ignored = not negate   # negation flips the state

    return ignored


# ─────────────────────────────────────────────────────────────────────────────
# GIT DIFF
# ─────────────────────────────────────────────────────────────────────────────

def get_git_changed_files(root: Path, staged_only: bool = False) -> list[Path] | None:
    """
    Return list of changed files via git diff.
    Returns None if not a git repo or git is unavailable.
    """
    try:
        inside_work_tree = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if inside_work_tree.returncode != 0 or inside_work_tree.stdout.strip() != "true":
            return None

        commands = (
            [["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]]
            if staged_only
            else [
                ["git", "diff", "--name-only", "--diff-filter=ACMR"],
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                ["git", "ls-files", "--others", "--exclude-standard"],
            ]
        )

        changed_relpaths: set[str] = set()
        for cmd in commands:
            result = subprocess.run(
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None
            changed_relpaths.update(
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip()
            )

        files = []
        for relpath in sorted(changed_relpaths):
            p = root / relpath
            if p.is_file():
                files.append(p)
        return files
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# FILE READING
# ─────────────────────────────────────────────────────────────────────────────

def read_file_safe(filepath: Path) -> tuple[str, bool, int]:
    """
    Read a text file safely, trying multiple encodings.
    Returns (content, was_truncated, total_line_count).
    """
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "utf-16"):
        try:
            raw = filepath.read_text(encoding=enc, errors="strict")
            lines = raw.splitlines()
            if len(lines) > MAX_FILE_LINES:
                return "\n".join(lines[:MAX_FILE_LINES]), True, len(lines)
            return raw, False, len(lines)
        except (UnicodeDecodeError, PermissionError):
            continue
    fallback = "_[Binary or unreadable file — content omitted]_"
    return fallback, False, len(fallback.splitlines())


# ─────────────────────────────────────────────────────────────────────────────
# FILTERING
# ─────────────────────────────────────────────────────────────────────────────

def should_ignore_dir(name: str, include_hidden: bool) -> bool:
    if name in IGNORE_DIRS:
        return True
    if not include_hidden and name.startswith("."):
        return True
    return False


def should_ignore_file(
    path: Path,
    include_unknown: bool,
    include_hidden: bool = False,
    root: Path | None = None,
    gitignore_patterns: list[str] | None = None,
) -> bool:
    name = path.name
    if not include_hidden and name.startswith("."):
        return True
    if name in IGNORE_FILES:
        return True
    for suffix in IGNORE_SUFFIXES:
        if name.endswith(suffix):
            return True
    if gitignore_patterns and root:
        if matches_gitignore(path, root, gitignore_patterns):
            return True
    if get_language(path) is None and not include_unknown:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# TREE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_tree(
    root: Path,
    include_hidden: bool,
    include_unknown: bool,
    log_cb,
    counter: list[int],
    gitignore_patterns: list[str],
    project_root: Path,
) -> dict:
    """Recursively build a tree dict of the project."""
    node: dict = {"name": root.name, "path": root, "dirs": [], "files": []}

    try:
        entries = sorted(root.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except PermissionError:
        log_cb(f"⚠  Permission denied: {root}", "warn")
        return node

    for entry in entries:
        if counter[0] >= MAX_TOTAL_FILES:
            log_cb(f"⚠  Reached {MAX_TOTAL_FILES}-file limit. Scan stopped.", "warn")
            return node

        if entry.is_dir():
            if should_ignore_dir(entry.name, include_hidden):
                continue
            if gitignore_patterns and matches_gitignore(entry, project_root, gitignore_patterns):
                continue
            log_cb(f"📁  {entry.relative_to(root.parent)}", "muted")
            node["dirs"].append(build_tree(
                entry, include_hidden, include_unknown,
                log_cb, counter, gitignore_patterns, project_root,
            ))
        elif entry.is_file():
            if should_ignore_file(
                entry,
                include_unknown,
                include_hidden=include_hidden,
                root=project_root,
                gitignore_patterns=gitignore_patterns,
            ):
                continue
            counter[0] += 1
            node["files"].append({
                "name": entry.name,
                "path": entry,
                "lang": get_language(entry),
            })

    return node


def build_diff_tree(
    changed_files: list[Path],
    root: Path,
    include_hidden: bool,
    include_unknown: bool,
    gitignore_patterns: list[str],
) -> dict:
    """Build a minimal tree containing only git-changed files."""
    node: dict = {"name": root.name, "path": root, "dirs": [], "files": []}

    for fpath in changed_files:
        if should_ignore_file(
            fpath,
            include_unknown,
            include_hidden=include_hidden,
            root=root,
            gitignore_patterns=gitignore_patterns,
        ):
            continue

        try:
            parts = fpath.relative_to(root).parts
        except ValueError:
            continue

        current = node
        current_path = root
        for part in parts[:-1]:
            current_path = current_path / part
            existing = next((d for d in current["dirs"] if d["name"] == part), None)
            if not existing:
                existing = {
                    "name": part,
                    "path": current_path,
                    "dirs": [], "files": [],
                }
                current["dirs"].append(existing)
            current = existing

        current["files"].append({
            "name": fpath.name,
            "path": fpath,
            "lang": get_language(fpath),
        })

    return node


def count_files(node: dict) -> int:
    return len(node["files"]) + sum(count_files(d) for d in node["dirs"])

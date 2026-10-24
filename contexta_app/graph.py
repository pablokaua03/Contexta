"""
graph.py - A persistent memory of the project, in SQLite.

``.contexta/graph.db`` holds files, symbols and the edges between them:
imports, calls, test -> source, and co-change from ``git log``. Contexta keeps it
current as it reads the project: a file is parsed again only when its size or
mtime changed and its content hash differs.

What is stored: paths, content hashes, symbol names and trimmed signatures,
edges, and commit timestamps. What is not: file content, author names or
emails, or anything the redactor would remove. Signatures pass through the
redactor, and credential files are never indexed.

``.contexta/`` gets its own ``.gitignore`` so the database stays out of commits
without touching the project's own ``.gitignore``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from contexta_app.redaction import redact_secrets
from contexta_app.safety import is_sensitive_path
from contexta_app.symbols import MODULE_SCOPE, FileFacts, ImportRef, extract_facts

SCHEMA_VERSION = 2
GRAPH_DIRNAME = ".contexta"
GRAPH_FILENAME = "graph.db"
MAX_PARSE_BYTES = 600_000
GIT_LOG_COMMITS = 1000
COCHANGE_MAX_FILES_PER_COMMIT = 25
COCHANGE_MIN_COUNT = 2
COCHANGE_KEEP_PER_FILE = 12
UNIQUE_NAME_MIN_LEN = 5
CODE_LANGS = frozenset(
    "python javascript typescript tsx jsx go rust java php ruby csharp kotlin swift c cpp scala vue svelte".split()
)
_TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs", "testing"}
_TEST_NAME = re.compile(r"(^test_.+|.+_test\.\w+$|.+\.(?:test|spec)\.\w+$|^test\.\w+$|.+tests?\.(?:cs|java|kt)$)", re.I)
_GENERIC_STEMS = frozenset({"__init__", "init", "index", "main", "conftest", "app", "utils", "util", "base", "common", "setup", "settings", "config"})
_LOW_VALUE_DIRS = frozenset({"examples", "example", "docs", "docs_src", "doc", "samples", "demo", "demos", "scripts", "benchmarks", "tutorial"})
_HUB_NAMES = frozenset({"__init__.py", "index.ts", "index.tsx", "index.js", "index.jsx", "mod.rs"})
_COMMON_NAMES = frozenset(
    "get set add run main init str int list dict len print open read write close join split items keys values "
    "append update copy format sorted range super self test setup teardown call send start stop".split()
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY, hash TEXT, mtime_ns INTEGER, size INTEGER, lang TEXT,
    kind TEXT, lines INTEGER, backend TEXT, rank REAL DEFAULT 0, indexed_at REAL
);
CREATE TABLE IF NOT EXISTS symbols (
    path TEXT, name TEXT, qualname TEXT, kind TEXT, line INTEGER, end_line INTEGER,
    signature TEXT, parent TEXT
);
CREATE INDEX IF NOT EXISTS symbols_path ON symbols(path);
CREATE INDEX IF NOT EXISTS symbols_name ON symbols(name);
CREATE TABLE IF NOT EXISTS imports_raw (path TEXT, module TEXT, level INTEGER, names TEXT, line INTEGER);
CREATE INDEX IF NOT EXISTS imports_raw_path ON imports_raw(path);
CREATE TABLE IF NOT EXISTS calls_raw (path TEXT, caller TEXT, callee TEXT);
CREATE INDEX IF NOT EXISTS calls_raw_path ON calls_raw(path);
CREATE TABLE IF NOT EXISTS edges (
    src_file TEXT, src_sym TEXT, dst_file TEXT, dst_sym TEXT, kind TEXT, weight REAL, detail TEXT,
    PRIMARY KEY (src_file, src_sym, dst_file, dst_sym, kind)
);
CREATE INDEX IF NOT EXISTS edges_src ON edges(src_file, kind);
CREATE INDEX IF NOT EXISTS edges_dst ON edges(dst_file, kind);
CREATE TABLE IF NOT EXISTS history (path TEXT, ts INTEGER, commit_id TEXT);
CREATE INDEX IF NOT EXISTS history_path ON history(path);
CREATE INDEX IF NOT EXISTS history_ts ON history(ts);
"""


@dataclass
class UpdateStats:
    total: int = 0
    added: int = 0
    changed: int = 0
    removed: int = 0
    unchanged: int = 0
    symbols: int = 0
    edges: int = 0
    seconds: float = 0.0
    git_commits: int = 0
    skipped_reason: str = ""

    def to_dict(self) -> dict:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.__dict__.items()}

    def summary(self) -> str:
        if self.skipped_reason:
            return f"Graph not updated: {self.skipped_reason}"
        return (
            f"Graph: {self.total} file(s), {self.added} new, {self.changed} changed, {self.removed} removed, "
            f"{self.unchanged} unchanged, {self.symbols} symbols, {self.edges} edges ({self.seconds:.2f}s)"
        )


# ------------------------------------------------------------------ helpers


def classify_kind(rel: str, lang: str | None) -> str:
    parts = PurePosixPath(rel).parts
    name = parts[-1]
    if lang in CODE_LANGS and (any(part.lower() in _TEST_DIRS for part in parts[:-1]) or _TEST_NAME.match(name)):
        return "test"
    if lang in {"markdown", "mdx", "rst", "text"}:
        return "doc"
    if lang in {"json", "yaml", "toml", "ini", "xml", "dotenv"}:
        return "config"
    if lang in CODE_LANGS:
        return "source"
    return "other"


def _test_stem(name: str) -> str:
    stem = PurePosixPath(name).stem
    for pattern in (r"^test_", r"_test$", r"\.test$", r"\.spec$", r"^test$"):
        stem = re.sub(pattern, "", stem)
    stem = re.sub(r"\.(test|spec)$", "", stem)
    return stem.lower()


def _git(root: Path, *args: str, timeout: int = 30) -> str | None:
    try:
        result = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _safe_signature(text: str) -> str:
    cleaned, _ = redact_secrets(text)
    return cleaned


def _now() -> float:
    return time.time()


def _iso(ts: float | int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------- import resolver

_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")
_LANG_EXTS = {
    "java": (".java",), "kotlin": (".kt", ".kts"), "scala": (".scala",), "csharp": (".cs",), "php": (".php",),
    "ruby": (".rb",), "swift": (".swift",), "c": (".h", ".c"), "cpp": (".hpp", ".h", ".cpp", ".cc", ".c"),
    "go": (".go",), "rust": (".rs",),
}


class Resolver:
    """Maps raw import strings to project files. Pure lookups over the file list."""

    def __init__(self, files: dict[str, str]):
        self.files = files  # path -> lang
        self.paths = set(files)
        self.py_exact: dict[str, str] = {}
        self.py_suffix: dict[str, list[str]] = defaultdict(list)
        self.by_dir: dict[str, list[str]] = defaultdict(list)
        self.suffix_index: dict[str, list[str]] = defaultdict(list)
        for path, lang in files.items():
            pp = PurePosixPath(path)
            self.by_dir[str(pp.parent)].append(path)
            noext = path[: -len(pp.suffix)] if pp.suffix else path
            parts = noext.split("/")
            for i in range(len(parts)):
                self.suffix_index["/".join(parts[i:]).lower()].append(path)
            if lang == "python":
                mod = parts[:-1] if parts[-1] == "__init__" else parts
                if mod:
                    self.py_exact[".".join(mod)] = path
                    for i in range(len(mod)):
                        self.py_suffix[".".join(mod[i:])].append(path)

    def _pick(self, candidates: list[str], importer: str) -> str | None:
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        ip = importer.split("/")

        def key(path: str):
            shared = 0
            for a, b in zip(ip, path.split("/")):
                if a != b:
                    break
                shared += 1
            return (-shared, len(path))

        return sorted(candidates, key=key)[0]

    # Python
    def _py_module(self, dotted: str, importer: str, absolute_only: bool = False) -> str | None:
        if not dotted:
            return None
        hit = self.py_exact.get(dotted)
        if hit:
            return hit
        return self._pick(self.py_suffix.get(dotted, []), importer)

    def python(self, importer: str, ref: ImportRef) -> list[tuple[str, str]]:
        """``(file, detail)`` targets. ``detail`` is the imported names, for symbol-level questions."""
        out: list[tuple[str, str]] = []
        if ref.level:
            pkg = importer.split("/")[:-1]
            up = ref.level - 1
            if up > len(pkg):
                return out
            base = pkg[: len(pkg) - up] if up else pkg
            base_dotted = ".".join(base + (ref.module.split(".") if ref.module else []))
            target = self.py_exact.get(base_dotted) if base_dotted else None
            if target and target != importer:
                out.append((target, ",".join(ref.names)))
            for name in ref.names:
                sub = self.py_exact.get(".".join(filter(None, [base_dotted, name])))
                if sub and sub != importer:
                    out.append((sub, name))
            return out
        target = self._py_module(ref.module, importer)
        if target and target != importer:
            out.append((target, ",".join(ref.names)))
        for name in ref.names:
            sub = self._py_module(f"{ref.module}.{name}", importer) if ref.module else self._py_module(name, importer)
            if sub and sub != importer:
                out.append((sub, name))
        return out

    # JS / TS
    def js(self, importer: str, ref: ImportRef) -> list[tuple[str, str]]:
        spec = ref.module
        if not spec:
            return []
        bases: list[str] = []
        if spec.startswith("."):
            bases.append(os.path.normpath(os.path.join(str(PurePosixPath(importer).parent), spec)).replace("\\", "/"))
        elif spec.startswith(("@/", "~/")):
            bases += [spec[2:], "src/" + spec[2:]]
        elif spec.startswith("src/"):
            bases.append(spec)
        for base in bases:
            if base in self.paths:
                return [(base, "")]
            for ext in _JS_EXTS:
                if base + ext in self.paths:
                    return [(base + ext, "")]
            for ext in _JS_EXTS:
                if f"{base}/index{ext}" in self.paths:
                    return [(f"{base}/index{ext}", "")]
        return []

    # everything else: path-suffix matching
    def generic(self, importer: str, ref: ImportRef, lang: str) -> list[tuple[str, str]]:
        spec = ref.module
        if not spec:
            return []
        exts = _LANG_EXTS.get(lang, ())
        if lang in {"c", "cpp", "ruby"}:
            rel = os.path.normpath(os.path.join(str(PurePosixPath(importer).parent), spec)).replace("\\", "/")
            for cand in (rel, rel + ".rb"):
                if cand in self.paths:
                    return [(cand, "")]
            key = spec.lower()
            key = key[: -len(PurePosixPath(key).suffix)] if PurePosixPath(key).suffix else key
            hit = self._pick(self.suffix_index.get(key, []), importer)
            return [(hit, "")] if hit and hit != importer else []
        if lang == "go":
            tail = "/".join(spec.split("/")[-2:])
            dirs = [d for d in self.by_dir if d.endswith(tail) or d == spec.split("/")[-1]]
            out = []
            for d in dirs[:1]:
                for path in sorted(self.by_dir[d]):
                    if path.endswith(".go") and not path.endswith("_test.go") and path != importer:
                        out.append((path, ""))
            return out[:8]
        if lang == "rust":
            return self._rust(importer, spec)
        sep = "\\" if lang == "php" else "."
        key = spec.replace(sep, "/").lower()
        # a.b.C or a.b.C.method -> try full, then drop trailing parts
        parts = key.split("/")
        for end in range(len(parts), max(len(parts) - 2, 0), -1):
            hit = self._pick(self.suffix_index.get("/".join(parts[:end]), []), importer)
            if hit and hit != importer and (not exts or hit.endswith(exts)):
                return [(hit, "")]
        return []

    def _rust(self, importer: str, spec: str) -> list[tuple[str, str]]:
        here = PurePosixPath(importer).parent
        spec = spec.strip()
        cands: list[str] = []
        if re.fullmatch(r"[A-Za-z_]\w*", spec):  # `mod x;`
            cands += [f"{here}/{spec}.rs", f"{here}/{spec}/mod.rs"]
        elif spec.startswith("crate::"):
            seg = [s for s in re.split(r"::|[{},\s]+", spec[7:]) if s]
            src_roots = {p.split("/src/")[0] + "/src" if "/src/" in p else "src" for p in self.paths if p.endswith(("lib.rs", "main.rs"))}
            for root in src_roots or {"src"}:
                for end in range(len(seg), 0, -1):
                    base = f"{root}/" + "/".join(seg[:end])
                    cands += [base + ".rs", base + "/mod.rs"]
        for cand in cands:
            cand = cand.lstrip("./") if cand.startswith("./") else cand
            if cand in self.paths and cand != importer:
                return [(cand, "")]
        return []

    def resolve(self, importer: str, lang: str, ref: ImportRef) -> list[tuple[str, str]]:
        if lang == "python":
            return self.python(importer, ref)
        if lang in {"javascript", "typescript", "tsx", "jsx", "vue", "svelte"}:
            return self.js(importer, ref)
        return self.generic(importer, ref, lang)


# -------------------------------------------------------------------- store


class ProjectGraph:
    def __init__(self, root: Path, db_path: Path | None = None):
        self.root = Path(root).resolve()
        if db_path is None:
            env = os.environ.get("CONTEXTA_GRAPH_DIR", "").strip()
            base = Path(env).expanduser() if env else self.root / GRAPH_DIRNAME
            db_path = base / GRAPH_FILENAME
        self.db_path = Path(db_path)
        self._con: sqlite3.Connection | None = None

    # connection
    @property
    def con(self) -> sqlite3.Connection:
        if self._con is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            guard = self.db_path.parent / ".gitignore"
            if self.db_path.parent.name == GRAPH_DIRNAME and not guard.exists():
                guard.write_text("# Contexta's local project memory. Safe to delete.\n*\n", encoding="utf-8")
            con = sqlite3.connect(str(self.db_path), timeout=10)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            version = None
            try:
                row = con.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
                version = int(row[0]) if row else None
            except sqlite3.DatabaseError:
                version = None
            if version != SCHEMA_VERSION:
                for table in ("files", "symbols", "imports_raw", "calls_raw", "edges", "history", "meta"):
                    con.execute(f"DROP TABLE IF EXISTS {table}")
            con.executescript(SCHEMA)
            con.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
            con.commit()
            self._con = con
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def __enter__(self) -> "ProjectGraph":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def meta(self, key: str, default: str | None = None) -> str | None:
        row = self.con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def _set_meta(self, key: str, value: str) -> None:
        self.con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def is_empty(self) -> bool:
        return self.con.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0

    # ---------------------------------------------------------------- update
    def update(self, files: list[Path] | None = None, *, use_git: bool = True, force: bool = False) -> UpdateStats:
        """Bring the graph in line with the files on disk. Parses only what changed."""
        started = time.perf_counter()
        stats = UpdateStats()
        if files is None:
            files = self._scan()
        current: dict[str, Path] = {}
        for path in files:
            try:
                rel = path.resolve().relative_to(self.root).as_posix()
            except (ValueError, OSError):
                continue
            if is_sensitive_path(rel) or rel.startswith(GRAPH_DIRNAME + "/"):
                continue
            current[rel] = path
        stats.total = len(current)

        con = self.con
        known = {r["path"]: r for r in con.execute("SELECT path, hash, mtime_ns, size FROM files")}
        gone = [p for p in known if p not in current]
        dirty = False
        now = _now()

        con.execute("BEGIN")
        try:
            for rel in gone:
                self._delete_file(rel)
                stats.removed += 1
                dirty = True
            from contexta_app.scanner import get_language

            for rel, path in current.items():
                try:
                    st = path.stat()
                except OSError:
                    continue
                row = known.get(rel)
                if row and not force and row["mtime_ns"] == st.st_mtime_ns and row["size"] == st.st_size:
                    stats.unchanged += 1
                    continue
                try:
                    raw = path.read_bytes() if st.st_size <= MAX_PARSE_BYTES * 4 else b""
                except OSError:
                    continue
                digest = hashlib.sha1(raw).hexdigest() if raw else f"size:{st.st_size}"
                if row and not force and row["hash"] == digest:
                    con.execute("UPDATE files SET mtime_ns=?, size=? WHERE path=?", (st.st_mtime_ns, st.st_size, rel))
                    stats.unchanged += 1
                    continue
                lang = get_language(path)
                self._store_file(rel, lang, raw, digest, st, now)
                stats.changed += 1 if row else 0
                stats.added += 0 if row else 1
                dirty = True
            if dirty or force or self.meta("edges_built") != "1":
                stats.edges = self._rebuild_edges()
                dirty = True
            if use_git:
                stats.git_commits = self._update_history(current)
            if dirty or use_git:
                self._compute_ranks()
            self._set_meta("updated_at", str(now))
            con.commit()
        except Exception:
            con.rollback()
            raise
        stats.symbols = con.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        if not dirty:
            stats.edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        stats.seconds = time.perf_counter() - started
        return stats

    def _scan(self) -> list[Path]:
        from contexta_app.engine.insight import flatten_tree
        from contexta_app.scanner import build_tree, load_gitignore_patterns

        patterns = load_gitignore_patterns(self.root)
        tree = build_tree(self.root, False, False, lambda *_a, **_k: None, [0], patterns, self.root)
        return flatten_tree(tree)

    def _delete_file(self, rel: str) -> None:
        for table in ("files", "symbols", "imports_raw", "calls_raw"):
            self.con.execute(f"DELETE FROM {table} WHERE path=?", (rel,))
        self._set_meta("edges_built", "0")

    def _store_file(self, rel: str, lang: str | None, raw: bytes, digest: str, st: os.stat_result, now: float) -> None:
        con = self.con
        for table in ("symbols", "imports_raw", "calls_raw"):
            con.execute(f"DELETE FROM {table} WHERE path=?", (rel,))
        facts = FileFacts()
        lines = 0
        if raw and len(raw) <= MAX_PARSE_BYTES and lang in CODE_LANGS:
            text = raw.decode("utf-8", errors="replace")
            lines = text.count("\n") + 1
            facts = extract_facts(text, lang)
        elif raw:
            lines = raw.count(b"\n") + 1
        kind = classify_kind(rel, lang)
        con.execute(
            "INSERT OR REPLACE INTO files(path, hash, mtime_ns, size, lang, kind, lines, backend, indexed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (rel, digest, st.st_mtime_ns, st.st_size, lang, kind, lines, facts.backend, now),
        )
        con.executemany(
            "INSERT INTO symbols VALUES (?,?,?,?,?,?,?,?)",
            [(rel, s.name, s.qualname, s.kind, s.line, s.end_line, _safe_signature(s.signature), s.parent) for s in facts.symbols],
        )
        con.executemany(
            "INSERT INTO imports_raw VALUES (?,?,?,?,?)",
            [(rel, i.module, i.level, ",".join(i.names), i.line) for i in facts.imports],
        )
        con.executemany("INSERT INTO calls_raw VALUES (?,?,?)", [(rel, a, b) for a, b in set(facts.calls)])
        self._set_meta("edges_built", "0")

    # ------------------------------------------------------------------ edges
    def _rebuild_edges(self) -> int:
        con = self.con
        con.execute("DELETE FROM edges WHERE kind != 'cochange'")
        files = {r["path"]: r for r in con.execute("SELECT path, lang, kind FROM files")}
        langs = {p: (r["lang"] or "") for p, r in files.items()}
        kinds = {p: r["kind"] for p, r in files.items()}
        resolver = Resolver(langs)

        symbols_by_file: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
        defs_by_name: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for r in con.execute("SELECT path, name, qualname, kind FROM symbols"):
            symbols_by_file[r["path"]][r["name"]].append((r["qualname"], r["kind"]))
            if r["kind"] != "const":
                defs_by_name[r["name"]].append((r["path"], r["qualname"], r["kind"]))

        edges: dict[tuple, list] = {}

        def add(src_file, src_sym, dst_file, dst_sym, kind, weight, detail=""):
            if src_file == dst_file and kind == "imports":
                return
            key = (src_file, src_sym, dst_file, dst_sym, kind)
            prev = edges.get(key)
            if prev is None:
                edges[key] = [weight, detail]
            else:
                prev[0] = max(prev[0], weight)
                if detail and detail not in prev[1].split(","):
                    prev[1] = ",".join(filter(None, [prev[1], detail]))

        raw_imports: dict[str, list[ImportRef]] = defaultdict(list)
        for r in con.execute("SELECT path, module, level, names, line FROM imports_raw"):
            raw_imports[r["path"]].append(ImportRef(r["module"], r["level"], tuple(filter(None, r["names"].split(","))), r["line"]))

        imported: dict[str, set[str]] = defaultdict(set)  # file -> files it imports (direct)
        for path, refs in raw_imports.items():
            lang = langs.get(path, "")
            for ref in refs:
                for target, detail in resolver.resolve(path, lang, ref):
                    add(path, "", target, "", "imports", 1.0, detail)
                    imported[path].add(target)
                    # follow re-exports: `from pkg import Name` where pkg/__init__ imports Name from elsewhere
                    if detail:
                        for name in detail.split(","):
                            for origin in self._reexport_origin(target, name, raw_imports, resolver, langs, symbols_by_file):
                                add(path, "", origin, "", "imports", 0.9, name)
                                imported[path].add(origin)

        # calls
        for r in con.execute("SELECT path, caller, callee FROM calls_raw"):
            path, caller, callee = r["path"], r["caller"], r["callee"]
            src_sym = "" if caller == MODULE_SCOPE else caller
            local = symbols_by_file[path].get(callee)
            if local:
                if not src_sym or local[0][0] != src_sym:
                    add(path, src_sym, path, local[0][0], "calls", 1.0)
                continue
            hit = False
            for target in imported.get(path, ()):
                found = symbols_by_file[target].get(callee)
                if found:
                    add(path, src_sym, target, found[0][0], "calls", 1.0)
                    hit = True
            if hit:
                continue
            if len(callee) >= UNIQUE_NAME_MIN_LEN and callee.lower() not in _COMMON_NAMES:
                defs = defs_by_name.get(callee, [])
                if len(defs) == 1 and defs[0][0] != path:
                    add(path, src_sym, defs[0][0], defs[0][1], "calls", 0.5)

        # tests -> sources
        sources_by_stem: dict[str, list[str]] = defaultdict(list)
        for p, k in kinds.items():
            if k == "source":
                sources_by_stem[PurePosixPath(p).stem.lower()].append(p)
        for (src_file, src_sym, dst_file, dst_sym, kind), (weight, detail) in list(edges.items()):
            if kind in {"imports", "calls"} and kinds.get(src_file) == "test" and kinds.get(dst_file) == "source":
                add(src_file, "", dst_file, "", "tests", 1.0 if kind == "imports" else weight)
        for p, k in kinds.items():
            if k != "test":
                continue
            stem = _test_stem(p)
            if stem in _GENERIC_STEMS or len(stem) < 3:
                continue
            for src in sources_by_stem.get(stem, [])[:3]:
                add(p, "", src, "", "tests", 0.6, "name")

        con.executemany(
            "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?,?)",
            [(*key, vals[0], vals[1]) for key, vals in edges.items()],
        )
        self._set_meta("edges_built", "1")
        return len(edges)

    def _reexport_origin(self, target, name, raw_imports, resolver, langs, symbols_by_file, depth=3) -> list[str]:
        """Where ``name`` really lives when ``target`` only re-exports it (``__init__.py`` or an index file)."""
        if depth == 0 or name in symbols_by_file.get(target, {}):
            return []
        out: list[str] = []
        for ref in raw_imports.get(target, ()):
            if name in ref.names:
                for origin, _detail in resolver.resolve(target, langs.get(target, ""), ref):
                    if origin != target:
                        out.append(origin)
                        if name not in symbols_by_file.get(origin, {}):
                            out += self._reexport_origin(origin, name, raw_imports, resolver, langs, symbols_by_file, depth - 1)
        return out

    # ---------------------------------------------------------------- history
    def _update_history(self, current: dict[str, Path]) -> int:
        head = _git(self.root, "rev-parse", "HEAD")
        if head is None:
            return 0
        head = head.strip()
        if self.meta("git_head") == head and self.meta("history_files") == str(len(current)):
            return 0
        log = _git(
            self.root, "log", f"-n{GIT_LOG_COMMITS}", "--no-renames", "--name-only", "--pretty=format:%x00%h%x00%ct", timeout=60
        )
        if log is None:
            return 0
        con = self.con
        con.execute("DELETE FROM history")
        con.execute("DELETE FROM edges WHERE kind='cochange'")
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        commits = 0
        rows: list[tuple[str, int, str]] = []
        for cid, ts, files in self._split_log(log):
            commits += 1
            kept = [f for f in files if f in current]
            for f in kept:
                rows.append((f, ts, cid))
            if 2 <= len(kept) <= COCHANGE_MAX_FILES_PER_COMMIT:
                kept.sort()
                for i, a in enumerate(kept):
                    for b in kept[i + 1:]:
                        pair_counts[(a, b)] += 1
        con.executemany("INSERT INTO history VALUES (?,?,?)", rows)
        per_file: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
        for (a, b), count in pair_counts.items():
            if count >= COCHANGE_MIN_COUNT:
                per_file[a].append((count, a, b))
                per_file[b].append((count, a, b))
        keep: set[tuple[str, str]] = set()
        for entries in per_file.values():
            for count, a, b in sorted(entries, reverse=True)[:COCHANGE_KEEP_PER_FILE]:
                keep.add((a, b))
        con.executemany(
            "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?,?)",
            [(a, "", b, "", "cochange", float(pair_counts[(a, b)]), "") for a, b in keep],
        )
        self._set_meta("git_head", head)
        self._set_meta("history_files", str(len(current)))
        return commits

    @staticmethod
    def _split_log(log: str):
        # format: \0<hash>\0<ts>\n<file>\n<file>\n\n\0<hash>...
        chunks = log.split("\x00")
        i = 1
        while i + 1 < len(chunks):
            cid = chunks[i]
            tail = chunks[i + 1]
            lines = tail.split("\n")
            try:
                ts = int(lines[0].strip())
            except ValueError:
                i += 2
                continue
            files = [x.strip() for x in lines[1:] if x.strip()]
            yield cid, ts, files
            i += 2

    # ------------------------------------------------------------------ ranks
    def _compute_ranks(self, damping: float = 0.85, iterations: int = 30) -> None:
        con = self.con
        paths = [r[0] for r in con.execute("SELECT path FROM files")]
        if not paths:
            return
        index = {p: i for i, p in enumerate(paths)}
        out_edges: list[list[tuple[int, float]]] = [[] for _ in paths]
        for r in con.execute("SELECT src_file, dst_file, kind, weight FROM edges WHERE kind IN ('imports','calls')"):
            a, b = index.get(r["src_file"]), index.get(r["dst_file"])
            if a is None or b is None or a == b:
                continue
            out_edges[a].append((b, r["weight"]))
        n = len(paths)
        rank = [1.0 / n] * n
        for _ in range(iterations):
            nxt = [(1 - damping) / n] * n
            dangling = 0.0
            for i, targets in enumerate(out_edges):
                if not targets:
                    dangling += rank[i]
                    continue
                total = sum(w for _, w in targets)
                for j, w in targets:
                    nxt[j] += damping * rank[i] * w / total
            share = damping * dangling / n
            rank = [v + share for v in nxt]
        top = max(rank) or 1.0
        con.executemany("UPDATE files SET rank=? WHERE path=?", [(round(rank[i] / top, 6), p) for p, i in index.items()])

    # ---------------------------------------------------------------- queries
    def stats(self) -> dict:
        con = self.con
        one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "files": one("SELECT COUNT(*) FROM files"),
            "symbols": one("SELECT COUNT(*) FROM symbols"),
            "edges": {r[0]: r[1] for r in con.execute("SELECT kind, COUNT(*) FROM edges GROUP BY kind")},
            "tests": one("SELECT COUNT(*) FROM files WHERE kind='test'"),
            "commits": one("SELECT COUNT(DISTINCT commit_id) FROM history"),
            "updated_at": _iso(float(self.meta("updated_at", "0") or 0)),
            "db": str(self.db_path.relative_to(self.root)) if self.db_path.is_relative_to(self.root) else "(outside project)",
            "parsers": {r[0] or "none": r[1] for r in con.execute("SELECT backend, COUNT(*) FROM files GROUP BY backend")},
        }

    def has_file(self, path: str) -> bool:
        return self.con.execute("SELECT 1 FROM files WHERE path=?", (path,)).fetchone() is not None

    def normalize(self, target: str) -> tuple[str, str]:
        """``(file, symbol)`` for ``path``, ``path::Symbol`` or a bare symbol name."""
        target = target.strip().replace("\\", "/")
        if "::" in target:
            path, sym = target.split("::", 1)
            return path.lstrip("./"), sym
        cleaned = target[2:] if target.startswith("./") else target
        if self.has_file(cleaned):
            return cleaned, ""
        row = self.con.execute("SELECT path FROM files WHERE path LIKE ? ORDER BY length(path) LIMIT 1", (f"%/{cleaned}",)).fetchone()
        if row:
            return row[0], ""
        rows = self.con.execute("SELECT path, qualname FROM symbols WHERE name=? OR qualname=? LIMIT 2", (cleaned, cleaned)).fetchall()
        if len(rows) == 1:
            return rows[0][0], rows[0][1]
        return cleaned, ""

    def dependencies(self, target: str, depth: int = 1, kinds: tuple[str, ...] = ("imports", "calls")) -> list[dict]:
        return self._walk(target, depth, kinds, forward=True)

    def dependents(self, target: str, depth: int = 1, kinds: tuple[str, ...] = ("imports", "calls")) -> list[dict]:
        return self._walk(target, depth, kinds, forward=False)

    def _walk(self, target: str, depth: int, kinds: tuple[str, ...], forward: bool) -> list[dict]:
        path, sym = self.normalize(target)
        ph = ",".join("?" * len(kinds))
        results: dict[str, dict] = {}
        if sym and not forward:
            for r in self.con.execute(
                f"SELECT src_file, src_sym, kind, detail FROM edges WHERE dst_file=? AND dst_sym=? AND kind IN ({ph})", (path, sym, *kinds)
            ):
                key = r["src_file"] + (f"::{r['src_sym']}" if r["src_sym"] else "")
                results.setdefault(key, {"path": r["src_file"], "symbol": r["src_sym"], "distance": 1, "via": r["kind"]})
            for r in self.con.execute(
                "SELECT src_file, detail FROM edges WHERE dst_file=? AND kind='imports' AND (',' || detail || ',') LIKE ?", (path, f"%,{sym.split('.')[-1]},%")
            ):
                results.setdefault(r["src_file"], {"path": r["src_file"], "symbol": "", "distance": 1, "via": "imports"})
            frontier_files = {v["path"] for v in results.values()}
        elif sym and forward:
            for r in self.con.execute(
                f"SELECT dst_file, dst_sym, kind FROM edges WHERE src_file=? AND src_sym=? AND kind IN ({ph})", (path, sym, *kinds)
            ):
                key = r["dst_file"] + (f"::{r['dst_sym']}" if r["dst_sym"] else "")
                results.setdefault(key, {"path": r["dst_file"], "symbol": r["dst_sym"], "distance": 1, "via": r["kind"]})
            frontier_files = {v["path"] for v in results.values()}
        else:
            frontier_files = {path}
            results = {}
            depth_left = depth
            seen = {path}
            frontier = deque([(path, 0)])
            col_from, col_to = ("src_file", "dst_file") if forward else ("dst_file", "src_file")
            while frontier:
                current, dist = frontier.popleft()
                if dist >= depth_left:
                    continue
                for r in self.con.execute(
                    f"SELECT DISTINCT {col_to} AS other, kind FROM edges WHERE {col_from}=? AND kind IN ({ph})", (current, *kinds)
                ):
                    other = r["other"]
                    if other in seen:
                        continue
                    seen.add(other)
                    results[other] = {"path": other, "symbol": "", "distance": dist + 1, "via": r["kind"]}
                    frontier.append((other, dist + 1))
            return self._decorate(sorted(results.values(), key=lambda v: (v["distance"], v["path"])))
        return self._decorate(sorted(results.values(), key=lambda v: (v["distance"], v["path"], v["symbol"])))

    def _decorate(self, rows: list[dict]) -> list[dict]:
        for row in rows:
            info = self.con.execute("SELECT kind, rank FROM files WHERE path=?", (row["path"],)).fetchone()
            if info:
                row["kind"] = info["kind"]
        return rows

    def tests_for(self, paths: list[str], limit: int = 50) -> list[dict]:
        """Tests that exercise any of ``paths``, with the reason."""
        if not paths:
            return []
        ph = ",".join("?" * len(paths))
        out: dict[str, dict] = {}
        for r in self.con.execute(
            f"SELECT src_file, dst_file, weight, detail FROM edges WHERE kind='tests' AND dst_file IN ({ph})", paths
        ):
            reason = "same name" if r["detail"] == "name" else "imports or calls it"
            prev = out.get(r["src_file"])
            if prev is None or r["weight"] > prev["weight"]:
                out[r["src_file"]] = {"path": r["src_file"], "covers": r["dst_file"], "reason": reason, "weight": r["weight"]}
        rows = sorted(out.values(), key=lambda v: (-v["weight"], v["path"]))
        return rows[:limit]

    def impact(self, targets: list[str], depth: int = 3, limit: int = 40) -> dict:
        """What a change to ``targets`` can reach: dependents by distance, ranked tests, and files that usually change with it.

        The walk goes through imports and resolved calls. Guesses (a call matched
        only by a unique name) count at the first hop only. It does not continue
        through ``__init__``/``index`` re-export files, because every importer
        of the package would otherwise count as affected.
        """
        files: list[str] = []
        for target in targets:
            path, _sym = self.normalize(target)
            if path and self.has_file(path) and path not in files:
                files.append(path)
        kinds = {r["path"]: r["kind"] for r in self.con.execute("SELECT path, kind FROM files")}
        distance: dict[str, int] = {f: 0 for f in files}
        via: dict[str, str] = {}
        frontier = deque(files)
        while frontier:
            current = frontier.popleft()
            dist = distance[current]
            if dist >= depth:
                continue
            if dist > 0 and PurePosixPath(current).name in _HUB_NAMES:
                continue
            floor = 0.5 if dist == 0 else 0.9
            for r in self.con.execute(
                "SELECT DISTINCT src_file, kind FROM edges WHERE dst_file=? AND kind IN ('imports','calls') AND weight>=?", (current, floor)
            ):
                other = r["src_file"]
                if other in distance:
                    continue
                distance[other] = dist + 1
                via[other] = r["kind"]
                frontier.append(other)
        impacted = [
            {"path": p, "distance": d, "via": via[p], "kind": kinds.get(p, "other")}
            for p, d in distance.items() if d > 0 and kinds.get(p) != "test"
        ]
        impacted.sort(key=lambda v: (v["distance"], v["path"]))

        tests: dict[str, dict] = {}

        def offer(path: str, covers: str, reason: str, weight: float) -> None:
            prev = tests.get(path)
            if prev is None or weight > prev["weight"]:
                tests[path] = {"path": path, "covers": covers, "reason": reason, "weight": round(weight, 3)}

        for path, d in distance.items():
            if kinds.get(path) == "test":
                offer(path, "", f"depends on a changed file (distance {d})", 0.7 / d if d else 1.0)
        for r in self.con.execute(
            "SELECT src_file, dst_file, weight, detail FROM edges WHERE kind='tests' AND dst_file IN (%s)" % ",".join("?" * len(distance)),
            list(distance),
        ) if distance else []:
            d = distance.get(r["dst_file"], 0)
            reason = "same name as" if r["detail"] == "name" else "imports or calls"
            base = r["weight"] * (1.0 if d == 0 else 0.5 / d)
            offer(r["src_file"], r["dst_file"], f"{reason} {r['dst_file']}" + ("" if d == 0 else f" (distance {d})"), base)
        ranked_tests = sorted(tests.values(), key=lambda v: (-v["weight"], v["path"]))[:limit]
        cochange = self.cochanged(files, limit=10) if files else []
        return {
            "changed": files,
            "impacted": impacted[:limit],
            "impacted_total": len(impacted),
            "tests": ranked_tests,
            "tests_total": len(tests),
            "cochanged": [c for c in cochange if c["path"] not in files],
        }

    def cochanged(self, paths: list[str], limit: int = 15) -> list[dict]:
        out: dict[str, float] = defaultdict(float)
        for path in paths:
            for r in self.con.execute(
                "SELECT src_file, dst_file, weight FROM edges WHERE kind='cochange' AND (src_file=? OR dst_file=?)", (path, path)
            ):
                other = r["dst_file"] if r["src_file"] == path else r["src_file"]
                out[other] += r["weight"]
        rows = sorted(out.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return [{"path": p, "times_together": int(w)} for p, w in rows]

    def changed_since(self, ref: str | None = None) -> dict:
        """Files changed since a commit, tag, branch or ISO date, plus uncommitted work."""
        changed: set[str] = set()
        mode = "uncommitted"
        if ref:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ][\d:]+)?Z?", ref.strip()):
                mode = f"since {ref}"
                out = _git(self.root, "log", f"--since={ref}", "--name-only", "--no-renames", "--pretty=format:")
            else:
                mode = f"since {ref}"
                out = _git(self.root, "diff", "--name-only", "--diff-filter=ACMRD", f"{ref}..HEAD")
            if out is None:
                raise ValueError(f"Could not read git history for {ref!r}. Is it a commit, tag, branch, or YYYY-MM-DD date?")
            changed |= {line.strip() for line in out.splitlines() if line.strip()}
        for args in (("diff", "--name-only"), ("diff", "--cached", "--name-only"), ("ls-files", "--others", "--exclude-standard")):
            out = _git(self.root, *args)
            if out:
                changed |= {line.strip() for line in out.splitlines() if line.strip()}
        rows = []
        for path in sorted(changed):
            info = self.con.execute("SELECT kind, rank FROM files WHERE path=?", (path,)).fetchone()
            if not info:
                continue
            n = self.con.execute("SELECT COUNT(DISTINCT src_file) FROM edges WHERE dst_file=? AND kind IN ('imports','calls')", (path,)).fetchone()[0]
            rows.append({"path": path, "kind": info["kind"], "dependents": n})
        return {"since": mode, "files": rows}

    def hot_files(self, limit: int = 20, since_days: int | None = None, kind: str | None = "source") -> list[dict]:
        cutoff = _now() - since_days * 86400 if since_days else 0
        sql = "SELECT h.path AS path, COUNT(DISTINCT h.commit_id) AS commits, MAX(h.ts) AS last_ts, f.kind AS kind FROM history h JOIN files f ON f.path=h.path WHERE h.ts>=?"
        params: list = [cutoff]
        if kind:
            sql += " AND f.kind=?"
            params.append(kind)
        sql += " GROUP BY h.path ORDER BY commits DESC, last_ts DESC, h.path LIMIT ?"
        params.append(limit)
        return [
            {"path": r["path"], "commits": r["commits"], "last_changed": _iso(r["last_ts"]), "kind": r["kind"]}
            for r in self.con.execute(sql, params)
        ]

    def search_symbols(self, query: str, limit: int = 20, kind: str | None = None) -> list[dict]:
        q = query.strip()
        if not q:
            return []
        like = f"%{q}%"
        sql = (
            "SELECT s.path, s.name, s.qualname, s.kind, s.line, s.signature, f.rank, f.kind AS fkind FROM symbols s "
            "JOIN files f ON f.path=s.path WHERE (s.name LIKE ? OR s.qualname LIKE ?)"
        )
        params: list = [like, like]
        if kind:
            sql += " AND s.kind=?"
            params.append(kind)
        rows = self.con.execute(sql, params).fetchall()
        ql = q.lower()

        def score(r) -> float:
            name = r["name"].lower()
            base = 3.0 if name == ql else 2.0 if name.startswith(ql) else 1.0
            if r["fkind"] == "test":
                base -= 0.6
            if r["kind"] in {"class", "function"}:
                base += 0.2
            return base + 0.5 * (r["rank"] or 0)

        rows.sort(key=lambda r: (-score(r), r["path"], r["line"]))
        return [
            {"path": r["path"], "symbol": r["qualname"], "kind": r["kind"], "line": r["line"], "signature": r["signature"]}
            for r in rows[:limit]
        ]

    def symbol_importance(self) -> dict[tuple[str, str], int]:
        """Number of other files that use each symbol (calls plus named imports)."""
        users: dict[tuple[str, str], set[str]] = defaultdict(set)
        for r in self.con.execute("SELECT src_file, dst_file, dst_sym FROM edges WHERE kind='calls' AND dst_sym != '' AND src_file != dst_file"):
            users[(r["dst_file"], r["dst_sym"])].add(r["src_file"])
        names: dict[str, list[str]] = defaultdict(list)
        for r in self.con.execute("SELECT path, name, qualname FROM symbols WHERE parent=''"):
            names[r["path"]].append((r["name"], r["qualname"]))
        for r in self.con.execute("SELECT src_file, dst_file, detail FROM edges WHERE kind='imports' AND detail != ''"):
            for name in r["detail"].split(","):
                users[(r["dst_file"], name)].add(r["src_file"])
        return {key: len(val) for key, val in users.items()}

    def rank_files(self, focus: str | None = None, limit: int | None = None, kinds: tuple[str, ...] = ("source",)) -> list[dict]:
        """Files by importance. With ``focus``, files and symbols whose names match the words get a boost."""
        ph = ",".join("?" * len(kinds))
        rows = [dict(r) for r in self.con.execute(f"SELECT path, kind, lang, rank, lines FROM files WHERE kind IN ({ph})", kinds)]
        words = [w for w in re.findall(r"[A-Za-z0-9]+", (focus or "").lower()) if len(w) > 2]
        if words:
            by_path = {r["path"]: r for r in rows}
            for r in rows:
                r["focus"] = 0.0
            for word in words:
                stem = word[:-3] if word.endswith("ing") and len(word) > 5 else word.rstrip("s") if len(word) > 4 else word
                for r in rows:
                    if stem in r["path"].lower():
                        r["focus"] += 1.0
                for s in self.con.execute("SELECT path, name FROM symbols WHERE lower(name) LIKE ?", (f"%{stem}%",)):
                    if s["path"] in by_path:
                        by_path[s["path"]]["focus"] += 0.5
            for r in rows:
                r["score"] = r["rank"] + (r["focus"] / max(len(words), 1)) * 1.5
        else:
            for r in rows:
                r["score"] = r["rank"]
        for r in rows:
            if any(part in _LOW_VALUE_DIRS for part in r["path"].split("/")[:-1]):
                r["score"] *= 0.35
        rows.sort(key=lambda r: (-r["score"], r["path"]))
        return rows[:limit] if limit else rows

    # ------------------------------------------------------------ repo map
    def repo_map(self, budget_tokens: int = 1500, focus: str | None = None, max_files: int = 80) -> dict:
        """A compact map of the repo: the most important files, each with its most used symbols, inside a token budget."""
        from contexta_app.renderer import estimate_tokens

        ranked = self.rank_files(focus=focus, limit=max_files)
        if not ranked:
            return {"text": "", "tokens": 0, "files": 0, "symbols": 0, "budget": budget_tokens, "omitted_files": 0}
        importance = self.symbol_importance()
        top_score = ranked[0]["score"] or 1.0
        candidates: list[tuple[float, str, dict]] = []
        file_syms: dict[str, list[dict]] = {}
        for r in ranked:
            syms, seen_q = [], set()
            for row in self.con.execute(
                "SELECT name, qualname, kind, line, signature, parent FROM symbols WHERE path=? ORDER BY line", (r["path"],)
            ):
                if row["qualname"] in seen_q:  # typing overloads repeat a name
                    continue
                seen_q.add(row["qualname"])
                syms.append(dict(row))
            file_syms[r["path"]] = syms
            file_priority = r["score"] / top_score
            for s in syms:
                use = importance.get((r["path"], s["qualname"]), 0) + importance.get((r["path"], s["name"]), 0) * (0 if s["parent"] else 1)
                depth_penalty = 0.0 if not s["parent"] else 0.25
                kind_boost = {"class": 0.35, "function": 0.25, "interface": 0.3, "type": 0.2, "enum": 0.2, "trait": 0.3}.get(s["kind"], 0.0)
                if s["name"].startswith("_") and not s["name"].startswith("__"):
                    depth_penalty += 0.3
                s["_priority"] = file_priority * 0.5 + min(use, 12) / 12 * 0.5 + kind_boost - depth_penalty
                if s["kind"] == "const":
                    s["_priority"] -= 0.2
                candidates.append((s["_priority"], r["path"], s))
        candidates.sort(key=lambda c: (-c[0], c[1], c[2]["line"]))

        chosen: dict[str, list[dict]] = defaultdict(list)
        used_tokens = estimate_tokens(f"# Repo map ({'focus: ' + focus if focus else 'by importance'})\n")
        header_cost: dict[str, int] = {}
        symbol_count = 0
        for priority, path, sym in candidates:
            line = f"  {'  ' if sym['parent'] else ''}{sym['signature'] or sym['name']}  :{sym['line']}\n"
            cost = estimate_tokens(line)
            if path not in chosen:
                header_cost[path] = estimate_tokens(f"{path}\n")
                cost += header_cost[path]
            if used_tokens + cost > budget_tokens:
                if used_tokens + 8 > budget_tokens:
                    break
                continue
            # methods only follow when their class is shown
            if sym["parent"] and not any(c["qualname"] == sym["parent"] for c in chosen.get(path, [])):
                continue
            chosen[path].append(sym)
            used_tokens += cost
            symbol_count += 1
        # files with no symbols still show up when they rank high and fit
        for r in ranked[:12]:
            if r["path"] not in chosen and not file_syms.get(r["path"]):
                cost = estimate_tokens(f"{r['path']}\n")
                if used_tokens + cost <= budget_tokens:
                    chosen[r["path"]] = []
                    used_tokens += cost
        order = [r["path"] for r in ranked if r["path"] in chosen]
        lines = [f"# Repo map ({'focus: ' + focus if focus else 'by importance'})"]
        for path in order:
            lines.append(path)
            for sym in sorted(chosen[path], key=lambda s: s["line"]):
                lines.append(f"  {'  ' if sym['parent'] else ''}{sym['signature'] or sym['name']}  :{sym['line']}")
        text = "\n".join(lines) + "\n"
        return {
            "text": text, "tokens": estimate_tokens(text), "files": len(order), "symbols": symbol_count,
            "budget": budget_tokens, "omitted_files": max(len(ranked) - len(order), 0),
        }

    # ---------------------------------------------------------------- export
    def export(self, fmt: str = "json") -> str:
        if fmt == "md" or fmt == "markdown":
            return self._export_markdown()
        if fmt in {"json", "jsonl"}:
            return self._export_json(jsonl=(fmt == "jsonl"))
        raise ValueError("Unknown graph format. Choose json, jsonl or md.")

    def _export_json(self, jsonl: bool = False) -> str:
        con = self.con
        nodes: list[dict] = []
        for r in con.execute("SELECT path, lang, kind, lines, rank FROM files ORDER BY path"):
            nodes.append({"id": r["path"], "type": r["kind"], "name": PurePosixPath(r["path"]).name, "lang": r["lang"], "lines": r["lines"], "rank": r["rank"]})
        for r in con.execute("SELECT path, qualname, kind, line, signature FROM symbols ORDER BY path, line"):
            nodes.append({"id": f"{r['path']}::{r['qualname']}", "type": "symbol", "symbol_kind": r["kind"], "name": r["qualname"], "file": r["path"], "line": r["line"], "signature": r["signature"]})
        edges = []
        for r in con.execute("SELECT * FROM edges ORDER BY kind, src_file, src_sym, dst_file, dst_sym"):
            edges.append({
                "source": r["src_file"] + (f"::{r['src_sym']}" if r["src_sym"] else ""),
                "target": r["dst_file"] + (f"::{r['dst_sym']}" if r["dst_sym"] else ""),
                "kind": r["kind"], "weight": r["weight"],
            })
        meta = {
            "format": "contexta.graph.v1", "project": self.root.name, "generated": _iso(_now()),
            "stats": {"nodes": len(nodes), "edges": len(edges)},
            "note": "Names, signatures and relations only. No file content, no authors.",
        }
        if jsonl:
            lines = [json.dumps({"record": "meta", **meta})]
            lines += [json.dumps({"record": "node", **n}) for n in nodes]
            lines += [json.dumps({"record": "edge", **e}) for e in edges]
            return "\n".join(lines) + "\n"
        return json.dumps({**meta, "nodes": nodes, "edges": edges}, indent=1, ensure_ascii=False) + "\n"

    def _export_markdown(self, max_files: int = 400) -> str:
        con = self.con
        out = [f"# {self.root.name}: project graph", "", f"_Generated {_iso(_now())} by Contexta. Names and relations only._", ""]
        s = self.stats()
        out.append(f"{s['files']} files, {s['symbols']} symbols, edges: " + ", ".join(f"{k} {v}" for k, v in sorted(s["edges"].items())))
        out.append("")
        hot = self.hot_files(10)
        if hot:
            out += ["## Hot files", ""] + [f"- `{h['path']}`: {h['commits']} commits, last {h['last_changed']}" for h in hot] + [""]
        out += ["## Files", ""]
        rows = con.execute("SELECT path, kind, rank FROM files WHERE kind IN ('source','test') ORDER BY rank DESC, path LIMIT ?", (max_files,)).fetchall()
        for r in rows:
            out.append(f"### `{r['path']}`" + (" (test)" if r["kind"] == "test" else ""))
            syms = con.execute("SELECT signature, line FROM symbols WHERE path=? AND parent='' ORDER BY line LIMIT 12", (r["path"],)).fetchall()
            if syms:
                out.append("- symbols: " + "; ".join(f"`{x['signature']}`" for x in syms[:8]))
            deps = [x[0] for x in con.execute("SELECT DISTINCT dst_file FROM edges WHERE src_file=? AND kind='imports' ORDER BY dst_file LIMIT 12", (r["path"],))]
            if deps:
                out.append("- imports: " + ", ".join(f"`{d}`" for d in deps))
            users = [x[0] for x in con.execute("SELECT DISTINCT src_file FROM edges WHERE dst_file=? AND kind IN ('imports','calls') ORDER BY src_file LIMIT 12", (r["path"],))]
            if users:
                out.append("- used by: " + ", ".join(f"`{d}`" for d in users))
            tests = [t["path"] for t in self.tests_for([r["path"]], 5)] if r["kind"] == "source" else []
            if tests:
                out.append("- tests: " + ", ".join(f"`{t}`" for t in tests))
            out.append("")
        return "\n".join(out)


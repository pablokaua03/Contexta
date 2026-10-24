"""
cache.py - Smart project cache with file-change detection.

Keeps ProjectAnalysis in memory and invalidates when source files change.
No background threads — checks mtimes on access, so it's safe for MCP's
async model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from contexta_app.context_engine import ExportConfig, ProjectAnalysis, build_analysis
from contexta_app.scanner import (
    build_tree,
    count_files,
    get_git_changed_files,
    load_gitignore_patterns,
)


@dataclass
class _CacheEntry:
    analysis: ProjectAnalysis
    tree: dict
    file_count: int
    mtimes: dict[str, float]
    created_at: float
    hit_count: int = 0


_NOOP_LOG = lambda msg, tag="": None
_MAX_CACHE_AGE = 300.0
_MAX_ENTRIES = 10

_cache: dict[str, _CacheEntry] = {}
_stats = {"hits": 0, "misses": 0, "invalidations": 0}


def _snapshot_mtimes(path: Path, file_paths: list[Path]) -> dict[str, float]:
    result = {}
    for fp in file_paths:
        try:
            result[str(fp)] = fp.stat().st_mtime
        except OSError:
            result[str(fp)] = 0.0

    for marker in ("package.json", "pyproject.toml", "Cargo.toml", "go.mod",
                    "requirements.txt", "composer.json", "Gemfile", ".gitignore",
                    ".contextaignore", "contexta.toml", ".contexta.toml"):
        candidate = path / marker
        if candidate.exists():
            try:
                result[str(candidate)] = candidate.stat().st_mtime
            except OSError:
                pass
    return result


def _has_changes(entry: _CacheEntry) -> bool:
    if time.time() - entry.created_at > _MAX_CACHE_AGE:
        return True

    for fpath, old_mtime in entry.mtimes.items():
        try:
            current = Path(fpath).stat().st_mtime
            if current != old_mtime:
                return True
        except OSError:
            return True
    return False


def _evict_oldest():
    if len(_cache) < _MAX_ENTRIES:
        return
    oldest_key = min(_cache, key=lambda k: _cache[k].created_at)
    del _cache[oldest_key]


def get_analysis(
    project_path: Path,
    config: ExportConfig | None = None,
    force_refresh: bool = False,
    log_cb=None,
) -> tuple[ProjectAnalysis, dict, int, bool]:
    """Return (analysis, tree, file_count, was_cached).

    Uses cached analysis if files haven't changed, otherwise recomputes.
    """
    if log_cb is None:
        log_cb = _NOOP_LOG
    if config is None:
        config = ExportConfig()

    key = str(project_path.resolve())
    entry = _cache.get(key)

    if entry is not None and not force_refresh and not _has_changes(entry):
        entry.hit_count += 1
        _stats["hits"] += 1
        return entry.analysis, entry.tree, entry.file_count, True

    if entry is not None:
        _stats["invalidations"] += 1

    _stats["misses"] += 1
    _evict_oldest()

    gitignore = load_gitignore_patterns(project_path)
    counter = [0]
    tree = build_tree(
        root=project_path,
        include_hidden=False,
        include_unknown=False,
        log_cb=log_cb,
        counter=counter,
        gitignore_patterns=gitignore,
        project_root=project_path,
    )
    file_count = count_files(tree)
    changed = get_git_changed_files(project_path) or []
    analysis = build_analysis(
        project_path=project_path,
        full_tree=tree,
        changed_files=changed,
        config=config,
        log_cb=log_cb,
    )

    all_paths = [f.path for f in analysis.all_files]
    mtimes = _snapshot_mtimes(project_path, all_paths)

    _cache[key] = _CacheEntry(
        analysis=analysis,
        tree=tree,
        file_count=file_count,
        mtimes=mtimes,
        created_at=time.time(),
    )

    return analysis, tree, file_count, False


def get_cache_stats() -> dict:
    return {
        "entries": len(_cache),
        "projects": list(_cache.keys()),
        **_stats,
    }


def invalidate(project_path: Path | None = None) -> int:
    if project_path is None:
        count = len(_cache)
        _cache.clear()
        return count
    key = str(project_path.resolve())
    if key in _cache:
        del _cache[key]
        return 1
    return 0

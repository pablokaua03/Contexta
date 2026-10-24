"""contexta_app.engine.relations: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from contexta_app.engine.constants import (
    normalized_name_similarity,
)
from contexta_app.engine.models import (
    FileInsight,
)

def build_module_map(insights: list[FileInsight]) -> dict[str, str]:
    module_map: dict[str, str] = {}
    for item in insights:
        parts = list(item.relpath.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        dotted = ".".join(parts)
        module_map[dotted] = item.relpath.as_posix()
        path_like = "/".join(parts)
        module_map[path_like.lower()] = item.relpath.as_posix()
        if len(parts) == 1:
            module_map.setdefault(parts[0], item.relpath.as_posix())
        stem = item.path.stem.lower()
        module_map.setdefault(stem, item.relpath.as_posix())
        module_map.setdefault(item.path.name.lower(), item.relpath.as_posix())
    return module_map

def resolve_local_relationships(
    insights: list[FileInsight],
    module_map: dict[str, str],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    rel_index: dict[str, set[str]] = defaultdict(set)
    reverse_index: dict[str, set[str]] = defaultdict(set)

    for item in insights:
        for imported in item.imports:
            target = resolve_local_import(item, imported, module_map)
            if not target or target == item.relpath.as_posix():
                continue
            rel_index[item.relpath.as_posix()].add(target)
            reverse_index[target].add(item.relpath.as_posix())

        related_tests = resolve_related_tests(item, insights)
        for test_rel in related_tests:
            reverse_index[item.relpath.as_posix()].add(test_rel)

    return rel_index, reverse_index

def resolve_local_import(item: FileInsight, imported: str, module_map: dict[str, str]) -> str | None:
    if item.lang == "python":
        if imported.startswith("."):
            base_parts = list(item.relpath.parent.parts)
            dots = len(imported) - len(imported.lstrip("."))
            tail = imported.lstrip(".")
            if dots <= len(base_parts):
                base_parts = base_parts[: len(base_parts) - dots + 1]
            else:
                base_parts = []
            if tail:
                base_parts.extend(tail.split("."))
            dotted = ".".join(part for part in base_parts if part)
            return module_map.get(dotted)
        return module_map.get(imported) or module_map.get(imported.split(".")[-1])
    if item.lang in {"javascript", "jsx", "typescript", "tsx"}:
        normalized = imported.strip().replace("\\", "/").lower()
        if not normalized:
            return None
        normalized = normalized.removeprefix("@/")
        normalized = normalized.removeprefix("./")
        if normalized.startswith("../"):
            base_parts = list(item.relpath.parent.parts)
            while normalized.startswith("../"):
                normalized = normalized[3:]
                if base_parts:
                    base_parts.pop()
            joined = "/".join(part.lower() for part in base_parts if part)
            normalized = f"{joined}/{normalized}" if joined else normalized
        candidates = [normalized.rstrip("/")]
        stem_candidate = candidates[0].rsplit("/", 1)[-1]
        candidates.extend(
            [
                f"{candidates[0]}/page",
                f"{candidates[0]}/index",
                stem_candidate,
                f"{stem_candidate}.tsx",
                f"{stem_candidate}.ts",
                f"{stem_candidate}.jsx",
                f"{stem_candidate}.js",
            ]
        )
        for candidate in candidates:
            target = module_map.get(candidate)
            if target:
                return target
        for key, target in module_map.items():
            if key.endswith(candidates[0]) or key.endswith(stem_candidate):
                return target
        return None
    if item.lang == "php":
        normalized = imported.strip().replace("\\", "/").lower()
        if not normalized:
            return None
        normalized = normalized.removeprefix("./")
        base_parts = list(item.relpath.parent.parts)
        while normalized.startswith("../"):
            normalized = normalized[3:]
            if base_parts:
                base_parts.pop()
        joined = "/".join(part.lower() for part in base_parts if part)
        if joined and "/" not in normalized and not normalized.endswith(".php"):
            candidates = [normalized, f"{normalized}.php"]
        else:
            combined = f"{joined}/{normalized}" if joined and "/" not in normalized else normalized
            candidates = [combined]
            if not combined.endswith(".php"):
                candidates.append(f"{combined}.php")
        candidates.extend([Path(candidate).stem.lower() for candidate in candidates])
        for candidate in candidates:
            target = module_map.get(candidate)
            if target:
                return target
        for key, target in module_map.items():
            if any(key.endswith(candidate) for candidate in candidates):
                return target
        return None
    return None

def _module_name(item: FileInsight) -> str:
    return ".".join(item.relpath.with_suffix("").parts).lower()

def _symbol_names(item: FileInsight) -> list[str]:
    return [name.lower() for name in item.functions[:6] + item.classes[:4] if len(name) >= 4]

def _dotted_suffixes(name: str) -> list[str]:
    """``a.b.c`` -> ``b.c``, ``c``: what ``name.endswith(f".{x}")`` can match."""
    return [name[i + 1:] for i, ch in enumerate(name) if ch == "."]

class RelatedTestIndex:
    """Finds the tests ``related_test_score`` can rate 4 or more, without scoring every pair.

    A pair reaches 4 only through a file-name match (4), an import match (2) or
    a symbol mention (1-2): name-only parts (parent folder 1, fuzzy name 2) top
    out at 3. The index returns every test that has a name, import or mention
    link to the file, and ``related_test_score`` then decides exactly as before.
    """

    def __init__(self, candidates: list[FileInsight]):
        self.candidates = [c for c in candidates if "test" in c.relpath.as_posix().lower()]
        self._by_target_stem: dict[str, list[FileInsight]] = defaultdict(list)
        self._by_import: dict[str, list[FileInsight]] = defaultdict(list)
        self._by_import_suffix: dict[str, list[FileInsight]] = defaultdict(list)
        self._by_word: dict[str, list[FileInsight]] = defaultdict(list)
        for test in self.candidates:
            for target in _test_target_stems(test.path.stem.lower()):
                self._by_target_stem[target].append(test)
            for imported in {value.lower() for value in test.imports}:
                self._by_import[imported].append(test)
                for suffix in _dotted_suffixes(imported):
                    self._by_import_suffix[suffix].append(test)
            for word in test.content_words:
                self._by_word[word].append(test)

    def tests_for(self, item: FileInsight) -> list[FileInsight]:
        found: dict[int, FileInsight] = {}
        stem = item.path.stem.lower()
        module = _module_name(item)
        for test in self._by_target_stem.get(stem, ()):
            found[id(test)] = test
        for test in self._by_import.get(stem, ()):
            found[id(test)] = test
        for test in self._by_import_suffix.get(stem, ()):
            found[id(test)] = test
        for i in range(len(module) + 1):
            for test in self._by_import.get(module[i:], ()):
                found[id(test)] = test
        for name in _symbol_names(item):
            if name.isidentifier():
                for test in self._by_word.get(name, ()):
                    found[id(test)] = test
            else:
                for test in self.candidates:
                    if re.search(rf"\b{re.escape(name)}\b", test.content_lower):
                        found[id(test)] = test
        return list(found.values())

    def related(self, item: FileInsight) -> list[FileInsight]:
        return [test for test in self.tests_for(item) if related_test_score(item, test) >= 4]

class RelatedSourceIndex:
    """The reverse lookup: which of ``sources`` does a test point at."""

    def __init__(self, sources: list[FileInsight]):
        self.sources = sources
        self._by_stem: dict[str, list[FileInsight]] = defaultdict(list)
        self._by_module_suffix: dict[str, list[FileInsight]] = defaultdict(list)
        self._by_word: dict[str, list[FileInsight]] = defaultdict(list)
        self._odd_symbols: list[FileInsight] = []
        for source in sources:
            self._by_stem[source.path.stem.lower()].append(source)
            module = _module_name(source)
            for i in range(len(module) + 1):
                self._by_module_suffix[module[i:]].append(source)
            for name in _symbol_names(source):
                if name.isidentifier():
                    self._by_word[name].append(source)
                else:
                    self._odd_symbols.append(source)

    def sources_for(self, test: FileInsight) -> list[FileInsight]:
        found: dict[int, FileInsight] = {}

        def add(group) -> None:
            for source in group:
                found[id(source)] = source

        add(self._odd_symbols)
        for stem in _test_target_stems(test.path.stem.lower()):
            add(self._by_stem.get(stem, ()))
        for imported in {value.lower() for value in test.imports}:
            add(self._by_stem.get(imported, ()))
            add(self._by_module_suffix.get(imported, ()))
            for suffix in _dotted_suffixes(imported):
                add(self._by_stem.get(suffix, ()))
        for word in test.content_words.intersection(self._by_word):
            add(self._by_word[word])
        return list(found.values())

    def has_related(self, test: FileInsight) -> bool:
        return any(related_test_score(source, test) >= 4 for source in self.sources_for(test))

_TEST_INDEX_CACHE: list = []

def related_test_index(candidates: list[FileInsight]) -> RelatedTestIndex:
    """One index per candidate list. The list object is the cache key."""
    if _TEST_INDEX_CACHE:
        cached_list, cached_len, index = _TEST_INDEX_CACHE[0]
        if cached_list is candidates and cached_len == len(candidates):
            return index
    index = RelatedTestIndex(candidates)
    _TEST_INDEX_CACHE[:] = [(candidates, len(candidates), index)]
    return index

def resolve_related_tests(item: FileInsight, insights: list[FileInsight]) -> set[str]:
    return {test.relpath.as_posix() for test in related_test_index(insights).related(item)}

def is_named_test_for(item: FileInsight, candidate: FileInsight) -> bool:
    rel = candidate.relpath.as_posix().lower()
    if "test" not in rel:
        return False

    target = item.path.stem.lower()
    cand = candidate.path.stem.lower()
    if cand == f"test_{target}" or cand == f"{target}_test":
        return True
    if cand.startswith("test_") and cand.endswith(f"_{target}"):
        return True
    return False

def related_test_score(item: FileInsight, candidate: FileInsight) -> int:
    rel = candidate.relpath.as_posix().lower()
    if "test" not in rel:
        return 0

    score = 0
    if is_named_test_for(item, candidate):
        score += 4

    item_stem = item.path.stem.lower()
    item_module = ".".join(item.relpath.with_suffix("").parts).lower()
    for imported in candidate.imports:
        imported = imported.lower()
        if (
            imported == item_stem
            or imported == item_module
            or imported.endswith(f".{item_stem}")
            or item_module.endswith(imported)
        ):
            score += 2
            break

    parent_name = item.relpath.parent.name.lower()
    if parent_name and parent_name != "." and parent_name in rel:
        score += 1

    fuzzy_name_score = normalized_name_similarity(item.path.stem, candidate.path.stem.replace("test_", "").replace("_test", ""))
    if fuzzy_name_score >= 92:
        score += 2
    elif fuzzy_name_score >= 80:
        score += 1

    symbol_names = [name for name in item.functions[:6] + item.classes[:4] if len(name) >= 4]
    if symbol_names:
        words = candidate.content_words
        mention_hits = 0
        for name in symbol_names:
            lowered = name.lower()
            if lowered.isidentifier():
                hit = lowered in words
            else:
                hit = re.search(rf"\b{re.escape(lowered)}\b", candidate.content_lower) is not None
            if hit:
                mention_hits += 1
                if mention_hits >= 2:
                    break
        score += 2 if mention_hits >= 2 else mention_hits

    return score

def test_relation_score(item: FileInsight, candidate: FileInsight) -> int:
    """Backwards-compatible name for :func:`related_test_score`.

    The ``test_`` prefix made pytest collect this production function, so the
    real name is ``related_test_score``. Kept for external callers.
    """
    return related_test_score(item, candidate)

test_relation_score.__test__ = False  # type: ignore[attr-defined]

def is_related_test_for(item: FileInsight, candidate: FileInsight) -> bool:
    return related_test_score(item, candidate) >= 4

def is_explicit_test_cover(item: FileInsight, candidate: FileInsight) -> bool:
    if not is_named_test_for(item, candidate):
        cand = candidate.path.stem.lower()
        target = item.path.stem.lower()
        if not (cand.startswith("test_") and target in cand):
            return False
    return related_test_score(item, candidate) >= 4

def is_test_file(path: Path) -> bool:
    rel = path.as_posix().lower()
    name = path.name.lower()
    return (
        rel.startswith("tests/")
        or "/tests/" in rel
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.tsx")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".test.js")
        or name.endswith(".test.jsx")
    )

def has_related_project_test(item: FileInsight, tests: list[FileInsight]) -> bool:
    if "test" in item.tags:
        return False
    return bool(related_test_index(tests).related(item))

_TAGGED_TESTS_CACHE: list = []

def _tagged_tests(all_files: list[FileInsight]) -> list[FileInsight]:
    """The test-tagged files of ``all_files``, built once per list object."""
    if _TAGGED_TESTS_CACHE:
        cached_list, cached_len, tests = _TAGGED_TESTS_CACHE[0]
        if cached_list is all_files and cached_len == len(all_files):
            return tests
    tests = [candidate for candidate in all_files if "test" in candidate.tags]
    _TAGGED_TESTS_CACHE[:] = [(all_files, len(all_files), tests)]
    return tests

def _test_target_stems(test_stem: str) -> set[str]:
    """Source stems a test file name points at: test_x, x_test, test_a_x."""
    stems = {test_stem[i + 1:] for i, ch in enumerate(test_stem) if ch == "_"}
    if test_stem.endswith("_test"):
        stems.add(test_stem[: -len("_test")])
    stems.discard("")
    return stems

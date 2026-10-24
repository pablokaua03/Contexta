"""contexta_app.engine.excerpts: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations



from contexta_app.engine.models import (
    FileInsight,
)
from contexta_app.engine.blobs import (
    build_embedded_asset_excerpt,
    sanitize_excerpt_lines,
)
from contexta_app.engine.focus import (
    _keyword_forms,
    extract_keywords,
)

def extract_signatures(item: FileInsight, focus: str = "", limit: int = 18) -> list[str]:
    """Up to ``limit`` definitions, shown in source order.

    When there are more than fit, the ones that match the focus words come first, then classes, then top-level
    functions, then methods. Source order alone cut a 1,400-line module off before its main function.
    """
    entries: list[tuple[int, str, bool]] = []
    lines = item.content.splitlines()

    if item.lang == "python":
        starts = ("def ", "async def ", "class ")
    elif item.lang in {"javascript", "jsx", "typescript", "tsx"}:
        starts = ("export ", "function ", "class ")
    else:
        return []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(starts):
            entries.append((index, stripped, line[:1] not in {" ", "\t"}))

    if len(entries) <= limit:
        return [text for _, text, _ in entries]
    stems = [form for word in extract_keywords(focus) for form in _keyword_forms(word)] if focus else []

    def priority(entry: tuple[int, str, bool]) -> tuple[int, int, int]:
        lower = entry[1].lower().replace("_", "")
        matched = any(stem.replace("_", "") in lower for stem in stems)
        tier = 0 if entry[1].startswith("class ") and entry[2] else (1 if entry[2] else 2)
        return (0 if matched else 1, tier, entry[0])

    chosen = sorted(sorted(entries, key=priority)[:limit], key=lambda entry: entry[0])
    return [text for _, text, _ in chosen]

def extract_relevant_excerpt(item: FileInsight, query: str, max_lines: int = 90) -> tuple[str, str]:
    lines = item.content.splitlines()
    keywords = extract_keywords(query)
    if not lines:
        return "", "No textual content available."

    if "embedded_asset" in item.tags:
        excerpt = build_embedded_asset_excerpt(item)
        reason = "Embedded asset payload omitted because the file mostly stores inline binary/base64 data."
        return excerpt, reason

    if not keywords:
        excerpt, omitted_blob = sanitize_excerpt_lines(item, lines[:max_lines])
        if not excerpt:
            return "<excerpt omitted>", "Opening excerpt omitted because the file content is not useful as readable source."
        reason = "Opening excerpt shown because no focus keywords were provided."
        if omitted_blob:
            reason += " Embedded blob lines were omitted."
        return "\n".join(excerpt), reason

    matches: list[int] = []
    for idx, line in enumerate(lines):
        lower = line.lower()
        if any(keyword in lower for keyword in keywords):
            matches.append(idx)

    if not matches:
        symbol_matches = [
            symbol
            for symbol in item.functions[:8] + item.classes[:6]
            if any(keyword in symbol.lower() for keyword in keywords)
        ]
        if symbol_matches:
            excerpt_lines = [
                stripped
                for stripped in extract_signatures(item, query, 200)
                if any(symbol in stripped for symbol in symbol_matches)
            ]
            if excerpt_lines:
                return "\n".join(excerpt_lines[:max_lines]), f"Focused excerpt based on matching symbols: {', '.join(symbol_matches[:4])}."
        excerpt, omitted_blob = sanitize_excerpt_lines(item, lines[:max_lines])
        if not excerpt:
            return "<excerpt omitted>", "Opening excerpt omitted because the file content is not useful as readable source."
        reason = "Opening excerpt shown because no focus match was found in the file."
        if omitted_blob:
            reason += " Embedded blob lines were omitted."
        return "\n".join(excerpt), reason

    gathered: list[str] = []
    used: set[int] = set()
    for idx in matches[:8]:
        start = max(0, idx - 2)
        end = min(len(lines), idx + 3)
        for line_no in range(start, end):
            if line_no not in used:
                gathered.append(lines[line_no])
                used.add(line_no)
            if len(gathered) >= max_lines:
                break
        if len(gathered) >= max_lines:
            break
    gathered, omitted_blob = sanitize_excerpt_lines(item, gathered[:max_lines])
    if not gathered:
        return "<excerpt omitted>", "Focused excerpt omitted because the matching content was not useful as readable source."
    reason = f"Focused excerpt based on keywords: {', '.join(keywords[:4])}."
    if omitted_blob:
        reason += " Embedded blob lines were omitted."
    return "\n".join(gathered[:max_lines]), reason

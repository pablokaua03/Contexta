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
    extract_keywords,
)

def extract_signatures(item: FileInsight) -> list[str]:
    signatures: list[str] = []
    lines = item.content.splitlines()

    if item.lang == "python":
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("async def ") or stripped.startswith("class "):
                signatures.append(stripped)
    elif item.lang in {"javascript", "jsx", "typescript", "tsx"}:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("export ") or stripped.startswith("function ") or stripped.startswith("class "):
                signatures.append(stripped)

    return signatures[:18]

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
                for stripped in extract_signatures(item)
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

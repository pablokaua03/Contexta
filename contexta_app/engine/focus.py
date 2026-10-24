"""contexta_app.engine.focus: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import re

from contexta_app.engine.constants import (
    STOPWORDS,
)
from contexta_app.engine.models import (
    FileInsight,
)

def matches_focus(item: FileInsight, query: str) -> bool:
    return compute_focus_score(item, query) > 0

def _keyword_forms(keyword: str) -> tuple[str, ...]:
    """The keyword plus a crude stem, so 'signing' also finds 'signer' and 'signature'."""
    forms = [keyword]
    for suffix in ("ing", "ation", "ion", "ers", "er", "ed", "es", "s", "y"):
        if keyword.endswith(suffix) and len(keyword) - len(suffix) >= 4:
            forms.append(keyword[: -len(suffix)])
            break
    return tuple(forms)

def compute_focus_raw(item: FileInsight, query: str) -> float:
    """Uncapped focus relevance. ``compute_focus_score`` caps it at 6 for scoring."""
    keywords = extract_keywords(query)
    if not keywords:
        return 0.0

    score = 0.0
    rel = item.relpath.as_posix().lower()
    stem = item.path.stem.lower()
    imports_blob = " ".join(imported.lower() for imported in item.imports)
    functions_blob = " ".join(func.lower() for func in item.functions)
    classes_blob = " ".join(cls.lower() for cls in item.classes)
    content_lower = item.content_lower
    words = item.content_words

    for keyword in keywords:
        best = 0.0
        for form in _keyword_forms(keyword):
            weight = 1.0 if form == keyword else 0.8
            part = 0.0
            if form == stem or form in rel:
                part += 2.0
            if form in functions_blob or form in classes_blob:
                part += 1.8
            if form in imports_blob:
                part += 1.4
            if (form in words) if form.isidentifier() else bool(re.search(rf"\b{re.escape(form)}\b", content_lower)):
                part += 0.8
            elif form in content_lower:
                part += 0.4
            best = max(best, part * weight)
        score += best

    return round(score, 2)

def compute_focus_score(item: FileInsight, query: str) -> float:
    return round(min(compute_focus_raw(item, query), 6.0), 2)

def extract_keywords(text: str) -> list[str]:
    parts = re.findall(r"[A-Za-z0-9_/-]+", text.lower())
    keywords = [part for part in parts if len(part) > 2 and part not in STOPWORDS]
    return list(dict.fromkeys(keywords[:10]))

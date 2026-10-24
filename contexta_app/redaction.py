"""
redaction.py - Best-effort secret redaction before context packs are exported.

This is a local, read-only pass. It does not decide whether a value is safe
to commit. It only keeps common credentials out of Markdown and JSON packs.

Two entry points share one set of rules:

- ``redact_secrets(text)`` replaces what it finds with ``[REDACTED]``.
- ``find_secrets(text)`` lists what it would replace (line, rule), never the value.

Rules, in order of confidence: private key blocks, credentials in URLs, bearer
tokens, known token formats, assignments to secret-looking names, and a
high-entropy heuristic. The heuristic skips hashes, UUIDs, URLs, paths,
placeholders, anything on the allowlist, and lines marked ``contexta:allow``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable

REDACTED = "[REDACTED]"

_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]{0,20000}?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)

_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GitHub token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9\-_]{16,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Slack webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9+/]+")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{16,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b")),
    ("Stripe key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("npm token", re.compile(r"\bnpm_[A-Za-z0-9]{20,}\b")),
    ("PyPI token", re.compile(r"\bpypi-[A-Za-z0-9\-_]{20,}\b")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("AWS temporary key id", re.compile(r"\bASIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("Google OAuth token", re.compile(r"\bya29\.[0-9A-Za-z\-_]{20,}\b")),
    ("JSON web token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
)

_URL_CREDENTIAL_RE = re.compile(
    r"\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|https?)://)"
    r"([^\s/:@]+):([^\s@/]+)@",
    re.IGNORECASE,
)

_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{16,}={0,2}")

_QUOTED_ASSIGN_RE = re.compile(
    r"(?P<key>\b[A-Za-z_][A-Za-z0-9_]*)['\"]?"
    r"(?P<sep>\s*[=:]\s*)"
    r"(?P<q>['\"])"
    r"(?P<value>[^'\"\n]*)"
    r"(?P=q)"
)

_ENV_LINE_RE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:export\s+)?)"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<eq>\s*[=:]\s*)"
    r"(?P<q>['\"]?)"
    r"(?P<value>[^\s#'\"]+)"
    r"(?P=q)\s*$"
)

_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(?:^|_)"
    r"(api[_-]?key|apikey|secret(?:[_-]?key)?|password|passwd|pwd|token|"
    r"access[_-]?key|auth[_-]?token|client[_-]?secret|private[_-]?key|"
    r"credential|credentials)$"
)

_PLACEHOLDER_VALUES = frozenset(
    {
        "changeme",
        "change_me",
        "change-me",
        "password",
        "secret",
        "token",
        "example",
        "example_key",
        "example-key",
        "placeholder",
        "your_api_key",
        "your-api-key",
        "your_token",
        "your-token",
        "insert_key",
        "insert-key-here",
        "replace_me",
        "replace-me",
        "todo",
        "undefined",
        "null",
        "none",
        "false",
        "true",
        "test",
        "testing",
        "sample",
        "dummy",
        "redacted",
        "<redacted>",
        "xxx",
        "xxxxxxxx",
        "********",
    }
)


# A name that hints at a secret anywhere in it, for the entropy heuristic.
_HINT_KEY_RE = re.compile(
    r"(?i)(key|token|secret|pass|pwd|auth|cred|salt|dsn|private|bearer|jwt)"
)

ENTROPY_MIN_LEN = 20
ENTROPY_MAX_LEN = 80
ENTROPY_MIN_DIGITS = 2
ENTROPY_HINT_BITS = 3.5
ENTROPY_STANDALONE_MIN_LEN = 32
ENTROPY_STANDALONE_BITS = 4.2
ALLOW_MARKERS = ("contexta:allow", "pragma: allowlist secret", "gitleaks:allow", "nosec secret")

_STRING_LITERAL_RE = re.compile(r"(?P<q>['\"])(?P<value>[^'\"\n\\]{20,400})(?P=q)")
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_INTEGRITY_RE = re.compile(r"^(?:sha(?:1|256|384|512)|md5)[-:]", re.IGNORECASE)
_VERSION_RE = re.compile(r"^[vV]?\d+(?:\.\d+){1,}")
_SECRET_CHARS_RE = re.compile(r"^[A-Za-z0-9+/=_\-.~]+$")
_IDENTIFIER_PART_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TEMPLATE_MARKERS = ("${", "{{", "{%", "<%", "%(", "%s", "$(", "os.environ", "getenv", "process.env", "secrets.")


@dataclass(frozen=True)
class Finding:
    """One thing the redactor would replace. Never carries the value."""

    line: int
    kind: str
    detail: str = ""
    start: int = 0
    end: int = 0


def shannon_entropy(value: str) -> float:
    """Bits per character."""
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = len(value)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def _char_classes(value: str) -> int:
    return sum(
        (
            any(c.islower() for c in value),
            any(c.isupper() for c in value),
            any(c.isdigit() for c in value),
            any(not c.isalnum() for c in value),
        )
    )


def _sequential_share(value: str) -> float:
    """Share of neighbouring characters that are consecutive (abc, 123). Alphabet tables score high."""
    if len(value) < 2:
        return 0.0
    steps = sum(1 for a, b in zip(value, value[1:]) if ord(b) - ord(a) == 1)
    return steps / (len(value) - 1)


def _mixed_case(value: str) -> bool:
    letters = [c for c in value if c.isalpha()]
    if len(letters) < 10:
        return False
    upper = sum(c.isupper() for c in letters) / len(letters)
    return 0.25 <= upper <= 0.75


def _looks_generated(value: str) -> bool:
    """Skip values that are high-entropy but not secrets: hashes, UUIDs, URLs, paths, versions."""
    if _sequential_share(value) >= 0.3:
        return True
    if _UUID_RE.match(value) or _INTEGRITY_RE.match(value) or _VERSION_RE.match(value):
        return True
    if "://" in value or value.startswith(("./", "../", "~", "#", "@")):
        return True
    if value.startswith("/") and "+" not in value and not _mixed_case(value):
        return True
    if value.startswith("data:") or value.startswith("mailto:"):
        return True
    if any(marker in value for marker in _TEMPLATE_MARKERS):
        return True
    if value.count("/") >= 2 and "+" not in value and not _mixed_case(value):
        return True  # a path; base64 with slashes has random upper and lower case
    if value.count(".") >= 3 and "-" not in value:
        return True
    if value.count(" ") or "\t" in value:
        return True
    lowered = value.lower()
    if any(word in lowered for word in ("example", "placeholder", "changeme", "your_", "your-", "xxxxxxxx", "lorem")):
        return True
    if len(set(value)) <= 4:
        return True
    return False


def _entropy_candidate(value: str, key_hint: bool, allow: frozenset[str]) -> str:
    """Return the rule name if ``value`` looks like a random secret, else ''.

    Random keys are drawn from a small alphabet, have digits mixed in, and are
    not words, code, hashes, URLs or paths. Anything else is left alone, so the
    heuristic favors missing an odd secret over redacting ordinary code.
    """
    if value in allow or value == REDACTED:
        return ""
    if not ENTROPY_MIN_LEN <= len(value) <= ENTROPY_MAX_LEN:
        return ""
    if _SECRET_CHARS_RE.match(value) is None or _looks_generated(value):
        return ""
    base64_like = ("+" in value or "/" in value) and _mixed_case(value)
    if sum(c.isdigit() for c in value) < ENTROPY_MIN_DIGITS and not base64_like:
        return ""
    parts = [part for part in re.split(r"[.]", value) if part]
    if len(parts) > 1 and all(_IDENTIFIER_PART_RE.match(part) for part in parts):
        return ""  # dotted attribute access such as pkg.module.Class2
    bits = shannon_entropy(value)
    classes = _char_classes(value)
    is_hex = _HEX_RE.match(value) is not None
    if key_hint:
        # A hex string under a secret-like name is plausibly a key, not a git sha.
        if bits >= (3.0 if is_hex else ENTROPY_HINT_BITS) and (classes >= 2 or is_hex):
            return "high-entropy value under a secret-like name"
        return ""
    if is_hex or len(value) < ENTROPY_STANDALONE_MIN_LEN:
        return ""
    if bits >= ENTROPY_STANDALONE_BITS and classes >= 3:
        return "high-entropy string"
    return ""


def _is_sensitive_key(key: str) -> bool:
    return _SENSITIVE_KEY_RE.search(key) is not None


def _is_yaml_word(match: "re.Match[str]") -> bool:
    """`token: Optional` (a type hint) or `password: required` is not a value. Colon form needs a digit."""
    if ":" not in match.group("eq") or match.group("q"):
        return False
    return not any(char.isdigit() for char in match.group("value"))


def _keep_literal(value: str) -> bool:
    """Return True when a quoted or env value should stay in the export."""
    raw = value.strip()
    if len(raw) < 8:
        return True
    if raw.lower() in _PLACEHOLDER_VALUES:
        return True
    if raw == REDACTED:
        return True
    if any(char.isspace() for char in raw):
        return True
    if any(char in raw for char in "()[]{}"):
        return True
    return False


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for match in re.finditer("\n", text):
        starts.append(match.end())
    return starts


def _line_of(starts: list[int], offset: int) -> int:
    lo, hi = 0, len(starts)
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid
    return lo + 1


def find_secrets(
    text: str,
    *,
    allow: Iterable[str] = (),
    entropy: bool = True,
) -> list[Finding]:
    """Everything ``redact_secrets`` would replace, with line numbers and rule names.

    Findings never include the secret. ``allow`` is a set of literal values to
    leave alone. A line containing ``contexta:allow`` is skipped.
    """
    if not text:
        return []
    allowed = frozenset(a for a in allow if a)
    starts = _line_starts(text)
    lines = text.split("\n")
    spans: list[Finding] = []

    def line_allowed(offset: int) -> bool:
        line = lines[_line_of(starts, offset) - 1].lower()
        return any(marker in line for marker in ALLOW_MARKERS)

    def add(start: int, end: int, kind: str, detail: str = "") -> None:
        if end <= start or text[start:end] in allowed or line_allowed(start):
            return
        spans.append(Finding(_line_of(starts, start), kind, detail, start, end))

    for match in _PRIVATE_KEY_RE.finditer(text):
        add(match.start(), match.end(), "private key block")
    for match in _URL_CREDENTIAL_RE.finditer(text):
        add(match.start(3), match.end(3), "password in URL", match.group(1).rstrip(":/"))
    for match in _BEARER_RE.finditer(text):
        add(match.start(), match.end(), "bearer token")
    for match in _QUOTED_ASSIGN_RE.finditer(text):
        if _is_sensitive_key(match.group("key")) and not _keep_literal(match.group("value")):
            add(match.start("value"), match.end("value"), "secret-named assignment", match.group("key"))
    for match in _ENV_LINE_RE.finditer(text):
        if _is_yaml_word(match):
            continue
        if _is_sensitive_key(match.group("key")) and not _keep_literal(match.group("value")):
            add(match.start("value"), match.end("value"), "secret-named assignment", match.group("key"))
    for name, pattern in _TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            add(match.start(), match.end(), "known token format", name)

    if entropy:
        for match in _QUOTED_ASSIGN_RE.finditer(text):
            key = match.group("key")
            rule = _entropy_candidate(match.group("value"), bool(_HINT_KEY_RE.search(key)), allowed)
            if rule:
                add(match.start("value"), match.end("value"), rule, key if _HINT_KEY_RE.search(key) else "")
        for match in _ENV_LINE_RE.finditer(text):
            if _is_yaml_word(match):
                continue
            key = match.group("key")
            rule = _entropy_candidate(match.group("value"), bool(_HINT_KEY_RE.search(key)), allowed)
            if rule:
                add(match.start("value"), match.end("value"), rule, key)
        for match in _STRING_LITERAL_RE.finditer(text):
            rule = _entropy_candidate(match.group("value"), False, allowed)
            if rule:
                add(match.start("value"), match.end("value"), rule)

    return _merge(spans)


def _merge(spans: list[Finding]) -> list[Finding]:
    """Drop overlaps so one secret counts once. The earliest, widest rule wins."""
    ordered = sorted(spans, key=lambda f: (f.start, -(f.end - f.start)))
    merged: list[Finding] = []
    for finding in ordered:
        if merged and finding.start < merged[-1].end:
            previous = merged[-1]
            if finding.end > previous.end:
                merged[-1] = Finding(previous.line, previous.kind, previous.detail, previous.start, finding.end)
            continue
        merged.append(finding)
    return merged


def redact_secrets(
    text: str,
    *,
    allow: Iterable[str] = (),
    entropy: bool = True,
) -> tuple[str, int]:
    """Replace likely credentials with ``[REDACTED]``.

    Returns ``(redacted_text, replacement_count)``. A count of zero means the
    text was left unchanged. Patterns favor precision: ordinary identifiers,
    form field names, and obvious placeholders are kept.
    """
    findings = find_secrets(text, allow=allow, entropy=entropy)
    if not findings:
        return text, 0
    out: list[str] = []
    cursor = 0
    for finding in findings:
        out.append(text[cursor:finding.start])
        out.append(REDACTED)
        cursor = finding.end
    out.append(text[cursor:])
    return "".join(out), len(findings)

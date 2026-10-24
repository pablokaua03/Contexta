"""
redaction.py - Best-effort secret redaction before context packs are exported.

This is a local, read-only pass. It does not decide whether a value is safe
to commit. It only keeps common credentials out of Markdown and JSON packs.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]{0,20000}?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)

_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9\-_]{16,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9+/]+"),
    re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{16,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bnpm_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bpypi-[A-Za-z0-9\-_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    re.compile(r"\bya29\.[0-9A-Za-z\-_]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)

_URL_CREDENTIAL_RE = re.compile(
    r"\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|https?)://)"
    r"([^\s/:@]+):([^\s@/]+)@",
    re.IGNORECASE,
)

_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{16,}={0,2}")

_QUOTED_ASSIGN_RE = re.compile(
    r"(?P<key>\b[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<sep>\s*[=:]\s*)"
    r"(?P<q>['\"])"
    r"(?P<value>[^'\"\n]*)"
    r"(?P=q)"
)

_ENV_LINE_RE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:export\s+)?)"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<eq>\s*=\s*)"
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


def _is_sensitive_key(key: str) -> bool:
    return _SENSITIVE_KEY_RE.search(key) is not None


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


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace likely credentials with ``[REDACTED]``.

    Returns ``(redacted_text, replacement_count)``. A count of zero means the
    text was left unchanged. Patterns favor precision: ordinary identifiers,
    form field names, and obvious placeholders are kept.
    """
    if not text:
        return text, 0

    count = 0

    def apply(pattern: re.Pattern[str], repl) -> None:
        nonlocal text, count

        def wrapper(match: re.Match[str]) -> str:
            nonlocal count
            updated = repl(match)
            if updated != match.group(0):
                count += 1
            return updated

        text = pattern.sub(wrapper, text)

    def replace_token(match: re.Match[str]) -> str:
        return REDACTED

    apply(_PRIVATE_KEY_RE, replace_token)
    apply(_URL_CREDENTIAL_RE, lambda match: f"{match.group(1)}{match.group(2)}:{REDACTED}@")
    apply(_BEARER_RE, replace_token)

    def replace_quoted(match: re.Match[str]) -> str:
        if not _is_sensitive_key(match.group("key")) or _keep_literal(match.group("value")):
            return match.group(0)
        return (
            f"{match.group('key')}{match.group('sep')}"
            f"{match.group('q')}{REDACTED}{match.group('q')}"
        )

    apply(_QUOTED_ASSIGN_RE, replace_quoted)

    def replace_env(match: re.Match[str]) -> str:
        if not _is_sensitive_key(match.group("key")) or _keep_literal(match.group("value")):
            return match.group(0)
        quote = match.group("q")
        return (
            f"{match.group('prefix')}{match.group('key')}{match.group('eq')}"
            f"{quote}{REDACTED}{quote}"
        )

    apply(_ENV_LINE_RE, replace_env)

    for pattern in _TOKEN_PATTERNS:
        apply(pattern, replace_token)

    return text, count

"""
safety.py - Files Contexta never reads into a pack or hands to an agent.

Credential files are kept out by name, no matter what is inside them. This is
separate from redaction, which scrubs secrets from files that are exported.
"""

from __future__ import annotations

import fnmatch
from pathlib import PurePath

# Matched against the lowercase file name.
SENSITIVE_NAMES: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*.kdbx",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".git-credentials",
    "credentials",
    "credentials.json",
    "secrets.json",
    "secrets.yml",
    "secrets.yaml",
    "service-account*.json",
    "terraform.tfstate*",
    "*.tfvars",
)

# Safe templates that share a sensitive prefix.
SAFE_NAMES: tuple[str, ...] = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    ".env.defaults",
    "*.pub",
)

SENSITIVE_DIRS = frozenset({".ssh", ".gnupg", ".aws", ".kube"})


def is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    if any(fnmatch.fnmatchcase(lowered, pattern) for pattern in SAFE_NAMES):
        return False
    return any(fnmatch.fnmatchcase(lowered, pattern) for pattern in SENSITIVE_NAMES)


def is_sensitive_path(path: str | PurePath) -> bool:
    """True for a credential file, or anything inside ~/.ssh, ~/.aws and friends."""
    pure = PurePath(path)
    if SENSITIVE_DIRS & {part.lower() for part in pure.parts[:-1]}:
        return True
    return is_sensitive_name(pure.name)

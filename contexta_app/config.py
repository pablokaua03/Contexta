"""
config.py - Project and user configuration for Contexta.

Project files (first match in the project root):
    contexta.toml
    .contexta.toml

User defaults:
    ~/.contexta/config.toml
    Override the directory with CONTEXTA_HOME.

CLI flags win over the project file, which wins over the user file.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

PROJECT_CONFIG_NAMES: tuple[str, ...] = ("contexta.toml", ".contexta.toml")
IGNORE_FILE_NAME = ".contextaignore"

_KNOWN_KEYS = frozenset(
    {
        "pack",
        "mode",
        "ai",
        "task",
        "compression",
        "focus",
        "format",
        "redact",
        "base",
        "output",
        "copy",
        "hidden",
        "unknown",
        "diff",
        "staged",
        "ignore",
        "max_tokens",
        "max_files",
        "redact_allow",
        "redact_entropy",
    }
)


class ConfigError(Exception):
    """A config file exists but Contexta cannot use it safely."""


@dataclass
class ContextaConfig:
    pack: str | None = None
    mode: str | None = None
    ai: str | None = None
    task: str | None = None
    compression: str | None = None
    focus: str | None = None
    format: str | None = None
    redact: bool | None = None
    base: str | None = None
    output: str | None = None
    copy: bool | None = None
    hidden: bool | None = None
    unknown: bool | None = None
    diff: bool | None = None
    staged: bool | None = None
    ignore: list[str] = field(default_factory=list)
    max_tokens: int | None = None
    max_files: int | None = None
    redact_allow: list[str] = field(default_factory=list)
    redact_entropy: bool | None = None
    warnings: list[str] = field(default_factory=list)
    source: str = ""

    def overlay(self, other: "ContextaConfig") -> "ContextaConfig":
        """Return this config with non-empty values from ``other`` applied on top."""
        merged = replace(self)
        for key in (
            "pack",
            "mode",
            "ai",
            "task",
            "compression",
            "focus",
            "format",
            "redact",
            "base",
            "output",
            "copy",
            "hidden",
            "unknown",
            "diff",
            "staged",
            "max_tokens",
            "max_files",
            "redact_entropy",
        ):
            value = getattr(other, key)
            if value is not None:
                setattr(merged, key, value)
        if other.ignore:
            merged.ignore = list(other.ignore)
        if other.redact_allow:
            merged.redact_allow = list(other.redact_allow)
        merged.warnings = [*self.warnings, *other.warnings]
        merged.source = other.source or self.source
        return merged


def user_config_dir() -> Path:
    override = os.environ.get("CONTEXTA_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".contexta"


def user_config_path() -> Path:
    return user_config_dir() / "config.toml"


def find_project_config(project: Path) -> Path | None:
    for name in PROJECT_CONFIG_NAMES:
        candidate = project / name
        if candidate.is_file():
            return candidate
    return None


def load_user_config() -> ContextaConfig:
    path = user_config_path()
    if not path.is_file():
        return ContextaConfig()
    return _load_file(path)


def load_project_config(project: Path) -> ContextaConfig:
    path = find_project_config(project)
    if path is None:
        return ContextaConfig()
    return _load_file(path)


def load_effective_config(project: Path) -> ContextaConfig:
    """User defaults overlaid by the project file."""
    return load_user_config().overlay(load_project_config(project))


def project_ignore_patterns(project: Path) -> list[str]:
    """Extra ignore rules from the project config only.

    User-level config is intentionally not applied here so a personal defaults
    file cannot hide files inside someone else's repository.
    """
    config = load_project_config(project)
    return list(config.ignore)


def _load_file(path: Path) -> ContextaConfig:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not read {path.name}: {exc}") from exc
    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"Could not read {path.name}: {exc}.\n"
            "Fix the file, or move it aside and run: contexta --init"
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must be a TOML table of settings.")
    return _parse_table(data, source=path.name)


def _parse_table(data: dict, source: str) -> ContextaConfig:
    warnings: list[str] = []
    unknown = sorted(set(data) - _KNOWN_KEYS)
    for key in unknown:
        warnings.append(f"{source}: ignored unknown setting '{key}'.")

    config = ContextaConfig(source=source, warnings=warnings)
    config.pack = _optional_str(data, "pack", source)
    config.mode = _optional_str(data, "mode", source)
    config.ai = _optional_str(data, "ai", source)
    config.task = _optional_str(data, "task", source)
    config.compression = _optional_str(data, "compression", source)
    config.focus = _optional_str(data, "focus", source)
    config.format = _optional_choice(data, "format", source, {"md", "json"})
    config.base = _optional_str(data, "base", source)
    config.output = _optional_str(data, "output", source)
    config.redact = _optional_bool(data, "redact", source)
    config.copy = _optional_bool(data, "copy", source)
    config.hidden = _optional_bool(data, "hidden", source)
    config.unknown = _optional_bool(data, "unknown", source)
    config.diff = _optional_bool(data, "diff", source)
    config.staged = _optional_bool(data, "staged", source)
    config.ignore = _optional_str_list(data, "ignore", source)
    config.max_tokens = _optional_positive_int(data, "max_tokens", source)
    config.max_files = _optional_positive_int(data, "max_files", source)
    config.redact_allow = _optional_str_list(data, "redact_allow", source)
    config.redact_entropy = _optional_bool(data, "redact_entropy", source)
    _validate_choices(config, source)
    return config


def _validate_choices(config: ContextaConfig, source: str) -> None:
    # Imported lazily so config loading does not cycle through the scanner.
    from contexta_app.context_engine import (
        AI_PROFILE_OPTIONS,
        COMPRESSION_OPTIONS,
        CONTEXT_MODE_OPTIONS,
        PACK_OPTIONS,
        TASK_PROFILE_OPTIONS,
    )

    _require_choice(config.pack, "pack", source, set(PACK_OPTIONS))
    _require_choice(config.mode, "mode", source, set(CONTEXT_MODE_OPTIONS))
    _require_choice(config.ai, "ai", source, set(AI_PROFILE_OPTIONS))
    _require_choice(config.task, "task", source, set(TASK_PROFILE_OPTIONS))
    _require_choice(config.compression, "compression", source, set(COMPRESSION_OPTIONS))


def _require_choice(value: str | None, key: str, source: str, choices: set[str]) -> None:
    if value is None or value in choices:
        return
    listed = ", ".join(sorted(choices))
    raise ConfigError(
        f"{source}: {key} = \"{value}\" is not a known value.\n"
        f"Choose one of: {listed}"
    )


def _optional_str(data: dict, key: str, source: str) -> str | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{source}: {key} must be a non-empty string.")
    return value.strip()


def _optional_choice(data: dict, key: str, source: str, choices: set[str]) -> str | None:
    value = _optional_str(data, key, source)
    if value is None:
        return None
    if value not in choices:
        listed = ", ".join(sorted(choices))
        raise ConfigError(f"{source}: {key} = \"{value}\" is not supported. Choose one of: {listed}")
    return value


def _optional_bool(data: dict, key: str, source: str) -> bool | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, bool):
        raise ConfigError(f"{source}: {key} must be true or false.")
    return value


def _optional_str_list(data: dict, key: str, source: str) -> list[str]:
    if key not in data:
        return []
    value = data[key]
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ConfigError(f"{source}: {key} must be a list of non-empty strings.")
    return [item.strip() for item in value]


def _optional_positive_int(data: dict, key: str, source: str) -> int | None:
    if key not in data:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{source}: {key} must be a positive integer.")
    return value


STARTER_PROJECT_CONFIG = """\
# Contexta project config. CLI flags override these values.
# Create it with: contexta --init

pack = "onboarding"
ai = "claude"
compression = "balanced"
redact = true

# Used when the pack or --diff is comparing git changes.
# base = "main"

# Extra ignore rules (gitignore syntax), applied after .gitignore
# and .contextaignore. Example: ["generated/", "*.snap"]
ignore = []

# Soft token ceiling. When set, Contexta tightens compression until the
# pack fits, then stops at lean. Example: 32000
# max_tokens = 32000

# Stop scanning after this many files (default 2000).
# max_files = 5000

# Values the redactor must leave alone (exact match), for example a public
# test key. A line containing "contexta:allow" is skipped too.
# redact_allow = []

# Flag random-looking strings as secrets even without a known prefix.
# redact_entropy = true
"""

STARTER_IGNORE_FILE = """\
# Files to keep out of Contexta packs. Same syntax as .gitignore.
# Secrets in files that are still exported are redacted separately.

*.snap
coverage/
"""


def write_starter_files(project: Path) -> list[str]:
    """Create missing starter files. Existing files are left untouched.

    Returns the names of files that were created.
    """
    project.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    config_path = project / PROJECT_CONFIG_NAMES[0]
    ignore_path = project / IGNORE_FILE_NAME
    if not find_project_config(project):
        config_path.write_text(STARTER_PROJECT_CONFIG, encoding="utf-8")
        created.append(config_path.name)
    if not ignore_path.exists():
        ignore_path.write_text(STARTER_IGNORE_FILE, encoding="utf-8")
        created.append(ignore_path.name)
    return created

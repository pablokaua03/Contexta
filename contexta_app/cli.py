"""
cli.py - Command-line interface for Contexta.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from contexta_app.budgets import format_budget_report, next_compression
from contexta_app.cli_style import format_ai_header, format_banner, format_log_line, format_saved, paint
from contexta_app.config import (
    ConfigError,
    load_project_config,
    load_user_config,
    write_starter_files,
)
from contexta_app.context_engine import (
    AI_PROFILE_OPTIONS,
    COMPRESSION_OPTIONS,
    CONTEXT_MODE_OPTIONS,
    PACK_DEFAULTS,
    PACK_OPTIONS,
    TASK_PROFILE_OPTIONS,
)
from contexta_app.renderer import __version__, export_pack
from contexta_app.scanner import GitError, GitRefError, git_ref_exists, git_state
from contexta_app.utils import get_desktop, safe_project_name

_DIFF_PACKS = frozenset({"pr_review", "changes_related"})


class ProjectPathError(Exception):
    """The path passed to the CLI is not a project directory."""


@dataclass
class RunPlan:
    project: Path
    include_hidden: bool
    include_unknown: bool
    diff_mode: bool
    staged_only: bool
    system_prompt: str
    context_mode: str
    ai_profile: str
    task_profile: str
    compression: str
    pack_profile: str
    focus_query: str
    locked_fields: tuple[str, ...]
    redact_secrets: bool
    redact_allow: tuple[str, ...]
    redact_entropy: bool
    dry_run: bool
    base_ref: str | None
    output_format: str
    output: str | None
    copy: bool
    max_tokens: int | None
    max_files: int | None
    to_stdout: bool
    ask: str
    provider: str
    api_key: str
    model: str
    warnings: tuple[str, ...]


class _RedactFlag(argparse.Action):
    """``--redact`` and ``--no-redact`` write one tri-state value and refuse to be combined."""

    def __call__(self, parser, namespace, values, option_string=None):
        previous = getattr(namespace, self.dest, None)
        if previous is not None and previous != self.const:
            parser.error("use either --redact or --no-redact, not both")
        setattr(namespace, self.dest, self.const)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contexta",
        description=(
            "Build a curated context pack from a codebase for Cursor, Claude Code,\n"
            "Copilot, ChatGPT, and other coding agents.\n"
            "\n"
            "Reads contexta.toml (or .contexta.toml) and .contextaignore from the\n"
            "project when they exist. CLI flags override the project file, which\n"
            "overrides ~/.contexta/config.toml. Common secrets are redacted before\n"
            "the pack is written."
        ),
        epilog=(
            "examples:\n"
            "  contexta .\n"
            "  contexta . --pack onboarding --copy\n"
            "  contexta . --pack bugfix --focus \"login timeout\"\n"
            "  contexta . --pack pr_review --base main --stdout\n"
            "  contexta . --pack refactor --format json -o pack.json\n"
            "  contexta . --budget 20000 --focus \"session cookie signing\"\n"
            "  contexta --init\n"
            "  contexta serve\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("project", nargs="?", default=None, help="Path to the project folder")
    parser.add_argument("--init", action="store_true", help="Write contexta.toml and .contextaignore if they are missing, then exit")
    parser.add_argument("--version", action="version", version=f"Contexta {__version__}")

    pack = parser.add_argument_group("pack")
    pack.add_argument("--pack", choices=sorted(PACK_OPTIONS), default=None, help="Preset workflow. Default: custom, or the pack in contexta.toml")
    pack.add_argument("--mode", choices=sorted(CONTEXT_MODE_OPTIONS), default=None, help="How files are chosen: full, debug, feature, diff, onboarding, refactor")
    pack.add_argument("--ai", choices=sorted(AI_PROFILE_OPTIONS), default=None, help="Model profile used for budget guidance: generic, chatgpt, claude, gemini, copilot")
    pack.add_argument("--task", choices=sorted(TASK_PROFILE_OPTIONS), default=None, help="Task lens such as bug_report, code_review, explain_project, or refactor_request")
    pack.add_argument("--compression", choices=sorted(COMPRESSION_OPTIONS), default=None, help="How much source to keep: full, balanced, focused, signatures, lean")
    pack.add_argument("--focus", default=None, help="Bias file selection around a topic, for example \"auth flow\"")
    pack.add_argument("-p", "--prompt", default="", help="Custom instruction included in the pack")
    pack.add_argument(
        "--budget", "--max-tokens", dest="max_tokens", type=int, default=None, metavar="N",
        help="Token budget. Files are ranked and kept at full, signature or lean detail until N tokens are used. "
             "The pack says what was left out. Combine with --focus to spend it where you care",
    )

    pack.add_argument("--max-files", type=int, default=None, help="Stop scanning after this many files. Default: 2000, or CONTEXTA_MAX_FILES")

    git = parser.add_argument_group("git")
    git.add_argument("--diff", action="store_true", help="Prefer git changes when selecting files")
    git.add_argument("--staged", action="store_true", help="Limit git detection to staged changes")
    git.add_argument("--base", default=None, help="Git ref to compare against, for example main or origin/main. Uses a merge-base diff and includes uncommitted work")

    output = parser.add_argument_group("output")
    output.add_argument("-o", "--output", default=None, help="Output file. Use - to write the pack to stdout")
    output.add_argument("--stdout", action="store_true", help="Write the pack to stdout instead of a file")
    output.add_argument("--format", choices=("md", "json"), default=None, help="md (default) or json. JSON wraps the same Markdown pack")
    output.add_argument("-c", "--copy", action="store_true", help="Copy the pack to the clipboard")
    output.add_argument("--hidden", action="store_true", help="Include hidden files and folders")
    output.add_argument("--unknown", action="store_true", help="Include files with unrecognised extensions")

    safety = parser.add_argument_group("safety")
    safety.add_argument("--redact", dest="redact", action=_RedactFlag, nargs=0, const=True, default=None,
                        help="Force secret redaction on, even if a config file turns it off. This is the default")
    safety.add_argument("--no-redact", dest="redact", action=_RedactFlag, nargs=0, const=False,
                        help="Keep secret-like values in the export. Redaction is on by default")
    safety.add_argument("--dry-run", action="store_true",
                        help="List what would be redacted (file, line, rule; never the value) and write no pack")

    ai = parser.add_argument_group("ai api")
    ai.add_argument("--ask", default="", help="Send the pack and this prompt to an AI API, then print the reply")
    ai.add_argument("--provider", choices=["claude", "gemini", "openai"], default="", help="AI provider for --ask")
    ai.add_argument("--api-key", default="", help="API key for --ask. Prefer an environment variable when you can")
    ai.add_argument("--model", default="", help="Override the default model for --ask")
    ai.add_argument("--configure-ai", action="store_true", help="Save an AI provider, API key, and model under ~/.contexta/ai_config.json")
    return parser


def validate_project(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.exists():
        raise ProjectPathError(
            f"No such directory: {path}\n"
            "Pass the project folder you want to pack.\n"
            "Example: contexta ."
        )
    if path.is_file():
        raise ProjectPathError(
            f"Contexta packs a project folder, and this path is a file:\n  {path}\n"
            f"Try the parent directory:\n  contexta {path.parent}"
        )
    if not path.is_dir():
        raise ProjectPathError(f"Not a directory: {path}")
    return path.resolve()


def _clipboard_commands() -> list[list[str]]:
    if sys.platform == "win32":
        return [["clip"]]
    if sys.platform == "darwin":
        return [["pbcopy"]]
    return [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ]


def copy_to_clipboard(text: str, *, status=print) -> bool:
    """Copy ``text`` using the first available platform clipboard tool."""
    data = text.encode("utf-16") if sys.platform == "win32" else text.encode("utf-8")
    last_error = "no clipboard tool found"
    for cmd in _clipboard_commands():
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                proc.communicate(input=data)
                if proc.returncode == 0:
                    status("Copied to clipboard.")
                    return True
                last_error = f"{cmd[0]} exited with status {proc.returncode}"
                continue
            subprocess.run(cmd, input=data, check=True)
            status("Copied to clipboard.")
            return True
        except FileNotFoundError:
            last_error = f"{cmd[0]} is not installed"
        except Exception as exc:
            last_error = str(exc)
    status(
        "Could not copy to clipboard: "
        f"{last_error}. On Linux install wl-clipboard or xclip, or rerun with --stdout."
    )
    return False


def _choose(locked: list[str], field_name: str, flag_value, config_value, preset_value, builtin):
    if flag_value is not None:
        locked.append(field_name)
        return flag_value
    if config_value is not None:
        locked.append(field_name)
        return config_value
    if preset_value is not None:
        return preset_value
    return builtin


def build_plan(args, project: Path, *, stdout_isatty: bool) -> RunPlan:
    user_cfg = load_user_config()
    project_cfg = load_project_config(project)
    warnings = list(user_cfg.warnings) + list(project_cfg.warnings)
    if user_cfg.ignore:
        warnings.append(
            "Ignore rules in the user config are not applied. "
            "Put them in contexta.toml, .contextaignore, or .gitignore inside the project."
        )
    cfg = user_cfg.overlay(project_cfg)

    if args.max_tokens is not None and args.max_tokens <= 0:
        raise ConfigError("--budget must be a positive integer.")
    if args.max_files is not None and args.max_files <= 0:
        raise ConfigError("--max-files must be a positive integer.")
    if args.base is not None and not str(args.base).strip():
        raise ConfigError("--base needs a git ref. Example: --base main")

    locked: list[str] = []
    pack = args.pack or cfg.pack or "custom"
    preset = PACK_DEFAULTS.get(pack, {})
    mode = _choose(locked, "context_mode", args.mode, cfg.mode, preset.get("context_mode"), "full")
    ai_profile = _choose(locked, "ai_profile", args.ai, cfg.ai, preset.get("ai_profile"), "generic")
    task = _choose(locked, "task_profile", args.task, cfg.task, preset.get("task_profile"), "general")
    compression = _choose(locked, "compression", args.compression, cfg.compression, preset.get("compression"), "balanced")
    focus = _choose(locked, "focus_query", args.focus, cfg.focus, preset.get("focus_query"), "")

    explicit_diff = bool(args.diff or args.staged or cfg.diff or cfg.staged)
    user_base = args.base.strip() if isinstance(args.base, str) else None
    wants_base = user_base is not None or pack in _DIFF_PACKS or mode == "diff" or explicit_diff
    base = user_base if user_base is not None else (cfg.base if wants_base else None)
    diff_mode = explicit_diff or base is not None or pack in _DIFF_PACKS
    if base and (args.staged or cfg.staged):
        warnings.append("--base includes committed and uncommitted changes. --staged is ignored when --base is set.")
    if diff_mode and mode == "full" and "context_mode" not in locked:
        mode = "diff"

    if args.redact is not None:
        redact = args.redact
    elif cfg.redact is not None:
        redact = cfg.redact
    else:
        redact = True

    output_format = args.format or cfg.format or "md"
    output = args.output if args.output is not None else cfg.output
    to_stdout = bool(args.stdout or output == "-")
    if not to_stdout and output is None and not stdout_isatty and not args.ask:
        to_stdout = True

    max_tokens = args.max_tokens if args.max_tokens is not None else cfg.max_tokens
    return RunPlan(
        project=project,
        include_hidden=bool(args.hidden or cfg.hidden),
        include_unknown=bool(args.unknown or cfg.unknown),
        diff_mode=diff_mode,
        staged_only=bool(args.staged or cfg.staged),
        system_prompt=args.prompt or "",
        context_mode=mode,
        ai_profile=ai_profile,
        task_profile=task,
        compression=compression,
        pack_profile=pack,
        focus_query=focus or "",
        locked_fields=tuple(dict.fromkeys(locked)),
        redact_secrets=redact,
        redact_allow=tuple(cfg.redact_allow),
        redact_entropy=True if cfg.redact_entropy is None else cfg.redact_entropy,
        dry_run=bool(args.dry_run),
        base_ref=base,
        output_format=output_format,
        output=output,
        copy=bool(args.copy or cfg.copy),
        max_tokens=max_tokens,
        max_files=args.max_files if args.max_files is not None else cfg.max_files,
        to_stdout=to_stdout,
        ask=args.ask or "",
        provider=args.provider or "",
        api_key=args.api_key or "",
        model=args.model or "",
        warnings=tuple(warnings),
    )


def _check_git_base(project: Path, base_ref: str | None) -> None:
    if not base_ref:
        return
    state = git_state(project)
    if state == "missing-git":
        raise GitError(
            "Git is not installed, so --base cannot be compared. Install git, or omit --base."
        )
    if state == "not-repo":
        raise GitError(
            f"{project} is not a git repository, so there is no branch to compare against '{base_ref}'."
        )
    if not git_ref_exists(project, base_ref):
        raise GitRefError(base_ref)


def _status_writer(to_stdout: bool):
    """Progress and status lines. Always styled for the stream they go to.

    When the pack itself goes to stdout, status goes to stderr so stdout stays
    only the pack. Color is applied only when that stream is a TTY.
    """
    stream = sys.stderr if to_stdout else sys.stdout

    def status(text: str, tag: str = "") -> None:
        text = format_log_line(text, tag, stream) if tag else text
        data = text if text.endswith("\n") else text + "\n"
        buffer = getattr(stream, "buffer", None)
        encoding = getattr(stream, "encoding", None) or "utf-8"
        if buffer is not None:
            try:
                stream.flush()
            except Exception:
                pass
            buffer.write(data.encode(encoding, errors="replace"))
            buffer.flush()
        else:
            stream.write(data)

    return status


def _write_pack(text: str, plan: RunPlan, status) -> None:
    if plan.to_stdout:
        buffer = getattr(sys.stdout, "buffer", None)
        payload = text.encode("utf-8")
        if buffer is not None:
            buffer.write(payload)
            buffer.flush()
        else:
            sys.stdout.write(text)
        return

    if plan.output and plan.output != "-":
        output_path = Path(plan.output).expanduser()
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
    else:
        suffix = ".json" if plan.output_format == "json" else ".md"
        output_path = get_desktop() / f"contexta - {safe_project_name(plan.project.name)}{suffix}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    status(format_saved(str(output_path), sys.stdout))


def _render_with_budget(plan: RunPlan, status) -> tuple[str, dict]:
    locked = list(plan.locked_fields)
    compression = plan.compression
    text = ""
    stats: dict = {}
    for _ in range(len(("full", "balanced", "focused", "signatures", "lean"))):
        stats = {}
        text = export_pack(
            plan.project,
            output_format=plan.output_format,
            stats=stats,
            include_hidden=plan.include_hidden,
            include_unknown=plan.include_unknown,
            diff_mode=plan.diff_mode,
            staged_only=plan.staged_only,
            system_prompt=plan.system_prompt,
            context_mode=plan.context_mode,
            ai_profile=plan.ai_profile,
            task_profile=plan.task_profile,
            compression=compression,
            pack_profile=plan.pack_profile,
            focus_query=plan.focus_query,
            redact_secrets=plan.redact_secrets,
            redact_allow=plan.redact_allow,
            redact_entropy=plan.redact_entropy,
            base_ref=plan.base_ref,
            max_files=plan.max_files,
            token_budget=plan.max_tokens,
            locked_fields=tuple(locked),
            log_cb=lambda msg, tag="": status(msg, tag or "info"),
        )
        tokens = int(stats.get("tokens") or 0)
        budget_report = stats.get("budget_report") or {}
        if budget_report and not (plan.max_tokens and tokens > plan.max_tokens and next_compression(compression)):
            status(
                f"Budget {plan.max_tokens}: kept {budget_report.get('kept')} of {budget_report.get('candidates')} "
                f"file(s), left out {budget_report.get('dropped')}. Pack is ~{tokens / 1000:.1f}k tokens."
            )
        resolved = str(stats.get("compression") or compression)
        nxt = next_compression(resolved)
        if plan.max_tokens and tokens > plan.max_tokens and nxt:
            status(
                f"Pack is ~{tokens / 1000:.1f}k tokens, still above budget {plan.max_tokens} after dropping files. "
                f"Retrying with --compression {nxt}."
            )
            compression = nxt
            if "compression" not in locked:
                locked.append("compression")
            continue
        if plan.max_tokens and tokens > plan.max_tokens:
            status(
                f"Pack is still ~{tokens / 1000:.1f}k tokens at compression {resolved}, "
                f"above budget {plan.max_tokens}. The fixed sections alone may not fit; raise --budget."
            )
        elif not plan.max_tokens and any(row.get("status") == "over" for row in stats.get("budgets") or []):
            if nxt:
                status(
                    f"Tighten the pack with --compression {nxt}, "
                    "or pass --budget N to fit automatically."
                )
            else:
                status("The lean pack is still over this profile. Narrow it with --focus or a smaller directory.")
        break
    return text, stats


def _send_ask(plan: RunPlan, markdown: str, status) -> None:
    from contexta_app.ai_client import (
        AIConfig,
        DEFAULT_MODELS,
        PROVIDER_LABELS,
        get_available_providers,
        resolve_api_key,
        send_to_ai,
    )

    provider = plan.provider
    if not provider:
        provider = AIConfig.load().provider
    if not provider:
        available = get_available_providers()
        if available:
            provider = available[0]
        else:
            raise ValueError(
                "No AI provider configured. Use --provider, --configure-ai, "
                "or install an SDK (pip install anthropic / google-genai / openai)."
            )

    available = get_available_providers()
    if provider not in available:
        pkg = {"claude": "anthropic", "gemini": "google-genai", "openai": "openai"}[provider]
        raise ValueError(f"SDK for '{provider}' is not installed. Run: pip install {pkg}")

    api_key = resolve_api_key(provider, plan.api_key)
    if not api_key:
        env_var = {"claude": "ANTHROPIC_API_KEY", "gemini": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY"}[provider]
        raise ValueError(
            f"No API key found for '{provider}'. Provide --api-key, set {env_var}, or run --configure-ai."
        )

    model = plan.model
    if not model:
        cfg = AIConfig.load()
        model = cfg.model if cfg.provider == provider and cfg.model else DEFAULT_MODELS.get(provider, "")

    label = PROVIDER_LABELS.get(provider, provider)
    status(f"\nSending to {label} ({model})...")
    try:
        response = send_to_ai(markdown, plan.ask, provider, api_key, model)
    except Exception as exc:
        raise ValueError(f"Error from {label}: {exc}") from exc
    status(format_ai_header(label))
    status(response)


def _dry_run(plan: RunPlan, status) -> None:
    """Report what redaction would change. Values are never printed."""
    stats: dict = {}
    export_pack(
        plan.project,
        stats=stats,
        include_hidden=plan.include_hidden,
        include_unknown=plan.include_unknown,
        diff_mode=plan.diff_mode,
        staged_only=plan.staged_only,
        system_prompt=plan.system_prompt,
        context_mode=plan.context_mode,
        ai_profile=plan.ai_profile,
        task_profile=plan.task_profile,
        compression=plan.compression,
        pack_profile=plan.pack_profile,
        focus_query=plan.focus_query,
        redact_secrets=plan.redact_secrets,
        redact_allow=plan.redact_allow,
        redact_entropy=plan.redact_entropy,
        base_ref=plan.base_ref,
        max_files=plan.max_files,
        locked_fields=tuple(plan.locked_fields),
        dry_run=True,
        log_cb=lambda msg, tag="": status(msg, tag or "info"),
    )
    findings = stats.get("findings") or []
    files = sorted({row["file"] for row in findings})
    if plan.output_format == "json":
        text = json.dumps(
            {"format": "contexta.dry-run.v1", "files_checked": stats.get("files_checked", 0),
             "redaction_enabled": plan.redact_secrets, "findings": findings},
            indent=2,
        ) + "\n"
        sys.stdout.write(text)
        return
    verb = "would be redacted" if plan.redact_secrets else "would NOT be redacted (--no-redact is on)"
    lines = [f"Dry run: {len(findings)} possible secret(s) in {len(files)} of {stats.get('files_checked', 0)} file(s) {verb}."]
    for row in findings:
        name = f" ({row['name']})" if row["name"] else ""
        lines.append(f"  {row['file']}:{row['line']}  {row['rule']}{name}")
    if not findings:
        lines.append("  Nothing to redact.")
    lines.append("No pack was written. Values are never shown here.")
    lines.append("To keep a value, add it to redact_allow in contexta.toml or put 'contexta:allow' on its line.")
    sys.stdout.write("\n".join(lines) + "\n")


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def run_cli() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.configure_ai:
        from contexta_app.ai_client import configure_interactive

        configure_interactive()
        return

    if args.init:
        if args.project:
            try:
                target = validate_project(args.project)
            except ProjectPathError as exc:
                _fail(str(exc))
        else:
            target = Path.cwd()
        created = write_starter_files(target)
        if created:
            print(f"Created {', '.join(created)} in {target}")
            print("Edit contexta.toml, then run: contexta .")
        else:
            print(f"Already configured. Left existing files in place in {target}")
        return

    if args.project is None:
        parser.error(
            "pass a project directory\n"
            "example: contexta . --pack onboarding\n"
            "         contexta --init"
        )

    try:
        project = validate_project(args.project)
        plan = build_plan(args, project, stdout_isatty=sys.stdout.isatty())
        _check_git_base(project, plan.base_ref)
    except (ProjectPathError, ConfigError, GitError) as exc:
        _fail(str(exc))

    status = _status_writer(plan.to_stdout)
    banner_stream = sys.stderr if plan.to_stdout else sys.stdout
    banner = format_banner(__version__, project.name, plan.pack_profile, banner_stream)
    if banner:
        banner_stream.write(banner + "\n")
    for warning in plan.warnings:
        status(f"Warning: {warning}", "warn")

    if plan.dry_run:
        try:
            _dry_run(plan, status)
        except (ConfigError, GitError, ValueError) as exc:
            _fail(str(exc))
        return

    try:
        text, stats = _render_with_budget(plan, status)
    except (ConfigError, GitError, ValueError) as exc:
        _fail(str(exc))

    _write_pack(text, plan, status)
    profile = str(stats.get("ai_profile") or plan.ai_profile)
    tokens = int(stats.get("tokens") or 0)
    status(format_budget_report(tokens, profile))

    if plan.copy:
        copy_to_clipboard(text, status=status)

    if plan.ask:
        try:
            _send_ask(plan, str(stats.get("markdown") or text), status)
        except ValueError as exc:
            _fail(str(exc))


if __name__ == "__main__":
    run_cli()

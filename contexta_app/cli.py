"""
cli.py - Command-line interface for Contexta.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from contexta_app.context_engine import (
    AI_PROFILE_OPTIONS,
    COMPRESSION_OPTIONS,
    CONTEXT_MODE_OPTIONS,
    PACK_OPTIONS,
    TASK_PROFILE_OPTIONS,
)
from contexta_app.renderer import __version__, generate_markdown
from contexta_app.utils import get_desktop, safe_project_name


def copy_to_clipboard(text: str) -> None:
    try:
        if sys.platform == "win32":
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-16"))
        elif sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)
        print("Copied to clipboard.")
    except Exception as exc:
        print(f"Could not copy to clipboard: {exc}")


def safe_print(text: str) -> None:
    stream = getattr(sys.stdout, "buffer", None)
    encoding = sys.stdout.encoding or "utf-8"
    if stream is not None:
        stream.write((text + "\n").encode(encoding, errors="replace"))
    else:
        print(text.encode(encoding, errors="replace").decode(encoding))


def run_cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="contexta",
        description="Generate a curated project context pack from a codebase.",
    )
    parser.add_argument("project", help="Path to the project folder")
    parser.add_argument("-o", "--output", help="Output .md file path")
    parser.add_argument("--hidden", action="store_true", help="Include hidden folders/files")
    parser.add_argument("--unknown", action="store_true", help="Include files with unrecognised extensions")
    parser.add_argument("--diff", action="store_true", help="Prefer git diff context")
    parser.add_argument("--staged", action="store_true", help="Limit git diff detection to staged changes")
    parser.add_argument("-p", "--prompt", default="", help="Custom instruction for the AI")
    parser.add_argument("--focus", default="", help="Feature, bug, or topic to prioritize")
    parser.add_argument("--mode", choices=sorted(CONTEXT_MODE_OPTIONS), default="full", help="Context selection mode")
    parser.add_argument("--ai", choices=sorted(AI_PROFILE_OPTIONS), default="generic", help="Target AI profile")
    parser.add_argument("--task", choices=sorted(TASK_PROFILE_OPTIONS), default="general", help="Task-oriented export profile")
    parser.add_argument("--compression", choices=sorted(COMPRESSION_OPTIONS), default="balanced", help="Context compression strategy")
    parser.add_argument("--pack", choices=sorted(PACK_OPTIONS), default="custom", help="Preset context pack")
    parser.add_argument("-c", "--copy", action="store_true", help="Copy output to clipboard after saving")
    parser.add_argument("--version", action="version", version=f"Contexta {__version__}")
    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    if not project_path.is_dir():
        print(f"'{project_path}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    markdown = generate_markdown(
        project_path,
        include_hidden=args.hidden,
        include_unknown=args.unknown,
        diff_mode=args.diff or args.staged,
        staged_only=args.staged,
        system_prompt=args.prompt,
        context_mode=args.mode,
        ai_profile=args.ai,
        task_profile=args.task,
        compression=args.compression,
        pack_profile=args.pack,
        focus_query=args.focus,
        log_cb=lambda msg, tag="": safe_print(msg),
    )

    safe_name = safe_project_name(project_path.name)
    default_name = f"contexta - {safe_name}.md"
    output_path = Path(args.output) if args.output else (get_desktop() / default_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    safe_print(f"\nSaved: {output_path}")

    if args.copy:
        copy_to_clipboard(markdown)

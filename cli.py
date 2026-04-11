"""
cli.py — Command-line interface for mdcodebrief.
"""

import subprocess
import sys
from pathlib import Path

from renderer import __version__, generate_markdown
from utils import get_desktop, safe_project_name


def copy_to_clipboard(text: str) -> None:
    try:
        if sys.platform == "win32":
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-16"))
        elif sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"],
                           input=text.encode("utf-8"), check=True)
        print("📋  Copied to clipboard!")
    except Exception as e:
        print(f"⚠  Could not copy to clipboard: {e}")


def run_cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="mdcodebrief",
        description="Generate a structured Markdown context file from a project folder.",
    )
    parser.add_argument("project",
                        help="Path to the project folder")
    parser.add_argument("-o", "--output",
                        help="Output .md file path (default: Desktop/resume - <name>.md)")
    parser.add_argument("--hidden",  action="store_true",
                        help="Include hidden folders/files")
    parser.add_argument("--unknown", action="store_true",
                        help="Include files with unrecognised extensions")
    parser.add_argument("--diff",    action="store_true",
                        help="Git diff mode — only changed files")
    parser.add_argument("--staged",  action="store_true",
                        help="Staged files only (git diff --cached)")
    parser.add_argument("-p", "--prompt", default="",
                        help="Inject an AI instruction at the top of the output")
    parser.add_argument("-c", "--copy",   action="store_true",
                        help="Copy output to clipboard after saving")
    parser.add_argument("--version", action="version",
                        version=f"mdcodebrief {__version__}")
    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    if not project_path.is_dir():
        print(f"❌  '{project_path}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    md = generate_markdown(
        project_path,
        include_hidden=args.hidden,
        include_unknown=args.unknown,
        diff_mode=args.diff or args.staged,
        staged_only=args.staged,
        system_prompt=args.prompt,
        log_cb=lambda msg, tag="": print(msg),
    )

    safe = safe_project_name(project_path.name)
    out = Path(args.output) if args.output else (get_desktop() / f"resume - {safe}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"\n✅  Saved: {out}")

    if args.copy:
        copy_to_clipboard(md)

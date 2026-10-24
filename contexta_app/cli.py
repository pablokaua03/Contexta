"""
cli.py - Command-line interface for Contexta.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from contexta_app.cli_style import format_ai_header, format_banner, format_log_line, format_saved, paint
from contexta_app.context_engine import (
    AI_PROFILE_OPTIONS,
    COMPRESSION_OPTIONS,
    CONTEXT_MODE_OPTIONS,
    PACK_OPTIONS,
    TASK_PROFILE_OPTIONS,
)
from contexta_app.renderer import __version__, generate_markdown
from contexta_app.utils import get_desktop, safe_project_name


def _emit(text: str, stream=None) -> None:
    if not text:
        return
    target = sys.stdout if stream is None else stream
    print(text, file=target)


def copy_to_clipboard(text: str) -> None:
    try:
        if sys.platform == "win32":
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-16"))
        elif sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)
        _emit(paint("Copied to clipboard.", "ok"))
    except Exception as exc:
        _emit(paint(f"Could not copy to clipboard: {exc}", "err", sys.stderr), sys.stderr)


def safe_print(text: str) -> None:
    stream = getattr(sys.stdout, "buffer", None)
    encoding = sys.stdout.encoding or "utf-8"
    try:
        sys.stdout.flush()
    except Exception:
        pass
    if stream is not None:
        stream.write((text + "\n").encode(encoding, errors="replace"))
        try:
            stream.flush()
        except Exception:
            pass
    else:
        print(text.encode(encoding, errors="replace").decode(encoding))


def run_cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="contexta",
        description="Generate a curated project context pack from a codebase.",
    )
    parser.add_argument("project", nargs="?", default=None, help="Path to the project folder")
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

    # AI API integration
    parser.add_argument("--ask", default="", help="Send context pack + this prompt to an AI API and print the response")
    parser.add_argument("--provider", choices=["claude", "gemini", "openai"], default="", help="AI provider (claude, gemini, openai)")
    parser.add_argument("--api-key", default="", help="API key (overrides env var and saved config)")
    parser.add_argument("--model", default="", help="Override the default model for the chosen provider")
    parser.add_argument("--configure-ai", action="store_true", help="Interactive setup: save AI provider, API key, and model to ~/.contexta/ai_config.json")

    args = parser.parse_args()

    # Handle --configure-ai (no project required)
    if args.configure_ai:
        from contexta_app.ai_client import configure_interactive

        configure_interactive()
        return

    # project is required for all other operations
    if args.project is None:
        parser.error("the following arguments are required: project")

    project_path = Path(args.project).resolve()
    if not project_path.is_dir():
        _emit(paint(f"'{project_path}' is not a valid directory.", "err", sys.stderr), sys.stderr)
        sys.exit(1)

    _emit(format_banner(__version__, project_path.name, args.pack))

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
        log_cb=lambda msg, tag="": safe_print(format_log_line(msg, tag)),
    )

    safe_name = safe_project_name(project_path.name)
    default_name = f"contexta - {safe_name}.md"
    output_path = Path(args.output) if args.output else (get_desktop() / default_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    safe_print(format_saved(str(output_path)))

    if args.copy:
        copy_to_clipboard(markdown)

    # AI API: send context pack + prompt if --ask was provided
    if args.ask:
        from contexta_app.ai_client import (
            AIConfig,
            DEFAULT_MODELS,
            PROVIDER_LABELS,
            get_available_providers,
            resolve_api_key,
            send_to_ai,
        )

        # Determine provider: explicit flag > saved config
        provider = args.provider
        if not provider:
            cfg = AIConfig.load()
            provider = cfg.provider
        if not provider:
            available = get_available_providers()
            if available:
                provider = available[0]
            else:
                _emit(
                    paint(
                        "\nError: No AI provider configured. Use --provider, --configure-ai, "
                        "or install an SDK (pip install anthropic / google-genai / openai).",
                        "err",
                        sys.stderr,
                    ),
                    sys.stderr,
                )
                sys.exit(1)

        # Check SDK availability
        available = get_available_providers()
        if provider not in available:
            pkg = {"claude": "anthropic", "gemini": "google-genai", "openai": "openai"}[provider]
            _emit(
                paint(
                    f"\nError: SDK for '{provider}' is not installed. Run: pip install {pkg}",
                    "err",
                    sys.stderr,
                ),
                sys.stderr,
            )
            sys.exit(1)

        # Resolve API key
        api_key = resolve_api_key(provider, args.api_key)
        if not api_key:
            env_var = {"claude": "ANTHROPIC_API_KEY", "gemini": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY"}[provider]
            _emit(
                paint(
                    f"\nError: No API key found for '{provider}'. Provide via --api-key, "
                    f"env var {env_var}, or run --configure-ai.",
                    "err",
                    sys.stderr,
                ),
                sys.stderr,
            )
            sys.exit(1)

        # Resolve model
        model = args.model
        if not model:
            cfg = AIConfig.load()
            if cfg.provider == provider and cfg.model:
                model = cfg.model
            else:
                model = DEFAULT_MODELS.get(provider, "")

        label = PROVIDER_LABELS.get(provider, provider)
        safe_print(paint(f"\nSending to {label} ({model})..."))

        try:
            response = send_to_ai(markdown, args.ask, provider, api_key, model)
            safe_print(format_ai_header(label))
            safe_print(response)
        except Exception as exc:
            _emit(paint(f"\nError from {label}: {exc}", "err", sys.stderr), sys.stderr)
            sys.exit(1)

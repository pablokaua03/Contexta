"""Tests for daily handoff: redaction, budgets, config, ignore rules, and CLI."""

import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contexta_app.budgets import budget_summary, evaluate_budgets, fit_status, next_compression
from contexta_app.cli import (
    ProjectPathError,
    build_parser,
    build_plan,
    copy_to_clipboard,
    run_cli,
    validate_project,
)
from contexta_app.config import ConfigError, load_effective_config, load_project_config, write_starter_files
from contexta_app.context_engine import ExportConfig, resolve_config
from contexta_app.redaction import REDACTED, redact_secrets
from contexta_app.renderer import __version__, export_pack, generate_markdown
from contexta_app.scanner import (
    GitRefError,
    build_tree,
    get_git_changed_files,
    load_gitignore_patterns,
    matches_gitignore,
)

TEST_TMP_ROOT = Path(__file__).parent / ".tmp"
TEST_TMP_ROOT.mkdir(exist_ok=True)


class AdoptionTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=TEST_TMP_ROOT))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self._env = patch.dict(os.environ, {"CONTEXTA_HOME": str(self.home)}, clear=False)
        self._env.start()

    def tearDown(self):
        self._env.stop()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, *args: str, cwd: Path | None = None) -> None:
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "Contexta Test"
        env["GIT_AUTHOR_EMAIL"] = "dev@example.com"
        env["GIT_COMMITTER_NAME"] = "Contexta Test"
        env["GIT_COMMITTER_EMAIL"] = "dev@example.com"
        subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.tmp),
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )


class TestRedaction(AdoptionTestCase):
    def test_known_tokens_and_private_keys_are_removed(self):
        source = "\n".join([
            "openai = 'sk-proj-abcdefghijklmnopqrstuvwxyz123456'",
            "anthropic = 'sk-ant-api03-abcdefghijklmnopqrstuvwxyz'",
            "github = 'ghp_abcdefghijklmnopqrstuvwxyz123456'",
            "aws = 'AKIAIOSFODNN7EXAMPLE'",
            "-----BEGIN RSA PRIVATE KEY-----",
            "MIIBogIBAAJBALFakeKeyMaterial1234567890",
            "-----END RSA PRIVATE KEY-----",
        ])
        redacted, count = redact_secrets(source)
        self.assertGreaterEqual(count, 5)
        for secret in ("sk-proj-abc", "sk-ant-api03", "ghp_abc", "AKIAIOSFODNN7EXAMPLE", "BEGIN RSA PRIVATE KEY"):
            self.assertNotIn(secret, redacted)
        self.assertIn(REDACTED, redacted)

    def test_assignment_and_url_passwords_are_removed(self):
        source = "\n".join([
            'API_KEY = "correcthorsebatterystaple"',
            "GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456",
            "DATABASE_URL=postgres://app:supersecret@db.internal:5432/app",
            'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U',
        ])
        redacted, count = redact_secrets(source)
        self.assertGreaterEqual(count, 4)
        self.assertNotIn("correcthorsebatterystaple", redacted)
        self.assertNotIn("supersecret", redacted)
        self.assertNotIn("ghp_abc", redacted)
        self.assertIn("postgres://app:[REDACTED]@db.internal:5432/app", redacted)

    def test_ordinary_code_and_placeholders_stay(self):
        source = "\n".join([
            "export default function RegisterPage() { return <form><input name='password' /></form>; }",
            'API_KEY = "your-api-key"',
            'password = "example"',
            'token = os.environ["APP_TOKEN"]',
            "def get_password():",
            "    return load_secret()",
            "print('hello')",
            "TOKEN_COUNT = 128000",
        ])
        redacted, count = redact_secrets(source)
        self.assertEqual(count, 0)
        self.assertEqual(redacted, source)

    def test_disabled_path_is_identity(self):
        source = 'API_KEY = "correcthorsebatterystaple"'
        self.assertEqual(redact_secrets(source)[0] != source, True)


class TestBudgets(unittest.TestCase):
    def test_fit_boundaries_for_a_128k_window(self):
        window = 128_000
        usable = int(window * 0.8)
        self.assertEqual(fit_status(usable, window), "fits")
        self.assertEqual(fit_status(usable + 1, window), "tight")
        self.assertEqual(fit_status(window, window), "tight")
        self.assertEqual(fit_status(window + 1, window), "over")

    def test_profile_report_names_the_models_a_dev_actually_picks(self):
        rows = {row.name: row.status for row in evaluate_budgets(150_000, "chatgpt")}
        self.assertEqual(rows["GPT-4o"], "over")
        self.assertEqual(rows["GPT-4.1"], "fits")
        claude = {row.name: row.status for row in evaluate_budgets(150_000, "claude")}
        self.assertEqual(claude["Claude Sonnet"], "fits")
        summary = budget_summary(150_000, "chatgpt")
        self.assertIn("over GPT-4o", summary)
        self.assertIn("fits GPT-4.1", summary)

    def test_compression_ladder_stops_at_lean(self):
        self.assertEqual(next_compression("full"), "balanced")
        self.assertEqual(next_compression("signatures"), "lean")
        self.assertIsNone(next_compression("lean"))


class TestConfigAndIgnore(AdoptionTestCase):
    def test_project_config_overrides_user_defaults(self):
        (self.home / "config.toml").write_text('ai = "gemini"\ncompression = "lean"\n', encoding="utf-8")
        (self.tmp / "contexta.toml").write_text('ai = "claude"\npack = "bugfix"\n', encoding="utf-8")
        cfg = load_effective_config(self.tmp)
        self.assertEqual(cfg.ai, "claude")
        self.assertEqual(cfg.compression, "lean")
        self.assertEqual(cfg.pack, "bugfix")

    def test_invalid_pack_names_the_choices(self):
        (self.tmp / "contexta.toml").write_text('pack = "nope"\n', encoding="utf-8")
        with self.assertRaises(ConfigError) as caught:
            load_project_config(self.tmp)
        self.assertIn("nope", str(caught.exception))
        self.assertIn("bugfix", str(caught.exception))

    def test_broken_toml_points_at_init(self):
        (self.tmp / "contexta.toml").write_text("pack = [\n", encoding="utf-8")
        with self.assertRaises(ConfigError) as caught:
            load_gitignore_patterns(self.tmp)
        self.assertIn("contexta --init", str(caught.exception))

    def test_contextaignore_and_config_ignore_hide_files(self):
        (self.tmp / "keep.py").write_text("print('keep')\n", encoding="utf-8")
        (self.tmp / "skip.py").write_text("print('skip-me')\n", encoding="utf-8")
        (self.tmp / "also.py").write_text("print('also-skip')\n", encoding="utf-8")
        (self.tmp / ".contextaignore").write_text("skip.py\n", encoding="utf-8")
        (self.tmp / "contexta.toml").write_text('ignore = ["also.py"]\n', encoding="utf-8")

        patterns = load_gitignore_patterns(self.tmp)
        self.assertTrue(matches_gitignore(self.tmp / "skip.py", self.tmp, patterns))
        self.assertTrue(matches_gitignore(self.tmp / "also.py", self.tmp, patterns))
        self.assertFalse(matches_gitignore(self.tmp / "keep.py", self.tmp, patterns))

        tree = build_tree(self.tmp, False, False, lambda *_a, **_k: None, [0], patterns, self.tmp)
        names = [item["name"] for item in tree["files"]]
        self.assertIn("keep.py", names)
        self.assertNotIn("skip.py", names)
        self.assertNotIn("also.py", names)

    def test_init_does_not_overwrite(self):
        first = write_starter_files(self.tmp)
        self.assertIn("contexta.toml", first)
        self.assertIn(".contextaignore", first)
        (self.tmp / "contexta.toml").write_text('pack = "debug"\n', encoding="utf-8")
        second = write_starter_files(self.tmp)
        self.assertEqual(second, [])
        self.assertIn('pack = "debug"', (self.tmp / "contexta.toml").read_text(encoding="utf-8"))

    def test_locked_compression_survives_pack_defaults(self):
        resolved = resolve_config(
            ExportConfig(pack_profile="pr_review", compression="lean", locked_fields=("compression",))
        )
        self.assertEqual(resolved.compression, "lean")
        self.assertEqual(resolved.context_mode, "diff")
        self.assertEqual(resolved.task_profile, "code_review")


class TestGitBase(AdoptionTestCase):
    def test_base_ref_includes_branch_commits_and_local_work(self):
        self._git("init", "-b", "main")
        (self.tmp / "base.py").write_text("print('base')\n", encoding="utf-8")
        self._git("add", "base.py")
        self._git("commit", "-m", "base")
        self._git("checkout", "-b", "feature")
        (self.tmp / "feature.py").write_text("print('feature')\n", encoding="utf-8")
        self._git("add", "feature.py")
        self._git("commit", "-m", "feature")
        (self.tmp / "base.py").write_text("print('edited')\n", encoding="utf-8")
        (self.tmp / "local.py").write_text("print('local')\n", encoding="utf-8")

        working = {path.name for path in get_git_changed_files(self.tmp) or []}
        self.assertIn("base.py", working)
        self.assertIn("local.py", working)
        self.assertNotIn("feature.py", working)

        compared = {path.name for path in get_git_changed_files(self.tmp, base_ref="main") or []}
        self.assertIn("feature.py", compared)
        self.assertIn("base.py", compared)
        self.assertIn("local.py", compared)

    def test_missing_ref_is_a_clear_error(self):
        self._git("init", "-b", "main")
        (self.tmp / "base.py").write_text("print('base')\n", encoding="utf-8")
        self._git("add", "base.py")
        self._git("commit", "-m", "base")
        with self.assertRaises(GitRefError) as caught:
            get_git_changed_files(self.tmp, base_ref="no-such-branch")
        self.assertIn("no-such-branch", str(caught.exception))
        self.assertIn("origin/main", str(caught.exception))


class TestExport(AdoptionTestCase):
    def test_markdown_redacts_and_reports_budget(self):
        (self.tmp / "settings.py").write_text(
            'API_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"\nprint("hello")\n',
            encoding="utf-8",
        )
        md = generate_markdown(self.tmp, compression="full")
        self.assertNotIn("sk-ant-api03", md)
        self.assertIn(REDACTED, md)
        self.assertIn('print("hello")', md)
        self.assertIn("budget:", md)
        self.assertIn("1 secret redacted", md)
        self.assertIn(__version__, md)

    def test_no_redact_keeps_the_literal(self):
        (self.tmp / "settings.py").write_text(
            'API_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"\n',
            encoding="utf-8",
        )
        md = generate_markdown(self.tmp, compression="full", redact_secrets=False)
        self.assertIn("sk-ant-api03", md)

    def test_json_envelope_omits_the_secret(self):
        (self.tmp / "settings.py").write_text(
            'API_KEY = "ghp_abcdefghijklmnopqrstuvwxyz123456"\n',
            encoding="utf-8",
        )
        payload = export_pack(self.tmp, output_format="json", compression="full")
        self.assertIn('"format": "contexta.pack.v1"', payload)
        self.assertNotIn("ghp_abc", payload)
        self.assertIn("budgets", payload)

    def test_bugfix_pack_still_includes_source_when_nothing_looks_suspicious(self):
        (self.tmp / "app.py").write_text("print('hello')\n", encoding="utf-8")
        md = generate_markdown(self.tmp, pack_profile="bugfix")
        self.assertIn("Bugfix Pack", md)
        self.assertIn("app.py", md)
        self.assertIn("print('hello')", md)

    def test_contextaignore_drops_the_file_from_the_pack(self):
        (self.tmp / "shown.py").write_text("print('shown-marker')\n", encoding="utf-8")
        (self.tmp / "hidden.py").write_text("print('hidden-marker')\n", encoding="utf-8")
        (self.tmp / ".contextaignore").write_text("hidden.py\n", encoding="utf-8")
        md = generate_markdown(self.tmp, compression="full")
        self.assertIn("shown-marker", md)
        self.assertNotIn("hidden-marker", md)


class TestCliPlan(AdoptionTestCase):
    def _args(self, *extra: str):
        return build_parser().parse_args([str(self.tmp), *extra])

    def test_help_shows_daily_commands(self):
        help_text = build_parser().format_help()
        for snippet in ("--base", "--stdout", "--init", "--no-redact", "bugfix", "pr_review", "contexta serve"):
            self.assertIn(snippet, help_text)

    def test_project_path_errors_are_specific(self):
        missing = self.tmp / "missing"
        with self.assertRaises(ProjectPathError) as caught:
            validate_project(str(missing))
        self.assertIn("No such directory", str(caught.exception))
        self.assertIn("contexta .", str(caught.exception))

        source = self.tmp / "app.py"
        source.write_text("x = 1\n", encoding="utf-8")
        with self.assertRaises(ProjectPathError) as caught:
            validate_project(str(source))
        self.assertIn("this path is a file", str(caught.exception))
        self.assertIn(str(source.parent), str(caught.exception))

    def test_config_and_flags_resolve_in_the_right_order(self):
        (self.tmp / "contexta.toml").write_text(
            "\n".join([
                'pack = "bugfix"',
                'compression = "lean"',
                'base = "main"',
                "redact = false",
                "max_tokens = 32000",
            ]),
            encoding="utf-8",
        )
        plan = build_plan(self._args(), self.tmp, stdout_isatty=True)
        self.assertEqual(plan.pack_profile, "bugfix")
        self.assertEqual(plan.compression, "lean")
        self.assertEqual(plan.context_mode, "debug")
        self.assertEqual(plan.ai_profile, "claude")
        self.assertIsNone(plan.base_ref)
        self.assertFalse(plan.redact_secrets)
        self.assertEqual(plan.max_tokens, 32000)

        forced = build_plan(
            self._args("--compression", "signatures", "--redact", "--base", "develop"),
            self.tmp,
            stdout_isatty=True,
        )
        self.assertEqual(forced.compression, "signatures")
        self.assertTrue(forced.redact_secrets)
        self.assertEqual(forced.base_ref, "develop")
        self.assertIn("compression", forced.locked_fields)

    def test_pr_review_uses_configured_base_and_onboarding_does_not(self):
        (self.tmp / "contexta.toml").write_text('base = "main"\npack = "pr_review"\n', encoding="utf-8")
        review = build_plan(self._args(), self.tmp, stdout_isatty=True)
        self.assertEqual(review.base_ref, "main")
        self.assertEqual(review.context_mode, "diff")
        self.assertTrue(review.diff_mode)

        (self.tmp / "contexta.toml").write_text('base = "main"\npack = "onboarding"\n', encoding="utf-8")
        tour = build_plan(self._args(), self.tmp, stdout_isatty=True)
        self.assertIsNone(tour.base_ref)
        self.assertEqual(tour.context_mode, "onboarding")

        explicit = build_plan(self._args("--pack", "onboarding", "--base", "main"), self.tmp, stdout_isatty=True)
        self.assertEqual(explicit.base_ref, "main")
        self.assertEqual(explicit.context_mode, "onboarding")

    def test_pipe_writes_stdout_unless_ask_or_output_is_set(self):
        piped = build_plan(self._args(), self.tmp, stdout_isatty=False)
        self.assertTrue(piped.to_stdout)
        interactive = build_plan(self._args(), self.tmp, stdout_isatty=True)
        self.assertFalse(interactive.to_stdout)
        asked = build_plan(self._args("--ask", "what breaks?"), self.tmp, stdout_isatty=False)
        self.assertFalse(asked.to_stdout)
        chosen = build_plan(self._args("-o", "pack.md"), self.tmp, stdout_isatty=False)
        self.assertFalse(chosen.to_stdout)
        self.assertEqual(chosen.output, "pack.md")

    def test_refactor_pack_selects_refactor_mode(self):
        plan = build_plan(self._args("--pack", "refactor"), self.tmp, stdout_isatty=True)
        self.assertEqual(plan.context_mode, "refactor")
        self.assertEqual(plan.task_profile, "refactor_request")
        self.assertEqual(plan.compression, "focused")

    def test_clipboard_failure_explains_the_next_step(self):
        messages: list[str] = []
        with patch("contexta_app.cli._clipboard_commands", return_value=[["not-a-real-clipboard-bin"]]):
            copied = copy_to_clipboard("hello", status=messages.append)
        self.assertFalse(copied)
        self.assertTrue(any("wl-clipboard" in message or "xclip" in message for message in messages))

    def test_stdout_run_redacts_and_stays_off_the_desktop(self):
        (self.tmp / "app.py").write_text(
            'API_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"\nprint("hello")\n',
            encoding="utf-8",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = ["contexta", str(self.tmp), "--stdout", "--compression", "full", "--max-tokens", "1"]
        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            run_cli()
        pack = stdout.getvalue()
        notes = stderr.getvalue()
        self.assertIn("Contexta", pack)
        self.assertNotIn("sk-ant-api03", pack)
        self.assertNotIn("sk-ant-api03", notes)
        self.assertIn("budget:", pack)
        self.assertIn("Retrying", notes)
        self.assertIn("Context budget", notes)
        self.assertNotIn("Saved:", notes)
        self.assertNotIn("Saved:", pack)


if __name__ == "__main__":
    unittest.main()

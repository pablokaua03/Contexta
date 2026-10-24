"""Security behaviour: redaction, dry-run, credential files, MCP confinement.

Every secret in this file is generated at test time from random characters. None is a real credential.
"""

from __future__ import annotations

import json
import os
import random
import string
import subprocess
import sys
from pathlib import Path

import pytest

from contexta_app import mcp_server
from contexta_app.cli import build_parser, build_plan
from contexta_app.redaction import find_secrets, redact_secrets
from contexta_app.safety import is_sensitive_name, is_sensitive_path

ALNUM = string.ascii_letters + string.digits
RNG = random.Random(1234)


def rnd(n: int, alphabet: str = ALNUM) -> str:
    return "".join(RNG.choice(alphabet) for _ in range(n))


def fake_pack_repo(root: Path) -> dict[str, str]:
    values = {
        "aws": "AKIA" + rnd(16, string.ascii_uppercase + string.digits),
        "github": "ghp_" + rnd(36),
        "stripe": "sk_live_" + rnd(24),
        "dbpass": rnd(14),
        "named": rnd(40, ALNUM + "+/"),
        "json": rnd(18),
        "env": rnd(32),
    }
    (root / "app.py").write_text(
        f'AWS = "{values["aws"]}"\nGH = "{values["github"]}"\nSTRIPE = "{values["stripe"]}"\n'
        f'DB = "postgres://admin:{values["dbpass"]}@db.example.com/app"\n'
        f'api_secret = "{values["named"]}"\n'
        'def main():\n    return 1\n'
    )
    (root / "config.json").write_text(json.dumps({"password": values["json"], "name": "demo"}))
    (root / ".env").write_text(f"TOKEN={values['env']}\n")
    (root / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n" + rnd(200) + "\n-----END OPENSSH PRIVATE KEY-----\n")
    (root / "README.md").write_text("# demo\n\nA demo project for tests.\n")
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1"\ndescription = "Demo project"\n')
    return values


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "NO_COLOR": "1"}
    return subprocess.run(
        [sys.executable, "-m", "contexta_app.cli", *args],
        capture_output=True, text=True, env=env, cwd=Path(__file__).resolve().parent.parent, timeout=120,
    )


class TestRedaction:
    def test_known_formats_and_named_values(self):
        values = {k: v for k, v in fake_pack_repo(Path(self._tmp())).items()}
        text = f'x = "{values["github"]}"\npassword: {values["env"]}1\n{{"password": "{values["json"]}"}}\n'
        out, count = redact_secrets(text)
        assert count == 3
        assert values["github"] not in out and values["json"] not in out

    @staticmethod
    def _tmp() -> str:
        import tempfile

        return tempfile.mkdtemp()

    def test_entropy_catches_unprefixed_secret(self):
        value = rnd(44, ALNUM + "+/")
        out, count = redact_secrets(f'client_blob = "{value}"\n')
        assert count == 1 and value not in out

    def test_entropy_catches_base64_with_slashes(self):
        for _ in range(200):
            value = rnd(40, ALNUM + "+/")
            assert redact_secrets(f'blob = "{value}"\n')[1] == 1, value

    def test_entropy_ignores_paths(self):
        assert redact_secrets('p = "src/contexta_app/context_engine/selector2.py"')[1] == 0
        assert redact_secrets('p = "docs/guides/getting-started/installation2/index"')[1] == 0

    def test_entropy_ignores_ordinary_strings(self):
        samples = [
            'name = "contexta_app.context_engine.build_analysis"',
            'url = "https://example.com/some/long/path/segment/here"',
            'sha = "da39a3ee5e6b4b0d3255bfef95601890afd80709"',
            'uid = "123e4567-e89b-12d3-a456-426614174000"',
            'ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"',
            'label = "this is a normal sentence with words"',
        ]
        for line in samples:
            assert redact_secrets(line)[1] == 0, line

    def test_entropy_can_be_turned_off(self):
        value = rnd(44, ALNUM + "+/")
        assert redact_secrets(f'blob = "{value}"', entropy=False)[1] == 0

    def test_allowlist_literal_and_marker(self):
        public = "pk_test_" + rnd(24)
        assert redact_secrets(f'KEY = "{public}"\n', allow=(public,))[1] == 0
        assert redact_secrets(f'KEY = "{public}"  # contexta:allow\n')[1] == 0
        assert redact_secrets(f'KEY = "ghp_{rnd(36)}"  # pragma: allowlist secret\n')[1] == 0

    def test_findings_carry_line_and_rule_but_never_the_value(self):
        token = "ghp_" + rnd(36)
        found = find_secrets(f"a = 1\nb = '{token}'\n")
        assert [f.line for f in found] == [2]
        assert token not in repr(found)

    def test_placeholders_stay(self):
        assert redact_secrets('API_KEY = "changeme"\npassword = "${PASSWORD}"\ntoken: Optional\n')[1] == 0


class TestCredentialFiles:
    @pytest.mark.parametrize("name", [".env", ".env.production", "id_rsa", "id_ed25519", "server.pem", "credentials.json", ".npmrc", ".netrc"])
    def test_sensitive_names(self, name):
        assert is_sensitive_name(name)

    @pytest.mark.parametrize("name", [".env.example", ".env.sample", "README.md", "app.py", "keyboard.py"])
    def test_safe_names(self, name):
        assert not is_sensitive_name(name)

    def test_sensitive_directory(self):
        assert is_sensitive_path(Path(".aws/config"))
        assert is_sensitive_path(Path("deploy/.ssh/id_rsa"))

    def test_pack_never_contains_env_or_key_files(self, tmp_path):
        values = fake_pack_repo(tmp_path)
        result = run_cli(str(tmp_path), "--stdout")
        assert result.returncode == 0, result.stderr
        assert values["env"] not in result.stdout
        assert "BEGIN OPENSSH" not in result.stdout
        for key in ("aws", "github", "stripe", "dbpass", "named", "json"):
            assert values[key] not in result.stdout, key
        assert "[REDACTED]" in result.stdout


class TestDryRun:
    def test_lists_findings_without_values(self, tmp_path):
        values = fake_pack_repo(tmp_path)
        result = run_cli(str(tmp_path), "--dry-run")
        assert result.returncode == 0, result.stderr
        assert "app.py:" in result.stdout and "config.json:" in result.stdout
        assert "No pack was written" in result.stdout
        for value in values.values():
            assert value not in result.stdout + result.stderr

    def test_json_output(self, tmp_path):
        fake_pack_repo(tmp_path)
        result = run_cli(str(tmp_path), "--dry-run", "--format", "json")
        data = json.loads(result.stdout)
        assert data["format"] == "contexta.dry-run.v1"
        assert {row["file"] for row in data["findings"]} >= {"app.py", "config.json"}
        assert all(set(row) == {"file", "line", "rule", "name"} for row in data["findings"])

    def test_writes_no_pack(self, tmp_path):
        fake_pack_repo(tmp_path)
        out = tmp_path / "pack.md"
        run_cli(str(tmp_path), "--dry-run", "-o", str(out))
        assert not out.exists()

    def test_respects_allowlist_from_config(self, tmp_path):
        (tmp_path / "app.py").write_text('KEY = "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"\n')
        (tmp_path / "contexta.toml").write_text('redact_allow = ["ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"]\n')
        result = run_cli(str(tmp_path), "--dry-run")
        assert "Nothing to redact" in result.stdout


class TestRedactFlag:
    def parse(self, *argv):
        return build_parser().parse_args(["."] + list(argv))

    def test_default_is_unset_and_plan_redacts(self, tmp_path):
        args = self.parse()
        assert args.redact is None

    def test_flags_are_tri_state(self):
        assert self.parse("--redact").redact is True
        assert self.parse("--no-redact").redact is False

    def test_conflict_is_an_error(self):
        with pytest.raises(SystemExit):
            self.parse("--redact", "--no-redact")
        with pytest.raises(SystemExit):
            self.parse("--no-redact", "--redact")

    def test_plan_defaults_to_redaction(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        args = build_parser().parse_args([str(tmp_path)])
        assert build_plan(args, tmp_path, stdout_isatty=False).redact_secrets is True


class TestMcpConfinement:
    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch):
        monkeypatch.delenv("CONTEXTA_ROOT", raising=False)
        yield
        mcp_server.configure_roots(None)

    def test_default_root_is_working_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert mcp_server.allowed_roots() == [tmp_path.resolve()]

    def test_project_outside_root_is_refused(self, tmp_path):
        inside = tmp_path / "ok"
        outside = tmp_path / "other"
        inside.mkdir(); outside.mkdir()
        mcp_server.configure_roots([inside])
        assert mcp_server.resolve_project(str(inside))[0] == inside.resolve()
        path, error = mcp_server.resolve_project(str(outside))
        assert path is None and "outside" in error

    def test_subfolder_allowed_and_dotdot_escape_refused(self, tmp_path):
        root = tmp_path / "root"; (root / "sub").mkdir(parents=True)
        mcp_server.configure_roots([root])
        assert mcp_server.resolve_project(str(root / "sub"))[0] is not None
        assert mcp_server.resolve_project(str(root / "sub" / ".." / ".."))[0] is None

    def test_env_var_roots(self, tmp_path, monkeypatch):
        a = tmp_path / "a"; b = tmp_path / "b"; a.mkdir(); b.mkdir()
        monkeypatch.setenv("CONTEXTA_ROOT", os.pathsep.join([str(a), str(b)]))
        assert {p.name for p in mcp_server.allowed_roots()} == {"a", "b"}

    def test_read_files_refuses_escapes_and_credentials(self, tmp_path):
        project = tmp_path / "proj"; project.mkdir()
        (project / "ok.py").write_text("x = 1\n")
        (project / ".env").write_text("TOKEN=" + rnd(30) + "\n")
        secret = tmp_path / "outside.txt"; secret.write_text("OUTSIDE-DATA")
        (project / "link.txt").symlink_to(secret)
        mcp_server.configure_roots([project])

        out = mcp_server.read_files(str(project), ["ok.py", "../outside.txt", str(secret), "link.txt", ".env"])
        assert "x = 1" in out
        assert "OUTSIDE-DATA" not in out
        assert "TOKEN=" not in out

    def test_every_tool_refuses_outside_root(self, tmp_path):
        inside = tmp_path / "in"; outside = tmp_path / "out"
        inside.mkdir(); outside.mkdir()
        (outside / "a.py").write_text("x = 1\n")
        mcp_server.configure_roots([inside])
        target = str(outside)
        assert "outside" in mcp_server.scan_project(target)
        assert "outside" in mcp_server.find_files(target, "a")
        assert "outside" in mcp_server.read_files(target, ["a.py"])
        assert "outside" in mcp_server.generate_context(target)

    def test_serve_args(self):
        assert mcp_server.parse_serve_args(["--root", "/a", "--root=/b"]) == ["/a", "/b"]
        with pytest.raises(SystemExit):
            mcp_server.parse_serve_args(["--root"])
        with pytest.raises(SystemExit):
            mcp_server.parse_serve_args(["--bogus"])


class TestScannerSymlinks:
    def test_symlink_pointing_outside_is_not_scanned(self, tmp_path):
        outside = tmp_path / "outside"; outside.mkdir()
        (outside / "leak.py").write_text("LEAK = 1\n")
        project = tmp_path / "proj"; project.mkdir()
        (project / "main.py").write_text("x = 1\n")
        (project / "escape").symlink_to(outside, target_is_directory=True)
        (project / "leak_link.py").symlink_to(outside / "leak.py")
        result = run_cli(str(project), "--stdout")
        assert "LEAK = 1" not in result.stdout
        assert "leak.py" not in result.stdout

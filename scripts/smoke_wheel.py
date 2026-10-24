"""Build the wheel, install it in a clean virtualenv and run the real entry points.

    python scripts/smoke_wheel.py            # needs network for the dependencies
    python scripts/smoke_wheel.py --wheel dist/contexta_ai-2.2.1-py3-none-any.whl

It catches the class of bug where the wheel installs but `contexta` cannot start because a module
is missing from the package. Exit code 0 means every check passed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import textwrap
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def check(ok: bool, name: str, detail: str = "") -> bool:
    print(("ok   " if ok else "FAIL ") + name + (f"\n{textwrap.indent(detail.strip(), '       ')}" if detail and not ok else ""))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wheel", help="use this wheel instead of building one")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="contexta-smoke-") as tmp_s:
        tmp = Path(tmp_s)
        if args.wheel:
            wheel = Path(args.wheel).resolve()
        else:
            out = tmp / "dist"
            r = run([sys.executable, "-m", "build", "--wheel", "--outdir", str(out), str(ROOT)])
            if r.returncode != 0:
                print(r.stdout, r.stderr)
                return 2
            wheel = next(out.glob("*.whl"))
        print("wheel:", wheel.name)

        env_dir = tmp / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        bindir = env_dir / ("Scripts" if sys.platform == "win32" else "bin")
        py = bindir / ("python.exe" if sys.platform == "win32" else "python")
        exe = bindir / ("contexta.exe" if sys.platform == "win32" else "contexta")
        r = run([str(py), "-m", "pip", "install", "--quiet", str(wheel)])
        if r.returncode != 0:
            print(r.stdout, r.stderr)
            return 2

        proj = tmp / "proj"
        (proj / "src").mkdir(parents=True)
        (proj / "src" / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
        (proj / "README.md").write_text("# demo\n", encoding="utf-8")

        results = []
        r = run([str(exe), "--version"])
        results.append(check(r.returncode == 0 and "Contexta" in r.stdout, "contexta --version", r.stdout + r.stderr))
        r = run([str(py), "-m", "contexta_app", "--version"])
        results.append(check(r.returncode == 0 and "Contexta" in r.stdout, "python -m contexta_app --version", r.stdout + r.stderr))
        r = run([str(exe), str(proj), "--no-memory", "-o", str(tmp / "pack.md")])
        pack = tmp / "pack.md"
        results.append(check(r.returncode == 0 and pack.exists() and "app.py" in pack.read_text(encoding="utf-8"), "contexta <project> writes a pack", r.stdout + r.stderr))
        r = run([str(exe), "serve", "--help"])
        results.append(check(r.returncode == 0 and "serve" in (r.stdout + r.stderr).lower(), "contexta serve --help", r.stdout + r.stderr))

        client = textwrap.dedent(
            f"""
            import asyncio, sys
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            async def main():
                params = StdioServerParameters(command={str(exe)!r}, args=["serve", "--root", {str(proj)!r}])
                async with stdio_client(params) as (r, w):
                    async with ClientSession(r, w) as s:
                        await s.initialize()
                        tools = [t.name for t in (await s.list_tools()).tools]
                        print(len(tools), "tools")
                        assert "repo_map" in tools, tools
            asyncio.run(main())
            """
        )
        r = run([str(py), "-c", client], timeout=120)
        results.append(check(r.returncode == 0, "contexta serve answers over MCP stdio", r.stdout + r.stderr))
        print("PASSED" if all(results) else "FAILED")
        return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

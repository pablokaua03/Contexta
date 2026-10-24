#!/usr/bin/env python3
"""
Contexta vs Repomix vs Gitingest, on pinned commits of flask, requests and fastapi.

    python benchmarks/bench.py --setup          # clone the repos at the pinned commits, install the tools
    python benchmarks/bench.py                  # run, print the table, write benchmarks/results.{json,md}
    python benchmarks/bench.py --repos flask --reps 1

What it measures
  tokens   tiktoken cl100k_base over the whole output file, the same tokenizer for every tool.
  time     wall clock of the whole command, median of --reps runs. For Contexta the first run starts
           with no .contexta/ (cold graph) and the rest reuse it (warm); both are reported.
  recall   a task, and the files a person would need for it. A file counts as found when its path
           and one signature line from it are in the output. Signatures survive compression, so
           compressed and signature-only packs are not punished for dropping bodies.

What it does not measure: whether the extra analysis sections Contexta adds (risk, entry points,
reading order) help a model. Recall says nothing about answer quality. See benchmarks/README.md.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TOOLS = HERE / ".tools"
REPOS = HERE / ".repos"

REPOMIX_VERSION = "1.18.1"
GITINGEST_VERSION = "0.3.1"
WINDOW = 128_000


@dataclass
class Case:
    name: str
    url: str
    commit: str
    package_glob: str  # what a person who knew the repo would point the other tools at
    task: str
    expected: list[tuple[str, str]] = field(default_factory=list)  # (path, a signature line from it)


CASES = [
    Case(
        "flask", "https://github.com/pallets/flask", "d086db856be187255b8ec61ef409357393020f32", "src/flask/**",
        "session cookie signing",
        [
            ("src/flask/sessions.py", "class SecureCookieSessionInterface"),
            ("src/flask/app.py", "session_interface"),
            ("src/flask/ctx.py", "open_session"),
            ("tests/test_session_interface.py", "def test_"),
        ],
    ),
    Case(
        "requests", "https://github.com/psf/requests", "611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60", "src/requests/**",
        "how the HTTP adapter sends a request and follows redirects",
        [
            ("src/requests/adapters.py", "class HTTPAdapter"),
            ("src/requests/sessions.py", "def resolve_redirects"),
            ("src/requests/exceptions.py", "class RetryError"),
            ("tests/test_requests.py", "def test_"),
        ],
    ),
    Case(
        "fastapi", "https://github.com/fastapi/fastapi", "7a0a3f0b286c6c865cf4398ea0e957a87b8bffa4", "fastapi/**",
        "dependency injection solving",
        [
            ("fastapi/dependencies/utils.py", "def solve_dependencies"),
            ("fastapi/routing.py", "def get_request_handler"),
            ("fastapi/params.py", "class Depends"),
            ("fastapi/dependencies/models.py", "class Dependant"),
            ("tests/test_dependency_cache.py", "def test_"),
        ],
    ),
]


def repomix_bin() -> list[str]:
    local = TOOLS / "node_modules" / ".bin" / "repomix"
    return [str(local)] if local.exists() else ["npx", "--yes", f"repomix@{REPOMIX_VERSION}"]


def gitingest_bin() -> list[str]:
    return [sys.executable, "-m", "gitingest"]


def configs(case: Case, budget: int) -> list[tuple[str, list[str], Path | None]]:
    """(label, argv, output file) for every tool setting. ``{repo}`` and ``{out}`` are filled in later."""
    contexta = [sys.executable, str(ROOT / "contexta.py"), "{repo}"]
    return [
        ("contexta (default)", contexta + ["-o", "{out}"], None),
        (f"contexta --budget {budget // 1000}k --focus", contexta + ["--budget", str(budget), "--focus", case.task, "-o", "{out}"], None),
        (f"contexta --budget {budget // 1000}k --focus --no-graph", contexta + ["--budget", str(budget), "--focus", case.task, "--no-graph", "-o", "{out}"], None),
        ("repomix (default)", repomix_bin() + ["{repo}", "--style", "markdown", "-o", "{out}", "--quiet"], None),
        ("repomix --compress", repomix_bin() + ["{repo}", "--style", "markdown", "--compress", "-o", "{out}", "--quiet"], None),
        (f"repomix --compress --include {case.package_glob}", repomix_bin() + ["{repo}", "--style", "markdown", "--compress", "--include", case.package_glob, "-o", "{out}", "--quiet"], None),
        ("gitingest (default)", gitingest_bin() + ["{repo}", "-o", "{out}"], None),
    ]


def count_tokens(text: str) -> int:
    import tiktoken

    return len(tiktoken.get_encoding("cl100k_base").encode(text, disallowed_special=()))


def recall(text: str, expected: list[tuple[str, str]]) -> tuple[int, list[str]]:
    hits, missing = 0, []
    for path, anchor in expected:
        if path in text and anchor in text:
            hits += 1
        else:
            missing.append(path)
    return hits, missing


def run_once(argv: list[str], repo: Path, out: Path) -> tuple[float, int, str]:
    cmd = [part.format(repo=str(repo), out=str(out)) for part in argv]
    if out.exists():
        out.unlink()
    start = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo.parent))
    elapsed = time.perf_counter() - start
    return elapsed, proc.returncode, (proc.stderr or "")[-300:]


def measure(label: str, argv: list[str], case: Case, repo: Path, budget: int, reps: int, workdir: Path) -> dict:
    out = workdir / f"{case.name}-{abs(hash(label)) % 10**8}.md"
    is_contexta = label.startswith("contexta")
    times: list[float] = []
    error = ""
    for i in range(reps):
        if is_contexta and "--no-graph" not in label and i == 0:
            shutil.rmtree(repo / ".contexta", ignore_errors=True)
        elapsed, code, err = run_once(argv, repo, out)
        if code != 0 or not out.exists():
            error = f"exit {code}: {err.strip()[-200:]}"
            break
        times.append(elapsed)
    row: dict = {"repo": case.name, "tool": label, "error": error}
    if error:
        return row
    text = out.read_text(encoding="utf-8", errors="replace")
    hits, missing = recall(text, case.expected)
    row.update(
        tokens=count_tokens(text),
        bytes=len(text.encode("utf-8")),
        recall=hits,
        expected=len(case.expected),
        missing=missing,
        time_median=round(statistics.median(times), 2),
        time_first=round(times[0], 2),
    )
    return row


def setup() -> None:
    REPOS.mkdir(exist_ok=True)
    for case in CASES:
        dest = REPOS / case.name
        if not dest.exists():
            dest.mkdir()
            for args in (["init", "-q"], ["remote", "add", "origin", case.url], ["fetch", "-q", "--depth", "1", "origin", case.commit], ["checkout", "-q", "FETCH_HEAD"]):
                subprocess.run(["git", *args], cwd=dest, check=True)
        print(f"{case.name}: {case.commit[:10]}")
    TOOLS.mkdir(exist_ok=True)
    subprocess.run(["npm", "install", "--silent", "--no-audit", "--no-fund", "--prefix", str(TOOLS), f"repomix@{REPOMIX_VERSION}"], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", f"gitingest=={GITINGEST_VERSION}", "tiktoken"], check=True)


def fmt_time(row: dict) -> str:
    if "time_first" not in row:
        return "n/a"
    if row["tool"].startswith("contexta") and "--no-graph" not in row["tool"]:
        return f"{row['time_first']:.1f}s cold / {row['time_median']:.1f}s"
    return f"{row['time_median']:.1f}s"


def table(rows: list[dict]) -> str:
    lines = ["| Repo | Tool | Tokens | Fits 128k | Time | Recall (files found) |", "|---|---|---:|:---:|---:|---|"]
    for row in rows:
        if row["error"]:
            lines.append(f"| {row['repo']} | {row['tool']} | failed | | | {row['error'][:60]} |")
            continue
        fits = "yes" if row["tokens"] <= WINDOW else "no"
        miss = f" (missing {', '.join(Path(m).name for m in row['missing'])})" if row["missing"] else ""
        lines.append(f"| {row['repo']} | {row['tool']} | {row['tokens']:,} | {fits} | {fmt_time(row)} | {row['recall']}/{row['expected']}{miss} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--setup", action="store_true", help="clone the pinned repos and install repomix and gitingest")
    parser.add_argument("--repos", nargs="*", default=[c.name for c in CASES])
    parser.add_argument("--repos-dir", default=str(REPOS), help="where the pinned clones live")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--budget", type=int, default=20000)
    parser.add_argument("--out-dir", default=str(HERE))
    args = parser.parse_args()
    if args.setup:
        setup()
        return 0

    workdir = Path(args.out_dir) / ".work"
    workdir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for case in [c for c in CASES if c.name in args.repos]:
        repo = Path(args.repos_dir) / case.name
        if not repo.exists():
            print(f"{repo} is missing. Run with --setup first.", file=sys.stderr)
            return 2
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
        if head != case.commit:
            print(f"warning: {case.name} is at {head[:10]}, not the pinned {case.commit[:10]}. Numbers will differ.", file=sys.stderr)
        for label, argv, _ in configs(case, args.budget):
            print(f"{case.name:9} {label} ...", file=sys.stderr, flush=True)
            rows.append(measure(label, argv, case, repo, args.budget, args.reps, workdir))
        shutil.rmtree(repo / ".contexta", ignore_errors=True)
    shutil.rmtree(workdir, ignore_errors=True)

    meta = {
        "python": platform.python_version(), "platform": platform.platform(), "cpus": __import__("os").cpu_count(),
        "repomix": REPOMIX_VERSION, "gitingest": GITINGEST_VERSION, "budget": args.budget, "reps": args.reps,
        "commits": {c.name: c.commit for c in CASES},
    }
    out_dir = Path(args.out_dir)
    (out_dir / "results.json").write_text(json.dumps({"meta": meta, "rows": rows}, indent=2), encoding="utf-8")
    md = table(rows)
    (out_dir / "results.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

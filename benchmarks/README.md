# Benchmark: Contexta vs Repomix vs Gitingest

Reproducible, on pinned commits of Flask, Requests and FastAPI.

```bash
python benchmarks/bench.py --setup   # clones the pinned commits, installs repomix and gitingest (needs git, node, pip)
python benchmarks/bench.py           # about 4 minutes; writes benchmarks/results.md and results.json
```

Versions: Repomix 1.18.1, Gitingest 0.3.1, Contexta from this checkout. Python 3.13, Linux, 3 runs per cell.

## What is measured

| Metric | How |
|---|---|
| **Tokens** | `tiktoken` `cl100k_base` over the whole output file. Same tokenizer for every tool |
| **Time** | Wall clock of the whole command, median of 3. Contexta's first run starts without `.contexta/` (cold graph), the next two reuse it |
| **Recall** | For each repo there is one task and the files a person would need for it (4 or 5 files, listed in `bench.py`). A file counts as found when its path **and** one signature line from it are in the output. Signatures survive compression, so compressed or signature-only output is not punished for dropping function bodies |

The task per repo: Flask "session cookie signing", Requests "how the HTTP adapter sends a request and
follows redirects", FastAPI "dependency injection solving". Contexta gets the task through `--focus`.
Repomix and Gitingest have no task input, so they get two settings: the default, and (for Repomix)
`--compress --include <package dir>`, which is what a person who already knows the repo would type.

## Results

| Repo | Tool | Tokens | Fits 128k | Time | Recall (files found) |
|---|---|---:|:---:|---:|---|
| flask | contexta (default) | 168,126 | no | 1.1s cold / 0.9s | 4/4 |
| flask | contexta --budget 20k --focus | 8,356 | yes | 0.8s cold / 0.6s | 3/4 (missing ctx.py) |
| flask | contexta --budget 20k --focus --no-graph | 17,174 | yes | 0.6s | 3/4 (missing ctx.py) |
| flask | repomix (default) | 285,568 | no | 0.6s | 4/4 |
| flask | repomix --compress | 228,991 | no | 0.7s | 4/4 |
| flask | repomix --compress --include src/flask/** | 53,926 | yes | 0.6s | 3/4 (missing test_session_interface.py) |
| flask | gitingest (default) | 402,444 | no | 0.9s | 4/4 |
| requests | contexta (default) | 71,689 | yes | 0.7s cold / 0.5s | 4/4 |
| requests | contexta --budget 20k --focus | 17,639 | yes | 0.6s cold / 0.5s | 4/4 |
| requests | contexta --budget 20k --focus --no-graph | 16,597 | yes | 0.4s | 4/4 |
| requests | repomix (default) | 685,407 | no | 0.6s | 3/4 (missing test_requests.py) |
| requests | repomix --compress | 663,115 | no | 0.7s | 2/4 (missing sessions.py, test_requests.py) |
| requests | repomix --compress --include src/requests/** | 32,080 | yes | 0.6s | 2/4 (missing sessions.py, test_requests.py) |
| requests | gitingest (default) | 170,996 | no | 0.7s | 4/4 |
| fastapi | contexta (default) | 2,108,026 | no | 10.4s cold / 8.6s | 5/5 |
| fastapi | contexta --budget 20k --focus | 17,677 | yes | 2.7s cold / 1.4s | 2/5 (missing params.py, models.py, test_dependency_cache.py) |
| fastapi | contexta --budget 20k --focus --no-graph | 17,723 | yes | 3.6s | 2/5 (missing params.py, models.py, test_dependency_cache.py) |
| fastapi | repomix (default) | 8,869,684 | no | 1.3s | 5/5 |
| fastapi | repomix --compress | 8,215,545 | no | 1.6s | 4/5 (missing utils.py) |
| fastapi | repomix --compress --include fastapi/** | 42,527 | yes | 0.7s | 2/5 (missing utils.py, routing.py, test_dependency_cache.py) |
| fastapi | gitingest (default) | 4,373,871 | no | 4.9s | 5/5 |

## How to read this

**Where Contexta is ahead**

- It is the only one of the three that can *fit a window*. With `--budget 20000` every run is 8k to 18k
  tokens. The others only fit when a person writes an `--include` glob first, and then the pack has no
  idea which of those files matter.
- Among the outputs that fit in 128k, Contexta found at least as many of the needed files on all three
  repos (3/4, 4/4, 2/5 against Repomix's guided 3/4, 2/4, 2/5), without being told where the code lives.
- On FastAPI (2,000+ files) the graph prefilter makes the budgeted run faster than without it
  (1.4 s warm and 2.7 s cold, against 3.6 s). On Flask it halves the tokens for the same recall (8.4k against 17.2k).

**Where Contexta loses**

- **Speed on small repos.** Repomix and Gitingest finish Flask in 0.6 to 0.9 s, the same range as
  Contexta (0.9 s default, 0.6 s budgeted). The unbudgeted FastAPI pack takes 8.6 s warm and 10.4 s cold, against
  1.3 s for Repomix and 4.9 s for Gitingest. Contexta does analysis (roles, risk, relationships,
  redaction) that the others skip.
- **Unbudgeted packs are not small.** Flask is 168k tokens by default and FastAPI is 2.1M, both over
  128k (Requests, at 72k, fits). Use `--budget` or `--focus`. Contexta stops at 2,000 files by default, so its FastAPI number is
  a partial repo, while Repomix's 8.9M is the whole thing.
- **Full dumps have perfect recall** for the trivial reason that they contain everything. Recall only
  means something between outputs that fit in a window.
- **Recall is not perfect.** FastAPI's focused pack finds `solve_dependencies` and `routing.py` but not
  `params.py` (`class Depends`) or `dependencies/models.py`: the focus words ("dependency injection
  solving") do not match "Depends" or "Dependant" and the pack has no semantic matching. Flask's focused pack misses `ctx.py`.
  Both are candidates for the next release, not solved problems.

**What this does not show.** Recall counts files, not answer quality. Contexta's packs also carry
sections (reading order, risks, entry points) that these numbers neither reward nor penalize. Three repos
and one task each is a small sample: treat the table as a reproducible comparison, not a verdict.
Contexta writes a `.contexta/` folder into the scanned repo (self-gitignored; `--no-graph` disables it).
The script deletes it afterwards.

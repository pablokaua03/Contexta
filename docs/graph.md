# Project graph

Contexta keeps a small SQLite index of your project in `.contexta/graph.db`: files, symbols
(classes, functions, methods), tests, and the relations between them. It updates itself as Contexta
reads the project, and it uses the index to answer questions without re-reading the repo.

```bash
contexta graph update                          # index or refresh (incremental, usually well under a second)
contexta graph impact src/app/session.py       # what a change reaches, and which tests to run
contexta graph dependents src/app/util.py::slugify
contexta graph dependencies src/app/core.py
contexta graph changed --since main            # also: a tag, a commit or 2026-10-01
contexta graph hot                             # most changed files
contexta graph symbols session                 # find a class or function
contexta graph map --budget 1500 --focus auth  # a ranked map of the repo in ~1.5k tokens
contexta graph export -o graph.json            # also: --format jsonl, --format md
contexta graph status | clear
```

Every query takes `-C DIR` for another folder, `--json` for machine-readable output, `--no-update` to
skip the refresh, and `--no-git` to skip git history.

## What is in it

| Node | Edge | Source |
|---|---|---|
| file, test, symbol | `imports` | static imports, resolved per language, following re-exports |
| | `calls` | calls that resolve to one definition (a call matched only by a unique name counts less) |
| | `tests` | test file to source file, by what it imports or calls, or by name |
| | `cochange` | files that changed in the same git commits (last 1,000 commits) |

Python is parsed with `ast`. JavaScript, TypeScript, Go and Rust use tree-sitter when it is installed
(`pip install "contexta-ai[syntax]"`) and a regex fallback otherwise. Other languages get file nodes
and import edges where the language is understood.

Updates are incremental: a file is re-read only when its size or modification time changed, and
re-parsed only when its hash changed.

## What it never stores

- **No file contents.** Names, signatures, line numbers, and relations only. Signatures go through
  the same secret redaction as packs.
- **No credential files.** `.env*`, private keys, `.npmrc` and the like are not indexed at all.
- **No authors.** Git history stores file, time and commit id.
- It is **gitignored by default**: Contexta writes `.contexta/.gitignore` containing `*`.
  `CONTEXTA_GRAPH_DIR` moves it elsewhere. `--no-graph`, or `graph = false` in `contexta.toml`, turns it
  off for packs, and `contexta graph clear` deletes it.

## In the desktop app

The **Project memory** card shows the graph's status and runs Update, Hot files, Symbols, Impact and
Open map without a terminal. Per analysis, **Save this analysis to Contexta memory** and **Memory to
use** decide whether a run writes the graph, only reads it, or ignores it. The CLI equivalents are
`--no-memory`, `--memory PATH` and `--memory-read-only` (`memory_path` and `memory_save` in
`contexta.toml`). A memory kept outside `.contexta/` carries a stamp of its project, and another
project's run only reads it.

## How packs use it

- **Ranking.** Files get a weighted PageRank over imports and calls. With `--budget` the rank and the
  git churn of a file raise its priority, so the files everything depends on survive the cut.
- **Focus.** With `--focus`, the tests that cover the best-matching files come along.
- **Large repos.** Above 800 files, a run with `--budget` or `--focus` analyses the 400 highest-ranked
  source files plus their tests and the root and manifest files, instead of every file. The pack says so.
- It never makes a pack fail. If the graph cannot be read, the pack is built without it.

## MCP

`repo_map`, `search_symbols`, `impacted_tests`, `graph_query` and `context_for` read the same graph.
See the README for the list. All of them are confined to the server's roots.

## Export for other tools

`contexta graph export` writes `contexta.graph.v1` JSON (`nodes`, `edges`, `meta`), JSON Lines (one
record per line, for streaming imports), or Markdown (one section per file, readable by people and
note-taking tools). Nothing in it depends on any particular tool.

```json
{"format": "contexta.graph.v1", "nodes": [{"id": "src/app/core.py", "type": "source", "rank": 0.07},
  {"id": "src/app/core.py::Engine.run", "type": "symbol", "line": 12}],
 "edges": [{"source": "src/app/api.py", "target": "src/app/core.py", "kind": "imports", "weight": 1.0}]}
```

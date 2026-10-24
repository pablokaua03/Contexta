# Contexta GitHub Action

Give every pull request an AI-ready context file: the diff, the files it reaches, the tests worth
running, and a redacted pack of the changed code that fits a token budget. Reviewers (and review
agents) open one file instead of reading the whole repo.

```yaml
# .github/workflows/contexta.yml
name: Contexta
on: pull_request

permissions:
  contents: read
  pull-requests: write   # only needed for `comment: true`

jobs:
  context:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # the action compares against the base branch
      - uses: pablokaua03/contexta@main    # pin a release tag in real use
        with:
          budget: 24000
          comment: true
```

Each run uploads `contexta-pr-context` (a Markdown file) as an artifact, writes the summary to the
job page, and, with `comment: true`, keeps **one** comment on the PR up to date instead of adding a
new one per push.

## What is in the file

1. A header: changed files and the test files to run (from the project graph: imports, calls,
   same-name tests, git co-change).
2. The PR pack (`contexta --for review`): the changed files plus the related files the pack selects, cut to the
   budget. The pack says what it left out.

The header counts against the budget, so the whole file stays at or under `budget` tokens.

## Inputs

| Input | Default | |
|---|---|---|
| `base-ref` | the PR's base branch | Branch to compare against. |
| `budget` | `24000` | Token budget for the whole file. |
| `comment` | `false` | Post or update the summary comment. |
| `artifact-name` | `contexta-pr-context` | |
| `output` | `contexta-pr-context.md` | File name of the pack. |
| `path` | `.` | Project folder, for monorepos. |
| `python-version` | `3.12` | |
| `github-token` | `github.token` | Used only for the comment. |

Outputs: `pack-path`, `tokens`, `changed-files`, `tests`.

## Safety

- **Redaction is on.** The pack goes through the same secret redaction as `contexta .`. Credential
  files such as `.env` or private keys are never read.
- **The comment has paths and numbers only**, never source code.
- **Forks.** Pull requests from forks get a read-only token. The comment step then logs a warning
  and the run still succeeds, with the artifact uploaded. Do not switch to `pull_request_target` to
  work around this: it would run with write permissions on code you have not reviewed.
- Inputs reach the shell through environment variables, never through the script text.
- The action writes `.contexta/` (the graph, self-gitignored) inside the checkout. The runner is
  thrown away afterwards.

## Without the action

The same thing works in any CI, or on your laptop:

```bash
pip install contexta-ai
python -m contexta_app.ci_report --base origin/main --budget 24000 --output pr-context.md
```

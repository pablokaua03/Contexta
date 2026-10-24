# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 2.2.x | Yes |
| 2.1.x | Yes |
| 2.0.x | Yes |
| < 2.0.0 | No |

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not open a public issue**.

Instead, contact directly via GitHub:
https://github.com/pablokaua03/Contexta/issues

Describe the vulnerability, steps to reproduce, and potential impact.
You can expect a response within 7 days.

## Security notes

- `Contexta` never modifies, deletes, or uploads your project files. It does write its own project graph to `.contexta/` (or `CONTEXTA_GRAPH_DIR`) unless `--no-graph` is set, and `contexta install` writes agent rules and MCP config files you ask for
- It sends no telemetry. Packs, the project graph and the MCP server do not need the network
- The network is used in three cases only: the first token count downloads the `cl100k_base` encoding once through `tiktoken` (cached afterwards; offline, Contexta falls back to a character-based estimate), the optional `--ask` feature sends the pack to the AI provider you configured, and the GitHub Action posts its pull request comment to the GitHub API
- It uses local runtime dependencies for parsing, token estimation, and repository analysis
- On some Linux distributions, `tkinter` may come from a system package such as `python3-tk`
- Windows builds use `Nuitka`; Linux packaging uses `PyInstaller`
- Analysis happens locally on your machine
- Exports replace likely secrets (API keys, private keys, tokens, connection-string passwords) with `[REDACTED]` before the pack is written. This is best-effort and does not make it safe to commit real credentials

# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 1.4.x | ✅ |
| < 1.4.0 | ❌ |

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not open a public issue**.

Instead, contact directly via GitHub:
👉 https://github.com/pablokaua03/Contexta/issues

Describe the vulnerability, steps to reproduce, and potential impact.
You can expect a response within 7 days.

## Security notes

- `Contexta` is a **read-only** tool — it never modifies, deletes or uploads any files
- It makes **no network requests** of any kind
- It has **zero external runtime dependencies**
- On some Linux distributions, `tkinter` may come from a system package such as `python3-tk`
- Optional executable builds use **PyInstaller**, which is a packaging dependency rather than a runtime dependency
- The `onedir` build (`contexta-safe`) is recommended when Windows SmartScreen or antivirus heuristics are too aggressive with the single-file executable
- All processing happens locally on your machine

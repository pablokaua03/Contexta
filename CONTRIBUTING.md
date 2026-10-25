# Contributing to Contexta

Thank you for considering a contribution!

## Ground rules

- Runtime dependencies should stay small and high-leverage
- Optional packaging tools such as **Nuitka** or **PyInstaller** must stay out of runtime code paths
- Python **3.10+** syntax is acceptable
- Every PR must keep the project runnable with `python contexta.py` after `python -m pip install -r requirements.txt`
- Tests: `python -m pip install -e . -r requirements-dev.txt`, then `python -m pytest -q` (on Linux add `xvfb-run -a` for the GUI tests; the tests that need Pillow or PyYAML skip when those are missing)

## How to contribute

1. Fork and clone
2. Create a branch: `git checkout -b feature/short-description`
3. Commit: `git commit -m "feat: description"`
4. Push and open a Pull Request against `main`

## Adding language extensions

```python
# In contexta_app/scanner.py → CODE_EXTENSIONS dict
".xyz": "xyz",
```

## Reporting bugs

Open an issue with OS, Python version, and full error traceback.

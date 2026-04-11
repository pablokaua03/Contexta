# Contributing to mdcodebrief

Thank you for considering a contribution!

## Ground rules

- The tool must remain **zero-dependency** (standard library only)
- Python **3.10+** syntax is acceptable
- Every PR must keep the project runnable with `python mdcodebrief.py`

## How to contribute

1. Fork and clone
2. Create a branch: `git checkout -b feature/short-description`
3. Commit: `git commit -m "feat: description"`
4. Push and open a Pull Request against `main`

## Adding language extensions

```python
# In scanner.py → CODE_EXTENSIONS dict
".xyz": "xyz",
```

## Reporting bugs

Open an issue with OS, Python version, and full error traceback.

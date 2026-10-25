"""contexta_app.engine.insight: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path
from contexta_app.scanner import get_language, read_file_safe
from contexta_app.syntax import extract_symbols_with_treesitter

from contexta_app.engine.models import (
    FileInsight,
    FileSignals,
)

def flatten_tree(node: dict) -> list[Path]:
    files = [item["path"] for item in node["files"]]
    for sub in node["dirs"]:
        files.extend(flatten_tree(sub))
    return files

def make_file_insight(project_path: Path, path: Path) -> FileInsight:
    content, truncated, total_line_count = read_file_safe(path)
    lang = get_language(path)
    functions, classes, imports = extract_symbols(content, lang)
    imported_names = python_imported_names(content) if lang == "python" else []
    external_imports = [item for item in imports if not item.startswith(".")]
    return FileInsight(
        path=path,
        relpath=path.relative_to(project_path),
        lang=lang,
        content=content,
        truncated=truncated,
        line_count=total_line_count,
        rendered_line_count=len(content.splitlines()),
        functions=functions,
        classes=classes,
        imports=imports,
        imported_names=imported_names,
        external_imports=external_imports,
    )

@lru_cache(maxsize=64)
def _python_ast_symbols(content: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    """Top-level functions and classes, imported modules and imported names, from ``ast``.

    Python is read with the standard library whether or not tree-sitter is installed, so a pack
    does not depend on an optional package. Modules are written the way ``resolve_local_import``
    expects them: ``pkg.core``, or leading dots for a relative import (``.util``).
    """
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError, RecursionError):
        return None
    functions = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    modules: list[str] = []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append("." * (node.level or 0) + (node.module or ""))
            names.extend(alias.name for alias in node.names if alias.name != "*")
    unique = lambda values, limit: tuple(dict.fromkeys(values))[:limit]  # noqa: E731
    return unique(functions, 12), unique(classes, 8), unique(modules, 24), unique(names, 40)

def python_imported_names(content: str) -> list[str]:
    """Names brought in with ``from x import name``, for focus matching ("slugify" finds its callers)."""
    parsed = _python_ast_symbols(content)
    return list(parsed[3]) if parsed else []

def extract_symbols(content: str, lang: str | None) -> tuple[list[str], list[str], list[str]]:
    if lang == "python":
        parsed = _python_ast_symbols(content)
        if parsed:
            return list(parsed[0]), list(parsed[1]), list(parsed[2])

    syntax_symbols = extract_symbols_with_treesitter(content, lang)
    if syntax_symbols:
        functions, classes, imports = syntax_symbols
        if functions or classes or imports:
            return functions[:12], classes[:8], imports[:24]

    if lang == "python":
        functions = re.findall(r"^\s*(?:async\s+def|def)\s+([A-Za-z_]\w*)", content, re.MULTILINE)
        classes = re.findall(r"^\s*class\s+([A-Za-z_]\w*)", content, re.MULTILINE)
        imports = []
        imports.extend(re.findall(r"^\s*import\s+([A-Za-z0-9_\.]+)", content, re.MULTILINE))
        imports.extend(re.findall(r"^\s*from\s+([A-Za-z0-9_\.]+|\.+[A-Za-z0-9_\.]*)\s+import", content, re.MULTILINE))
        return functions[:12], classes[:8], imports[:24]

    if lang in {"javascript", "jsx", "typescript", "tsx"}:
        functions = re.findall(r"(?:function|const|let|var)\s+([A-Za-z_]\w*)", content)
        classes = re.findall(r"class\s+([A-Za-z_]\w*)", content)
        imports = re.findall(r"""from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)""", content)
        flat_imports = [left or right for left, right in imports]
        return functions[:12], classes[:8], flat_imports[:24]

    if lang == "php":
        functions = re.findall(r"function\s+([A-Za-z_]\w*)", content, re.IGNORECASE)
        classes = re.findall(r"class\s+([A-Za-z_]\w*)", content, re.IGNORECASE)
        imports = []
        imports.extend(
            re.findall(r"""(?:require|require_once|include|include_once)\s*(?:\(|)\s*['"]([^'"]+)['"]""", content, re.IGNORECASE)
        )
        imports.extend(re.findall(r"^\s*use\s+([A-Za-z0-9_\\\\]+)", content, re.MULTILINE))
        return functions[:12], classes[:8], imports[:24]

    if lang == "java":
        functions = re.findall(
            r"\b(?:public|protected|private|static|final|synchronized|abstract|native|\s)+[\w<>\[\],?]+\s+([A-Za-z_]\w*)\s*\(",
            content,
        )
        classes = re.findall(r"\b(?:class|interface|enum|record)\s+([A-Za-z_]\w*)", content)
        imports = re.findall(r"^\s*import\s+([A-Za-z0-9_.*]+)", content, re.MULTILINE)
        return functions[:12], classes[:8], imports[:24]

    if lang == "csharp":
        functions = re.findall(
            r"\b(?:public|private|protected|internal|static|async|virtual|override|sealed|partial|extern|new|\s)+[\w<>\[\],?]+\s+([A-Za-z_]\w*)\s*\(",
            content,
        )
        classes = re.findall(r"\b(?:class|interface|enum|record|struct)\s+([A-Za-z_]\w*)", content)
        imports = re.findall(r"^\s*using\s+([A-Za-z0-9_.]+)", content, re.MULTILINE)
        return functions[:12], classes[:8], imports[:24]

    if lang == "go":
        functions = re.findall(r"\bfunc\s+([A-Za-z_]\w*)\s*\(", content)
        classes = re.findall(r"\btype\s+([A-Za-z_]\w*)\s+(?:struct|interface)", content)
        imports = re.findall(r'import\s+(?:\(\s*)?"([^"]+)"', content)
        return functions[:12], classes[:8], imports[:24]

    if lang == "rust":
        functions = re.findall(r"\bfn\s+([A-Za-z_]\w*)\s*\(", content)
        classes = re.findall(r"\b(?:struct|enum|trait)\s+([A-Za-z_]\w*)", content)
        imports = re.findall(r"^\s*use\s+([^;]+);", content, re.MULTILINE)
        return functions[:12], classes[:8], imports[:24]

    return [], [], []

def collect_file_signals(item: FileInsight) -> FileSignals:
    rel = item.relpath.as_posix().lower()
    content_lower = item.content.lower()
    signals = FileSignals()

    if "createcontext" in content_lower or "usecontext" in content_lower:
        signals.has_react_context = True
        signals.raw_matches.append("react_context")
    if (
        "translations" in content_lower
        or "translation" in content_lower
        or "dictionary" in content_lower
        or "uselocale" in content_lower
        or "usetranslations" in content_lower
        or "/locales/" in rel
        or "/translations/" in rel
    ):
        signals.has_translation_dict = True
        signals.raw_matches.append("translations")
    if "tkinter" in content_lower:
        signals.has_tkinter = True
        signals.raw_matches.append("tkinter")
    if "sys.argv" in content_lower or "argparse" in content_lower:
        signals.has_cli_args = True
        signals.raw_matches.append("cli_args")
    if "require_once" in content_lower or "include_once" in content_lower:
        signals.has_require_once = True
        signals.raw_matches.append("php_require_once")
    if "service" in item.path.stem.lower() or re.search(r"class\s+[a-z0-9_]*service", content_lower):
        signals.has_service_class = True
        signals.raw_matches.append("service_class")
    if (
        "dao" in item.path.stem.lower()
        or "repository" in item.path.stem.lower()
        or "repository" in content_lower
        or "dao" in content_lower
    ):
        signals.has_dao_usage = True
        signals.raw_matches.append("dao_usage")
    if "export default function" in content_lower and rel.endswith(("/page.tsx", "/page.jsx")):
        signals.has_next_page_export = True
        signals.raw_matches.append("next_page")
    if (
        "<form" in content_lower
        or "onsubmit" in content_lower
        or "handlechange" in content_lower
        or "useform" in content_lower
        or "textarea" in content_lower
    ):
        signals.has_form_handling = True
        signals.raw_matches.append("form_handling")
    if "firebase/auth" in content_lower:
        signals.imports_firebase_auth = True
        signals.raw_matches.append("firebase_auth")
    if "next/navigation" in content_lower:
        signals.imports_next_navigation = True
        signals.raw_matches.append("next_navigation")
    return signals

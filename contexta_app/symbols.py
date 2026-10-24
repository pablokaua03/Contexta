"""
symbols.py - Symbols, imports and calls for the project graph.

Python uses the standard library ``ast``, so it is exact and needs nothing
installed. Other languages use tree-sitter when it is installed (the optional
``syntax`` extra) and a small regex scanner when it is not. Both paths return
the same ``FileFacts``.

Nothing here keeps file content. Signatures are trimmed and redacted by the
caller before they are stored.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from contexta_app import syntax as _syntax

MAX_SYMBOLS_PER_FILE = 400
MAX_CALLS_PER_FILE = 1500
MAX_SIGNATURE = 160
MODULE_SCOPE = "<module>"


@dataclass(frozen=True)
class Symbol:
    name: str
    qualname: str
    kind: str  # function | method | class | const | type | interface | enum | trait | module
    line: int
    end_line: int = 0
    signature: str = ""
    parent: str = ""


@dataclass(frozen=True)
class ImportRef:
    module: str
    level: int = 0
    names: tuple[str, ...] = ()
    line: int = 0


@dataclass
class FileFacts:
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)  # (caller qualname, callee name)
    backend: str = "none"  # ast | tree-sitter | regex | none


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_SIGNATURE else text[: MAX_SIGNATURE - 1] + "…"


# ---------------------------------------------------------------- Python (ast)


def _py_signature(node: ast.AST) -> str:
    try:
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            return _clip(f"class {node.name}({bases})" if bases else f"class {node.name}")
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        return _clip(f"{prefix} {node.name}({ast.unparse(node.args)}){returns}")
    except Exception:
        return getattr(node, "name", "")


def _called_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


class _CallCollector(ast.NodeVisitor):
    """Names called (or used as decorators / bases) inside one scope, not descending into nested defs."""

    def __init__(self) -> None:
        self.names: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = _called_name(node.func)
        if name:
            self.names.append(name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):  # nested defs are scopes of their own
        return

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef


def _py_calls(nodes: list[ast.AST]) -> list[str]:
    collector = _CallCollector()
    for node in nodes:
        collector.visit(node)
    return collector.names


def _decorator_names(node) -> list[str]:
    names = []
    for deco in getattr(node, "decorator_list", []):
        target = deco.func if isinstance(deco, ast.Call) else deco
        name = _called_name(target)
        if name:
            names.append(name)
    return names


def _python_facts(content: str) -> FileFacts | None:
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError, RecursionError):
        return None
    facts = FileFacts(backend="ast")

    def walk_scope(body: list[ast.stmt], parent: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{parent}.{node.name}" if parent else node.name
                kind = "method" if parent and parent_kind.get(parent) == "class" else "function"
                facts.symbols.append(
                    Symbol(node.name, qual, kind, node.lineno, getattr(node, "end_lineno", 0) or 0, _py_signature(node), parent)
                )
                parent_kind[qual] = kind
                for callee in _decorator_names(node) + _py_calls(node.body):
                    facts.calls.append((qual, callee))
                walk_scope(node.body, qual)
            elif isinstance(node, ast.ClassDef):
                qual = f"{parent}.{node.name}" if parent else node.name
                facts.symbols.append(
                    Symbol(node.name, qual, "class", node.lineno, getattr(node, "end_lineno", 0) or 0, _py_signature(node), parent)
                )
                parent_kind[qual] = "class"
                for base in node.bases:
                    name = _called_name(base)
                    if name:
                        facts.calls.append((qual, name))
                for callee in _decorator_names(node):
                    facts.calls.append((qual, callee))
                walk_scope(node.body, qual)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and not parent:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id.isupper() and len(target.id) > 1:
                        facts.symbols.append(Symbol(target.id, target.id, "const", node.lineno, getattr(node, "end_lineno", 0) or 0, target.id))
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)) and not parent:
                for inner in ast.iter_child_nodes(node):
                    if isinstance(inner, ast.stmt):
                        walk_scope([inner], parent)
        # module-level calls are attributed to <module>

    parent_kind: dict[str, str] = {}
    walk_scope(tree.body, "")
    module_level = [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    for callee in _py_calls(module_level):
        facts.calls.append((MODULE_SCOPE, callee))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                facts.imports.append(ImportRef(alias.name, 0, (), node.lineno))
        elif isinstance(node, ast.ImportFrom):
            facts.imports.append(
                ImportRef(node.module or "", node.level or 0, tuple(a.name for a in node.names if a.name != "*"), node.lineno)
            )
    facts.symbols = facts.symbols[:MAX_SYMBOLS_PER_FILE]
    facts.calls = facts.calls[:MAX_CALLS_PER_FILE]
    return facts


# ------------------------------------------------------------- tree-sitter path

_TS_SYMBOL_TYPES = {
    "javascript": {
        "function_declaration": "function", "generator_function_declaration": "function",
        "class_declaration": "class", "method_definition": "method",
    },
    "typescript": {
        "function_declaration": "function", "class_declaration": "class", "method_definition": "method",
        "interface_declaration": "interface", "type_alias_declaration": "type", "enum_declaration": "enum",
        "abstract_class_declaration": "class",
    },
    "go": {"function_declaration": "function", "method_declaration": "method", "type_spec": "type"},
    "rust": {
        "function_item": "function", "struct_item": "class", "enum_item": "enum",
        "trait_item": "trait", "mod_item": "module",
    },
}
_TS_SYMBOL_TYPES["tsx"] = _TS_SYMBOL_TYPES["typescript"]


def _ts_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def _ts_name(node, source: bytes) -> str:
    named = node.child_by_field_name("name")
    return _ts_text(named, source) if named is not None else ""


def _tree_sitter_facts(content: str, lang: str | None) -> FileFacts | None:
    parsed = _syntax.parse_tree(content, lang)
    if parsed is None:
        return None
    root, source, key = parsed
    types = _TS_SYMBOL_TYPES.get(key)
    if not types:
        return None
    facts = FileFacts(backend="tree-sitter")

    def signature(node) -> str:
        first = _ts_text(node, source).split("\n", 1)[0]
        return _clip(first.rstrip("{ \t"))

    def visit(node, parent: str) -> None:
        kind = types.get(node.type)
        scope = parent
        if kind:
            name = _ts_name(node, source)
            if name:
                qual = f"{parent}.{name}" if parent else name
                facts.symbols.append(Symbol(name, qual, kind, node.start_point[0] + 1, node.end_point[0] + 1, signature(node), parent))
                if kind in {"class", "trait", "interface"}:
                    scope = qual
        elif node.type == "variable_declarator" and key in {"javascript", "typescript", "tsx"}:
            value = node.child_by_field_name("value")
            if value is not None and value.type in {"arrow_function", "function_expression", "function"}:
                name = _ts_name(node, source)
                if name:
                    qual = f"{parent}.{name}" if parent else name
                    facts.symbols.append(Symbol(name, qual, "function", node.start_point[0] + 1, node.end_point[0] + 1, signature(node), parent))
        elif node.type == "import_statement" and key != "go":
            src = node.child_by_field_name("source")
            if src is not None:
                facts.imports.append(ImportRef(_ts_text(src, source).strip("'\""), 0, (), node.start_point[0] + 1))
        elif node.type == "import_spec" and key == "go":
            path = node.child_by_field_name("path")
            if path is not None:
                facts.imports.append(ImportRef(_ts_text(path, source).strip('"`'), 0, (), node.start_point[0] + 1))
        elif node.type == "use_declaration" and key == "rust":
            facts.imports.append(ImportRef(_ts_text(node, source)[4:].strip().rstrip(";"), 0, (), node.start_point[0] + 1))
        elif node.type == "call_expression" or node.type == "call":
            fn = node.child_by_field_name("function")
            if fn is not None:
                tail = fn
                if fn.type in {"member_expression", "selector_expression", "field_expression"}:
                    prop = fn.child_by_field_name("property") or fn.child_by_field_name("field")
                    tail = prop if prop is not None else fn
                text = _ts_text(tail, source)
                if re.fullmatch(r"[A-Za-z_$][\w$]*", text):
                    facts.calls.append((parent or MODULE_SCOPE, text))
        for child in node.children:
            visit(child, scope)

    try:
        visit(root, "")
    except RecursionError:
        pass
    facts.symbols = facts.symbols[:MAX_SYMBOLS_PER_FILE]
    facts.calls = facts.calls[:MAX_CALLS_PER_FILE]
    return facts


# ------------------------------------------------------------------ regex path

_REGEX_RULES: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "javascript": [
        ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\*?\s+([A-Za-z_$][\w$]*)")),
        ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>")),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)")),
        ("type", re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*[=<]")),
        ("enum", re.compile(r"^\s*(?:export\s+)?(?:const\s+)?enum\s+([A-Za-z_$][\w$]*)")),
    ],
    "go": [
        ("method", re.compile(r"^func\s+\([^)]*\)\s+([A-Za-z_]\w*)")),
        ("function", re.compile(r"^func\s+([A-Za-z_]\w*)")),
        ("type", re.compile(r"^type\s+([A-Za-z_]\w*)")),
    ],
    "rust": [
        ("function", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+([A-Za-z_]\w*)")),
        ("class", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+([A-Za-z_]\w*)")),
        ("enum", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+([A-Za-z_]\w*)")),
        ("trait", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+([A-Za-z_]\w*)")),
    ],
    "java": [
        ("class", re.compile(r"^\s*(?:public\s+|protected\s+|private\s+|abstract\s+|final\s+|static\s+)*(?:class|interface|enum|record)\s+([A-Za-z_]\w*)")),
        ("method", re.compile(r"^\s*(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?[\w<>\[\],.?\s]+?\s+([A-Za-z_]\w*)\s*\([^;]*$")),
    ],
    "php": [
        ("function", re.compile(r"^\s*(?:public\s+|protected\s+|private\s+|static\s+)*function\s+&?([A-Za-z_]\w*)")),
        ("class", re.compile(r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait|enum)\s+([A-Za-z_]\w*)")),
    ],
    "ruby": [
        ("function", re.compile(r"^\s*def\s+(?:self\.)?([A-Za-z_]\w*[?!=]?)")),
        ("class", re.compile(r"^\s*(?:class|module)\s+([A-Z]\w*)")),
    ],
    "csharp": [
        ("class", re.compile(r"^\s*(?:public\s+|internal\s+|private\s+|protected\s+|static\s+|abstract\s+|sealed\s+|partial\s+)*(?:class|interface|struct|enum|record)\s+([A-Za-z_]\w*)")),
        ("method", re.compile(r"^\s*(?:public|private|protected|internal)\s+(?:static\s+|async\s+|virtual\s+|override\s+)*[\w<>\[\],.?]+\s+([A-Za-z_]\w*)\s*\(")),
    ],
    "kotlin": [
        ("function", re.compile(r"^\s*(?:(?:public|private|internal|protected|override|suspend|inline)\s+)*fun\s+(?:<[^>]+>\s*)?(?:[\w.]+\.)?([A-Za-z_]\w*)")),
        ("class", re.compile(r"^\s*(?:(?:data|sealed|open|abstract|enum|private|internal)\s+)*(?:class|interface|object)\s+([A-Za-z_]\w*)")),
    ],
    "swift": [
        ("function", re.compile(r"^\s*(?:(?:public|private|internal|open|static|override|final)\s+)*func\s+([A-Za-z_]\w*)")),
        ("class", re.compile(r"^\s*(?:(?:public|private|internal|open|final)\s+)*(?:class|struct|enum|protocol|actor)\s+([A-Za-z_]\w*)")),
    ],
    "c": [
        ("function", re.compile(r"^[A-Za-z_][\w\s\*]*?\b([A-Za-z_]\w*)\s*\([^;]*\)\s*\{?\s*$")),
        ("class", re.compile(r"^\s*(?:typedef\s+)?(?:struct|enum|union)\s+([A-Za-z_]\w*)")),
    ],
}
_REGEX_RULES["typescript"] = _REGEX_RULES["javascript"]
_REGEX_RULES["tsx"] = _REGEX_RULES["javascript"]
_REGEX_RULES["jsx"] = _REGEX_RULES["javascript"]
_REGEX_RULES["cpp"] = _REGEX_RULES["c"]
_REGEX_RULES["scala"] = _REGEX_RULES["kotlin"]

_REGEX_IMPORTS: dict[str, list[re.Pattern[str]]] = {
    "javascript": [
        re.compile(r"""^\s*import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""),
        re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
        re.compile(r"""^\s*export\s+[^'"]*?\s+from\s+['"]([^'"]+)['"]"""),
    ],
    "go": [re.compile(r'^\s*(?:import\s+)?(?:[\w.]+\s+)?"([\w./\-]+)"\s*$')],
    "rust": [re.compile(r"^\s*(?:pub\s+)?use\s+([\w:{},\s*]+);"), re.compile(r"^\s*(?:pub\s+)?mod\s+([A-Za-z_]\w*)\s*;")],
    "java": [re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)")],
    "php": [re.compile(r"^\s*use\s+([\w\\]+)")],
    "csharp": [re.compile(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;")],
    "kotlin": [re.compile(r"^\s*import\s+([\w.]+)")],
    "swift": [re.compile(r"^\s*import\s+(\w+)")],
    "ruby": [re.compile(r"""^\s*require(?:_relative)?\s+['"]([^'"]+)['"]""")],
    "c": [re.compile(r'^\s*#\s*include\s+"([^"]+)"')],
}
for _alias, _base in (("typescript", "javascript"), ("tsx", "javascript"), ("jsx", "javascript"), ("cpp", "c"), ("scala", "kotlin")):
    _REGEX_IMPORTS[_alias] = _REGEX_IMPORTS[_base]

_CALL_RE = re.compile(r"\b([A-Za-z_][\w]*)\s*\(")
_CALL_STOP = frozenset(
    "if for while switch catch return function def fn func class new sizeof typeof await async and or not in is "
    "elif else with print super self this import from require using match case when".split()
)


def _regex_facts(content: str, lang: str | None) -> FileFacts | None:
    rules = _REGEX_RULES.get(lang or "")
    if rules is None:
        return None
    facts = FileFacts(backend="regex")
    imports = _REGEX_IMPORTS.get(lang or "", [])
    seen_calls: set[str] = set()
    declared_here: set[str] = set()
    for number, line in enumerate(content.splitlines(), start=1):
        if len(line) > 400:
            continue
        for kind, pattern in rules:
            match = pattern.match(line)
            if match and len(facts.symbols) < MAX_SYMBOLS_PER_FILE:
                name = match.group(1)
                facts.symbols.append(Symbol(name, name, kind, number, number, _clip(line.strip().rstrip("{ \t")), ""))
                declared_here.add(name)
                break
        for pattern in imports:
            match = pattern.search(line)
            if match:
                facts.imports.append(ImportRef(match.group(1).strip(), 0, (), number))
                break
        for match in _CALL_RE.finditer(line):
            name = match.group(1)
            if name not in _CALL_STOP and name not in seen_calls and name not in declared_here and len(seen_calls) < MAX_CALLS_PER_FILE:
                seen_calls.add(name)
                facts.calls.append((MODULE_SCOPE, name))
    return facts


# --------------------------------------------------------------------- entry

_LANG_ALIAS = {"js": "javascript", "ts": "typescript", "c++": "cpp", "c#": "csharp", "golang": "go"}


def extract_facts(content: str, lang: str | None) -> FileFacts:
    """Symbols, imports and calls for one file. Never raises."""
    lang = _LANG_ALIAS.get((lang or "").lower(), (lang or "").lower()) or None
    try:
        if lang == "python":
            facts = _python_facts(content)
            if facts is not None:
                return facts
            return FileFacts()
        facts = _tree_sitter_facts(content, lang)
        if facts is not None:
            return facts
        facts = _regex_facts(content, lang)
        if facts is not None:
            return facts
    except Exception:
        pass
    return FileFacts()

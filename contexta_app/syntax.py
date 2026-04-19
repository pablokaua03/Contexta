"""
syntax.py - Light syntax-aware helpers for multi-language symbol extraction.
"""

from __future__ import annotations

from functools import lru_cache

from tree_sitter_language_pack import get_parser


TREE_SITTER_LANGUAGE_KEYS = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "tsx": "tsx",
    "go": "go",
    "rust": "rust",
}


@lru_cache(maxsize=8)
def _get_parser(language_key: str):
    return get_parser(language_key)


def _decode(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def _first_named_child_text(node, source: bytes, child_types: set[str]) -> str | None:
    for child in node.children:
        if child.type in child_types and child.is_named:
            return _decode(child, source)
    return None


def _collect_python_symbols(root, source: bytes) -> tuple[list[str], list[str], list[str]]:
    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []

    for child in root.children:
        if child.type == "function_definition":
            name = _first_named_child_text(child, source, {"identifier"})
            if name:
                functions.append(name)
        elif child.type == "class_definition":
            name = _first_named_child_text(child, source, {"identifier"})
            if name:
                classes.append(name)
        elif child.type == "import_statement":
            for grandchild in child.children:
                if grandchild.type == "dotted_name":
                    imports.append(_decode(grandchild, source))
        elif child.type == "import_from_statement":
            for grandchild in child.children:
                if grandchild.type == "dotted_name":
                    imports.append(_decode(grandchild, source))
                    break

    return functions[:12], classes[:8], imports[:24]


def _collect_js_like_symbols(root, source: bytes) -> tuple[list[str], list[str], list[str]]:
    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []

    for child in root.children:
        if child.type in {"function_declaration"}:
            name = _first_named_child_text(child, source, {"identifier", "property_identifier"})
            if name:
                functions.append(name)
        elif child.type == "class_declaration":
            name = _first_named_child_text(child, source, {"identifier", "type_identifier"})
            if name:
                classes.append(name)
        elif child.type == "lexical_declaration":
            for grandchild in child.children:
                if grandchild.type != "variable_declarator":
                    continue
                declarator_children = [node for node in grandchild.children if node.is_named]
                if len(declarator_children) < 2:
                    continue
                identifier = declarator_children[0]
                initializer = declarator_children[1]
                if initializer.type in {"arrow_function", "function_expression"}:
                    functions.append(_decode(identifier, source))
        elif child.type == "import_statement":
            for grandchild in child.children:
                if grandchild.type == "string":
                    imports.append(_decode(grandchild, source).strip("\"'"))

    return functions[:12], classes[:8], imports[:24]


def _collect_go_symbols(root, source: bytes) -> tuple[list[str], list[str], list[str]]:
    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []

    for child in root.children:
        if child.type == "function_declaration":
            name = _first_named_child_text(child, source, {"identifier"})
            if name:
                functions.append(name)
        elif child.type == "type_declaration":
            for grandchild in child.children:
                if grandchild.type == "type_spec":
                    name = _first_named_child_text(grandchild, source, {"type_identifier", "identifier"})
                    if name:
                        classes.append(name)
        elif child.type == "import_declaration":
            for grandchild in child.children:
                if grandchild.type == "import_spec":
                    for spec_child in grandchild.children:
                        if spec_child.is_named:
                            imports.append(_decode(spec_child, source).strip("\"'"))

    return functions[:12], classes[:8], imports[:24]


def _collect_rust_symbols(root, source: bytes) -> tuple[list[str], list[str], list[str]]:
    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []

    for child in root.children:
        if child.type == "function_item":
            name = _first_named_child_text(child, source, {"identifier"})
            if name:
                functions.append(name)
        elif child.type in {"struct_item", "enum_item", "trait_item"}:
            name = _first_named_child_text(child, source, {"type_identifier", "identifier"})
            if name:
                classes.append(name)
        elif child.type == "use_declaration":
            scoped = _first_named_child_text(child, source, {"scoped_identifier", "identifier"})
            if scoped:
                imports.append(scoped)

    return functions[:12], classes[:8], imports[:24]


def extract_symbols_with_treesitter(content: str, lang: str | None) -> tuple[list[str], list[str], list[str]] | None:
    language_key = TREE_SITTER_LANGUAGE_KEYS.get(lang or "")
    if not language_key:
        return None

    try:
        parser = _get_parser(language_key)
        source = content.encode("utf-8", errors="ignore")
        tree = parser.parse(source)
    except Exception:
        return None

    root = tree.root_node
    if language_key == "python":
        return _collect_python_symbols(root, source)
    if language_key in {"javascript", "typescript", "tsx"}:
        return _collect_js_like_symbols(root, source)
    if language_key == "go":
        return _collect_go_symbols(root, source)
    if language_key == "rust":
        return _collect_rust_symbols(root, source)
    return None

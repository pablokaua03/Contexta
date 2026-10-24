"""contexta_app.engine.manifests: split out of context_engine.py. Bodies are unchanged."""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET

from contexta_app.engine.constants import (
    IDENTITY_FILE_WEIGHTS,
    IDENTITY_PREFIX_WEIGHTS,
    IDENTITY_SUFFIX_WEIGHTS,
)
from contexta_app.engine.models import (
    FileInsight,
)

def parse_json_dependencies(content: str) -> dict[str, str]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {}
    deps: dict[str, str] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies", "require", "require-dev"):
        section = payload.get(key, {})
        if isinstance(section, dict):
            deps.update({str(name).lower(): str(version) for name, version in section.items()})
    return deps

def parse_json_document(content: str) -> dict:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}

def parse_package_scripts(content: str) -> list[str]:
    payload = parse_json_document(content)
    scripts = payload.get("scripts", {})
    if not isinstance(scripts, dict):
        return []
    return [str(name) for name in scripts.keys()]

def parse_requirements_dependencies(content: str) -> set[str]:
    deps: set[str] = set()
    for line in content.splitlines():
        raw = line.split("#", 1)[0].strip()
        if not raw or raw.startswith(("-", "--")):
            continue
        token = re.split(r"[<>=!~;\[]", raw, maxsplit=1)[0].strip()
        if token:
            deps.add(token.lower())
    return deps

def parse_pyproject_dependencies(content: str) -> set[str]:
    deps: set[str] = set()
    for match in re.finditer(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL | re.IGNORECASE):
        for raw_dep in re.findall(r'["\']([^"\']+)["\']', match.group(1)):
            token = re.split(r"[<>=!~;\[]", raw_dep, maxsplit=1)[0].strip()
            if token:
                deps.add(token.lower())
    poetry_block = re.search(r"\[tool\.poetry\.dependencies\](.*?)(?:\n\[|$)", content, re.DOTALL | re.IGNORECASE)
    if poetry_block:
        for name in re.findall(r"^\s*([A-Za-z0-9_.-]+)\s*=", poetry_block.group(1), re.MULTILINE):
            if name.lower() != "python":
                deps.add(name.lower())
    return deps

def parse_pyproject_document(content: str) -> dict:
    try:
        payload = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}

def parse_pyproject_scripts(content: str) -> list[str]:
    payload = parse_pyproject_document(content)
    scripts: list[str] = []
    project = payload.get("project", {})
    if isinstance(project, dict) and isinstance(project.get("scripts"), dict):
        scripts.extend(str(name) for name in project["scripts"].keys())
    tool = payload.get("tool", {})
    poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
    if isinstance(poetry, dict) and isinstance(poetry.get("scripts"), dict):
        scripts.extend(str(name) for name in poetry["scripts"].keys())
    return list(dict.fromkeys(scripts))

def parse_go_mod_dependencies(content: str) -> set[str]:
    deps: set[str] = set()
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("require "):
            module = line.split()[1] if len(line.split()) > 1 else ""
            if module:
                deps.add(module.lower())
    for module in re.findall(r"^\s*([A-Za-z0-9\./_-]+)\s+v[0-9]", content, re.MULTILINE):
        deps.add(module.lower())
    return deps

def parse_gemfile_dependencies(content: str) -> set[str]:
    deps: set[str] = set()
    for gem_name in re.findall(r"""^\s*gem\s+['"]([^'"]+)['"]""", content, re.MULTILINE):
        deps.add(gem_name.lower())
    return deps

def parse_mix_dependencies(content: str) -> set[str]:
    deps: set[str] = set()
    for dep_name in re.findall(r"\{\s*:([a-zA-Z0-9_]+)\s*,", content):
        deps.add(dep_name.lower())
    return deps

def parse_pubspec_dependencies(content: str) -> set[str]:
    deps: set[str] = set()
    in_dependencies = False
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^[A-Za-z0-9_-]+:\s*$", line) and not line.startswith("  "):
            in_dependencies = stripped.startswith(("dependencies:", "dev_dependencies:"))
            continue
        if in_dependencies and line.startswith("  "):
            name = stripped.split(":", 1)[0].strip()
            if name:
                deps.add(name.lower())
        elif not line.startswith("  "):
            in_dependencies = False
    return deps

def parse_gradle_dependencies(content: str) -> set[str]:
    deps: set[str] = set()
    for raw_dep in re.findall(r"""['"]([A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+(?::[A-Za-z0-9+_.-]+)?)['"]""", content):
        parts = raw_dep.split(":")
        if len(parts) >= 2:
            group = parts[0].lower()
            artifact = parts[1].lower()
            deps.add(artifact)
            deps.add(f"{group}:{artifact}")
    return deps

def parse_gradle_scripts(content: str) -> list[str]:
    scripts: list[str] = []
    scripts.extend(re.findall(r"^\s*task\s+([A-Za-z_][A-Za-z0-9_]*)", content, re.MULTILINE))
    scripts.extend(re.findall(r"""tasks\.register\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""", content))
    return list(dict.fromkeys(scripts))

def parse_toml_section_keys(content: str, section_name: str) -> set[str]:
    match = re.search(rf"\[{re.escape(section_name)}\](.*?)(?:\n\[|$)", content, re.DOTALL | re.IGNORECASE)
    if not match:
        return set()
    return {
        name.lower()
        for name in re.findall(r"^\s*([A-Za-z0-9_.-]+)\s*=", match.group(1), re.MULTILINE)
    }

def parse_cargo_document(content: str) -> dict:
    try:
        payload = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}

def parse_xml_package_references(content: str) -> set[str]:
    return {
        value.lower()
        for value in re.findall(r'PackageReference[^>]+Include="([^"]+)"', content, re.IGNORECASE)
    } | {
        value.lower()
        for value in re.findall(r"<artifactId>([^<]+)</artifactId>", content, re.IGNORECASE)
    }

def parse_xml_document(content: str) -> ET.Element | None:
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        return None

def parse_csproj_scripts(content: str) -> list[str]:
    root = parse_xml_document(content)
    if root is None:
        return []
    commands: list[str] = []
    for tag in ("Target", "Exec"):
        for node in root.iter():
            if node.tag.endswith(tag):
                name = node.attrib.get("Name") or node.attrib.get("Command")
                if name:
                    commands.append(str(name))
    return list(dict.fromkeys(commands))

def parse_pom_scripts(content: str) -> list[str]:
    root = parse_xml_document(content)
    if root is None:
        return []
    scripts: list[str] = []
    for node in root.iter():
        if node.tag.endswith("goal") and node.text:
            scripts.append(node.text.strip())
    return list(dict.fromkeys(filter(None, scripts)))

def parse_manifest_scripts(item: FileInsight) -> list[str]:
    name = item.path.name.lower()
    if name in {"package.json", "composer.json"}:
        return parse_package_scripts(item.content)
    if name == "pyproject.toml":
        return parse_pyproject_scripts(item.content)
    if name in {"build.gradle", "build.gradle.kts"}:
        return parse_gradle_scripts(item.content)
    if name.endswith(".csproj"):
        return parse_csproj_scripts(item.content)
    if name == "pom.xml":
        return parse_pom_scripts(item.content)
    return []

def get_dependency_names(item: FileInsight) -> set[str]:
    name = item.path.name.lower()
    if name in {"package.json", "composer.json"}:
        return set(parse_json_dependencies(item.content))
    if name == "gemfile":
        return parse_gemfile_dependencies(item.content)
    if name == "requirements.txt":
        return parse_requirements_dependencies(item.content)
    if name == "pyproject.toml":
        return parse_pyproject_dependencies(item.content)
    if name == "mix.exs":
        return parse_mix_dependencies(item.content)
    if name in {"pubspec.yaml", "pubspec.yml"}:
        return parse_pubspec_dependencies(item.content)
    if name == "cargo.toml":
        return parse_toml_section_keys(item.content, "dependencies") | parse_toml_section_keys(item.content, "dev-dependencies")
    if name == "go.mod":
        return parse_go_mod_dependencies(item.content)
    if name in {"build.gradle", "build.gradle.kts"}:
        return parse_gradle_dependencies(item.content)
    if name == "pom.xml" or name.endswith(".csproj"):
        return parse_xml_package_references(item.content)
    return set()

def identity_weight_for(item: FileInsight) -> tuple[float, str | None]:
    name = item.path.name.lower()
    if name in IDENTITY_FILE_WEIGHTS:
        return IDENTITY_FILE_WEIGHTS[name]
    for suffix, payload in IDENTITY_SUFFIX_WEIGHTS.items():
        if name.endswith(suffix):
            return payload
    for prefix, payload in IDENTITY_PREFIX_WEIGHTS.items():
        if name.startswith(prefix):
            return payload
    return 0.0, None

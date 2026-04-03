"""Plugin-related data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GeneratorResult:
    """Result of a generator plugin invocation."""

    path: Path | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    success: bool = True
    error_message: str = ""


@dataclass(frozen=True)
class PluginInfo:
    """Metadata about a discovered plugin."""

    name: str = ""
    entry_point: str = ""
    package: str = ""
    capabilities: list[str] = field(default_factory=list)
    enabled: bool = False


@dataclass(frozen=True)
class RegistryEntry:
    """A plugin entry from the remote registry."""

    name: str = ""
    package: str = ""
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    homepage: str = ""
    min_reeln_version: str = ""
    author: str = ""
    license: str = ""
    input_contributions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginStatus:
    """Unified view merging registry info + installed state."""

    name: str = ""
    installed: bool = False
    installed_version: str = ""
    available_version: str = ""
    package: str = ""
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    enabled: bool = False
    update_available: bool = False
    homepage: str = ""


def _parse_string_list(value: object) -> list[str]:
    """Safely parse an object into a list of strings."""
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _parse_input_contributions(data: dict[str, object]) -> dict[str, list[dict[str, Any]]]:
    """Extract ``input_fields`` from ``ui_contributions``.

    Returns ``{command: [field_dict, ...]}`` mapping.
    """
    ui = data.get("ui_contributions")
    if not isinstance(ui, dict):
        return {}
    raw = ui.get("input_fields")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for command, fields in raw.items():
        if isinstance(fields, list):
            result[str(command)] = [dict(f) for f in fields if isinstance(f, dict)]
    return result


def dict_to_registry_entry(data: dict[str, object]) -> RegistryEntry:
    """Deserialize a dict into a ``RegistryEntry``, ignoring unknown keys."""
    return RegistryEntry(
        name=str(data.get("name", "")),
        package=str(data.get("package", "")),
        description=str(data.get("description", "")),
        capabilities=_parse_string_list(data.get("capabilities")),
        homepage=str(data.get("homepage", "")),
        min_reeln_version=str(data.get("min_reeln_version", "")),
        author=str(data.get("author", "")),
        license=str(data.get("license", "")),
        input_contributions=_parse_input_contributions(data),
    )


def registry_entry_to_dict(entry: RegistryEntry) -> dict[str, object]:
    """Serialize a ``RegistryEntry`` to a JSON-compatible dict."""
    d: dict[str, object] = {
        "name": entry.name,
        "package": entry.package,
        "description": entry.description,
        "capabilities": list(entry.capabilities),
        "homepage": entry.homepage,
        "min_reeln_version": entry.min_reeln_version,
        "author": entry.author,
        "license": entry.license,
    }
    if entry.input_contributions:
        d["input_contributions"] = dict(entry.input_contributions)
    return d


@dataclass
class OrchestrationConfig:
    """Configuration for the plugin orchestration pipeline."""

    upload_bitrate_kbps: int = 0
    sequential: bool = True

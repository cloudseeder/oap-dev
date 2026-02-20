"""Convert OAP manifests to Ollama tool definitions."""

from __future__ import annotations

import re
from typing import Any

from .tool_models import (
    Tool,
    ToolFunction,
    ToolParameter,
    ToolParameters,
    ToolRegistryEntry,
)


def manifest_to_tool_name(name: str) -> str:
    """Convert a manifest name to an Ollama tool name.

    Lowercase, replace non-alphanumeric with underscore, prefix with oap_.
    Collapse consecutive underscores and strip leading/trailing underscores.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"oap_{slug}"


def _extract_json_fields(description: str) -> list[str]:
    """Extract quoted field names from an input description.

    Looks for patterns like 'field_name' (single-quoted words) in descriptions
    of JSON inputs to build parameter schemas.
    """
    return re.findall(r"'([a-z][a-z0-9_]*)'", description)


def _build_parameters(manifest: dict[str, Any]) -> ToolParameters:
    """Build JSON Schema parameters from a manifest's input spec.

    Heuristics:
    - text/plain -> {input: string}
    - application/json with quoted fields in description -> extracted fields
    - application/json without parseable fields -> {data: string}
    - stdio method -> {args: string}
    - No input spec -> {input: string}
    """
    invoke = manifest.get("invoke", {})
    method = invoke.get("method", "").upper()
    input_spec = manifest.get("input")

    # stdio commands get an args parameter
    if method == "STDIO":
        desc = input_spec["description"] if input_spec else "Command arguments"
        return ToolParameters(
            properties={"args": ToolParameter(type="string", description=desc)},
            required=["args"],
        )

    if input_spec is None:
        return ToolParameters(
            properties={
                "input": ToolParameter(
                    type="string",
                    description=f"Input for {manifest.get('name', 'this tool')}",
                ),
            },
            required=["input"],
        )

    fmt = input_spec.get("format", "")
    desc = input_spec.get("description", "")

    if "json" in fmt:
        # Try to extract field names from the description
        fields = _extract_json_fields(desc)
        if fields:
            props = {f: ToolParameter(type="string", description=f"The '{f}' value") for f in fields}
            return ToolParameters(properties=props, required=fields)
        # Fallback: generic data parameter
        return ToolParameters(
            properties={"data": ToolParameter(type="string", description=desc)},
            required=["data"],
        )

    # text/plain and everything else
    return ToolParameters(
        properties={"input": ToolParameter(type="string", description=desc)},
        required=["input"],
    )


def manifest_to_tool(domain: str, manifest: dict[str, Any]) -> ToolRegistryEntry:
    """Convert a manifest to an Ollama tool definition with registry metadata."""
    name = manifest_to_tool_name(manifest["name"])
    parameters = _build_parameters(manifest)

    tool = Tool(
        function=ToolFunction(
            name=name,
            description=manifest["description"],
            parameters=parameters,
        )
    )

    return ToolRegistryEntry(
        tool=tool,
        domain=domain,
        manifest=manifest,
    )

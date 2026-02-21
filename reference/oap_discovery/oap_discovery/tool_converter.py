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

    Looks for patterns like 'field_name' or "field_name" (single- or
    double-quoted words) in descriptions of JSON inputs to build
    parameter schemas.
    """
    # Single-quoted fields
    fields = re.findall(r"'([a-z][a-z0-9_]*)'", description)
    if fields:
        return fields
    # Double-quoted fields
    return re.findall(r'"([a-z][a-z0-9_]*)"', description)


def _extract_example_fields(manifest: dict[str, Any]) -> list[str]:
    """Extract field names from a manifest's example inputs.

    Collects all keys from example input dicts, which represent the
    actual JSON fields the API accepts.
    """
    examples = manifest.get("examples")
    if not examples or not isinstance(examples, list):
        return []
    fields: set[str] = set()
    for ex in examples:
        inp = ex.get("input") if isinstance(ex, dict) else None
        if isinstance(inp, dict):
            fields.update(inp.keys())
    return sorted(fields)


def _build_parameters_from_spec(
    parameters: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> ToolParameters:
    """Build ToolParameters from a manifest's structured input.parameters.

    When a manifest provides explicit parameter definitions in
    input.parameters, use them as the base.  Additionally extracts
    field names from examples to fill in parameters that the manifest
    author didn't define explicitly (e.g. ``intent``, ``limit``).
    """
    props: dict[str, ToolParameter] = {}
    required: list[str] = []

    for name, schema in parameters.items():
        param_type = schema.get("type", "string")
        param_desc = schema.get("description", "")
        props[name] = ToolParameter(type=param_type, description=param_desc)
        if schema.get("required", True):
            required.append(name)

    # Supplement with fields found in examples
    if manifest is not None:
        for field in _extract_example_fields(manifest):
            if field not in props:
                props[field] = ToolParameter(
                    type="string",
                    description=f"The '{field}' value (see examples)",
                )

    return ToolParameters(properties=props, required=required)


def _build_parameters(manifest: dict[str, Any]) -> ToolParameters:
    """Build JSON Schema parameters from a manifest's input spec.

    Priority:
    1. Structured input.parameters (explicit schema from manifest)
    2. Quoted field names extracted from description (heuristic)
    3. Generic fallback ({data: string} for JSON, {input: string} for text)

    Special cases:
    - stdio method -> {args: string}
    - No input spec -> {input: string}
    """
    invoke = manifest.get("invoke", {})
    method = invoke.get("method", "").upper()
    input_spec = manifest.get("input")

    # stdio commands get stdin (piped input) and args (flags/arguments)
    if method == "STDIO":
        input_desc = input_spec["description"] if input_spec else ""
        return ToolParameters(
            properties={
                "stdin": ToolParameter(
                    type="string",
                    description=input_desc or "Data to provide on standard input",
                ),
                "args": ToolParameter(
                    type="string",
                    description="Command-line flags and arguments (e.g. '-w', '-l')",
                ),
            },
            required=[],
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

    # Use structured parameters if the manifest provides them
    structured_params = input_spec.get("parameters")
    if structured_params and isinstance(structured_params, dict):
        return _build_parameters_from_spec(structured_params, manifest)

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

"""Manifest validation for OAP v1.0."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Manifest


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_manifest(data: dict[str, Any]) -> ValidationResult:
    """Validate a manifest dict against v1.0 rules.

    Returns a ValidationResult with errors (fatal) and warnings (advisory).
    """
    result = ValidationResult()

    # Check required fields exist
    for key in ("oap", "name", "description", "invoke"):
        if key not in data:
            result.errors.append(f"Missing required field: {key}")

    if result.errors:
        result.valid = False
        return result

    # Check oap version
    if data["oap"] != "1.0":
        result.errors.append(f"Unsupported oap version: {data['oap']} (expected 1.0)")

    # Check invoke has required subfields
    invoke = data.get("invoke", {})
    if not isinstance(invoke, dict):
        result.errors.append("invoke must be an object")
    else:
        if "method" not in invoke:
            result.errors.append("invoke.method is required")
        if "url" not in invoke:
            result.errors.append("invoke.url is required")

    # Warnings for missing recommended fields
    if "input" not in data:
        result.warnings.append("Missing recommended field: input")
    if "output" not in data:
        result.warnings.append("Missing recommended field: output")

    # Warn on long descriptions
    desc = data.get("description", "")
    if len(desc) > 1000:
        result.warnings.append(f"Description is {len(desc)} chars (recommended max 1000)")

    if result.errors:
        result.valid = False

    return result


def parse_manifest(data: dict[str, Any]) -> Manifest:
    """Parse and validate a manifest dict, returning a Manifest model.

    Raises ValueError if validation fails.
    """
    result = validate_manifest(data)
    if not result.valid:
        raise ValueError(f"Invalid manifest: {'; '.join(result.errors)}")
    return Manifest.model_validate(data)

"""Layer 2 capability testing — verify that a manifest does what it claims."""

from __future__ import annotations

import logging

import httpx

from .config import AttestationConfig
from .manifest import _validate_url
from .models import CapabilityTestResult

log = logging.getLogger("oap.trust.capability")

TIMEOUT = 10.0


async def test_capability(
    manifest: dict,
    cfg: AttestationConfig,
    *,
    allow_http: bool = False,
) -> CapabilityTestResult:
    """Run Layer 2 capability tests against a manifest's invoke endpoint."""
    errors: list[str] = []
    invoke = manifest.get("invoke", {})
    url = invoke.get("url")
    method = invoke.get("method", "GET").upper()

    # Skip stdio invocations — can't test from a trust provider
    if method == "stdio":
        return CapabilityTestResult(
            endpoint_live=False,
            passed=False,
            errors=["Cannot test stdio invocations remotely"],
        )

    if not url:
        return CapabilityTestResult(
            endpoint_live=False,
            passed=False,
            errors=["No invoke URL in manifest"],
        )

    # SSRF protection
    try:
        _validate_url(url, allow_http=allow_http)
    except ValueError as e:
        return CapabilityTestResult(
            endpoint_live=False,
            passed=False,
            errors=[f"Invoke URL failed safety check: {e}"],
        )

    # Skip auth-gated endpoints — we can't test them without credentials
    auth = invoke.get("auth")
    if auth and auth != "none":
        return CapabilityTestResult(
            endpoint_live=False,
            passed=False,
            errors=[f"Cannot test auth-gated endpoint (auth: {auth})"],
        )

    result = CapabilityTestResult(
        endpoint_live=False,
        passed=False,
    )

    async with httpx.AsyncClient() as client:
        # Test 1: Endpoint liveness
        try:
            if method in ("GET", "HEAD"):
                resp = await client.get(
                    url,
                    timeout=TIMEOUT,
                    headers={"User-Agent": "OAP-Trust/0.1"},
                    follow_redirects=True,
                )
            else:
                # For POST/PUT/etc, send a HEAD-like request first
                resp = await client.head(
                    url,
                    timeout=TIMEOUT,
                    headers={"User-Agent": "OAP-Trust/0.1"},
                    follow_redirects=True,
                )
            # Accept any non-5xx response as "live"
            result.endpoint_live = resp.status_code < 500
            if not result.endpoint_live:
                errors.append(f"Endpoint returned {resp.status_code}")
        except httpx.RequestError as e:
            errors.append(f"Endpoint unreachable: {e}")

        # Test 2: Health endpoint (if declared)
        health_url = manifest.get("health")
        if health_url:
            try:
                _validate_url(health_url, allow_http=allow_http)
                health_resp = await client.get(
                    health_url,
                    timeout=TIMEOUT,
                    headers={"User-Agent": "OAP-Trust/0.1"},
                    follow_redirects=True,
                )
                result.health_ok = health_resp.status_code < 400
                if not result.health_ok:
                    errors.append(f"Health endpoint returned {health_resp.status_code}")
            except (httpx.RequestError, ValueError) as e:
                result.health_ok = False
                errors.append(f"Health check failed: {e}")

        # Test 3: Example invocation (if examples provided)
        examples = manifest.get("examples", [])
        if examples and result.endpoint_live:
            example = examples[0]
            example_input = example.get("input")
            try:
                if method == "POST" and example_input is not None:
                    # Determine content type
                    input_spec = manifest.get("input", {})
                    content_type = input_spec.get("format", "application/json")

                    headers = {"User-Agent": "OAP-Trust/0.1"}
                    if "json" in content_type:
                        resp = await client.post(
                            url,
                            json=example_input,
                            timeout=TIMEOUT,
                            headers=headers,
                            follow_redirects=True,
                        )
                    else:
                        headers["Content-Type"] = content_type
                        resp = await client.post(
                            url,
                            content=str(example_input).encode() if not isinstance(example_input, bytes) else example_input,
                            timeout=TIMEOUT,
                            headers=headers,
                            follow_redirects=True,
                        )

                    result.example_passed = resp.status_code < 400
                    if not result.example_passed:
                        errors.append(f"Example invocation returned {resp.status_code}")

                    # Check output format if specified
                    output_spec = manifest.get("output", {})
                    expected_format = output_spec.get("format")
                    if expected_format and result.example_passed:
                        actual_ct = resp.headers.get("content-type", "")
                        # Loose match — "application/json" matches "application/json; charset=utf-8"
                        result.format_match = expected_format.split(";")[0] in actual_ct
                        if not result.format_match:
                            errors.append(
                                f"Output format mismatch: expected {expected_format}, "
                                f"got {actual_ct}"
                            )

                elif method == "GET":
                    resp = await client.get(
                        url,
                        timeout=TIMEOUT,
                        headers={"User-Agent": "OAP-Trust/0.1"},
                        follow_redirects=True,
                    )
                    result.example_passed = resp.status_code < 400
                    if not result.example_passed:
                        errors.append(f"GET invocation returned {resp.status_code}")
            except httpx.RequestError as e:
                result.example_passed = False
                errors.append(f"Example invocation failed: {e}")

    result.errors = errors
    result.passed = result.endpoint_live and (result.health_ok is not False)
    return result

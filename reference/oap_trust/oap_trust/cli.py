"""CLI for OAP trust provider — talks to the FastAPI service."""

from __future__ import annotations

import json
import sys

import click
import httpx

DEFAULT_API = "http://localhost:8301"


def _api_url(ctx: click.Context) -> str:
    return ctx.obj.get("api_url", DEFAULT_API)


@click.group()
@click.option("--api", "api_url", default=DEFAULT_API, envvar="OAP_TRUST_API_URL", help="API base URL")
@click.pass_context
def cli(ctx: click.Context, api_url: str) -> None:
    """OAP Trust CLI — domain and capability attestation for OAP manifests."""
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url.rstrip("/")


@cli.command()
@click.argument("domain")
@click.option("--method", default="dns", type=click.Choice(["dns", "http"]), help="Challenge method")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output raw JSON")
@click.pass_context
def attest(ctx: click.Context, domain: str, method: str, as_json: bool) -> None:
    """Initiate domain attestation for a domain.

    Example: oap-trust attest example.com
    """
    base = _api_url(ctx)
    try:
        resp = httpx.post(
            f"{base}/v1/attest/domain",
            json={"domain": domain, "method": method},
            timeout=30.0,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        click.echo("Is the API running? Start it with: oap-trust-api", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.status_code} — {e.response.json().get('detail', e.response.text)}", err=True)
        sys.exit(1)

    data = resp.json()

    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    click.echo(f"\nLayer 0 checks: {'PASSED' if data['layer0']['passed'] else 'FAILED'}")
    if data["layer0"]["errors"]:
        for err in data["layer0"]["errors"]:
            click.echo(f"  ! {err}")

    click.echo(f"\nChallenge issued (method: {data['method']})")
    click.echo(f"\n{data['instructions']}")


@cli.command()
@click.argument("domain")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output raw JSON")
@click.pass_context
def verify(ctx: click.Context, domain: str, as_json: bool) -> None:
    """Check domain challenge status and retrieve attestation.

    Example: oap-trust verify example.com
    """
    base = _api_url(ctx)
    try:
        resp = httpx.get(
            f"{base}/v1/attest/domain/{domain}/status",
            timeout=30.0,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.status_code} — {e.response.text}", err=True)
        sys.exit(1)

    data = resp.json()

    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    if data["challenge_verified"]:
        click.echo(f"\nDomain verified: {domain}")
        if data.get("attestation"):
            att = data["attestation"]
            click.echo(f"  Layer:   {att['layer']}")
            click.echo(f"  Issued:  {att['issued_at']}")
            click.echo(f"  Expires: {att['expires_at']}")
            click.echo(f"  Hash:    {att['manifest_hash']}")
    else:
        click.echo(f"\nChallenge not yet verified for {domain}")
        if data.get("error"):
            click.echo(f"  {data['error']}")


@cli.command("test-capability")
@click.argument("domain")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output raw JSON")
@click.pass_context
def test_capability(ctx: click.Context, domain: str, as_json: bool) -> None:
    """Run Layer 2 capability tests for a domain.

    Example: oap-trust test-capability example.com
    """
    base = _api_url(ctx)
    try:
        resp = httpx.post(
            f"{base}/v1/attest/capability",
            json={"domain": domain},
            timeout=30.0,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.status_code} — {e.response.text}", err=True)
        sys.exit(1)

    data = resp.json()

    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    tr = data["test_result"]
    click.echo(f"\nCapability test: {'PASSED' if tr['passed'] else 'FAILED'}")
    click.echo(f"  Endpoint live: {tr['endpoint_live']}")
    if tr.get("health_ok") is not None:
        click.echo(f"  Health OK:     {tr['health_ok']}")
    if tr.get("format_match") is not None:
        click.echo(f"  Format match:  {tr['format_match']}")
    if tr.get("example_passed") is not None:
        click.echo(f"  Example pass:  {tr['example_passed']}")
    if tr["errors"]:
        for err in tr["errors"]:
            click.echo(f"  ! {err}")

    if data.get("attestation"):
        att = data["attestation"]
        click.echo(f"\n  Attestation issued (Layer {att['layer']})")
        click.echo(f"  Expires: {att['expires_at']}")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Check trust API health."""
    base = _api_url(ctx)
    try:
        resp = httpx.get(f"{base}/health", timeout=10.0)
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)

    data = resp.json()
    click.echo(f"Status:       {data['status']}")
    click.echo(f"Key loaded:   {data['key_loaded']}")
    click.echo(f"Attestations: {data['attestation_count']} active")


@cli.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output raw JSON")
@click.pass_context
def keys(ctx: click.Context, as_json: bool) -> None:
    """Fetch JWKS public keys from the trust provider."""
    base = _api_url(ctx)
    try:
        resp = httpx.get(f"{base}/v1/keys", timeout=10.0)
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)

    data = resp.json()

    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    for key in data.get("keys", []):
        click.echo(f"  Key ID:    {key.get('kid')}")
        click.echo(f"  Algorithm: {key.get('alg')}")
        click.echo(f"  Curve:     {key.get('crv')}")
        click.echo(f"  Use:       {key.get('use')}")


if __name__ == "__main__":
    cli()

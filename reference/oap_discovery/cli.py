"""CLI for OAP discovery — talks to the FastAPI service."""

from __future__ import annotations

import json
import sys

import click
import httpx

DEFAULT_API = "http://localhost:8300"


def _api_url(ctx: click.Context) -> str:
    return ctx.obj.get("api_url", DEFAULT_API)


@click.group()
@click.option("--api", "api_url", default=DEFAULT_API, envvar="OAP_API_URL", help="API base URL")
@click.pass_context
def cli(ctx: click.Context, api_url: str) -> None:
    """OAP Discovery CLI — find capabilities by describing what you need."""
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url.rstrip("/")


@cli.command()
@click.argument("task")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output raw JSON")
@click.option("--top-k", default=5, help="Number of candidates to consider")
@click.pass_context
def discover(ctx: click.Context, task: str, as_json: bool, top_k: int) -> None:
    """Discover the best capability for a task.

    Example: oap discover "search text files for a regex pattern"
    """
    base = _api_url(ctx)
    try:
        resp = httpx.post(
            f"{base}/v1/discover",
            json={"task": task, "top_k": top_k},
            timeout=60.0,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        click.echo("Is the API running? Start it with: oap-api", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.status_code} {e.response.text}", err=True)
        sys.exit(1)

    data = resp.json()

    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    match = data.get("match")
    if not match:
        click.echo("No matching capability found.")
        return

    click.echo(f"\nBest match: {match['name']}")
    click.echo(f"  Domain:  {match['domain']}")
    click.echo(f"  Score:   {match['score']:.4f}")
    click.echo(f"  Invoke:  {match['invoke']['method']} {match['invoke']['url']}")
    if match.get("reason"):
        click.echo(f"  Reason:  {match['reason']}")
    click.echo(f"\n  {match['description']}")

    candidates = data.get("candidates", [])
    if len(candidates) > 1:
        click.echo(f"\nOther candidates ({len(candidates) - 1}):")
        for c in candidates:
            if c["domain"] != match["domain"]:
                click.echo(f"  - {c['name']} [{c['domain']}] (score: {c['score']:.4f})")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Check API and Ollama health."""
    base = _api_url(ctx)
    try:
        resp = httpx.get(f"{base}/health", timeout=10.0)
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)

    data = resp.json()
    click.echo(f"Status:    {data['status']}")
    click.echo(f"Ollama:    {'connected' if data['ollama'] else 'not connected'}")
    click.echo(f"Manifests: {data['index_count']} indexed")


@cli.command("list-manifests")
@click.pass_context
def list_manifests(ctx: click.Context) -> None:
    """List all indexed manifests."""
    base = _api_url(ctx)
    try:
        resp = httpx.get(f"{base}/v1/manifests", timeout=10.0)
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)

    entries = resp.json()
    if not entries:
        click.echo("No manifests indexed.")
        return

    for e in entries:
        click.echo(f"  {e['name']:30s}  [{e['domain']}]")
    click.echo(f"\n{len(entries)} manifests indexed")


if __name__ == "__main__":
    cli()

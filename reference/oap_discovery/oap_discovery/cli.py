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


@cli.group()
@click.pass_context
def experience(ctx: click.Context) -> None:
    """Procedural memory experience cache commands."""
    pass


@experience.command("invoke")
@click.argument("task")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output raw JSON")
@click.option("--threshold", default=0.85, type=float, help="Confidence threshold for cache hit")
@click.option("--top-k", default=5, help="Number of candidates for discovery")
@click.pass_context
def experience_invoke(ctx: click.Context, task: str, as_json: bool, threshold: float, top_k: int) -> None:
    """Run experience-augmented discovery + invocation for a task.

    Example: oap experience invoke "search text files for a regex pattern"
    """
    base = _api_url(ctx)
    try:
        resp = httpx.post(
            f"{base}/v1/experience/invoke",
            json={"task": task, "confidence_threshold": threshold, "top_k": top_k},
            timeout=120.0,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.status_code} {e.response.text}", err=True)
        sys.exit(1)

    data = resp.json()

    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    route = data.get("route", {})
    click.echo(f"\nRoute: {route.get('path', 'unknown')}")
    if route.get("cache_confidence"):
        click.echo(f"  Cache confidence: {route['cache_confidence']:.4f}")
    if route.get("experience_id"):
        click.echo(f"  Experience ID: {route['experience_id']}")

    match = data.get("match")
    if match:
        click.echo(f"\nMatch: {match['name']}")
        click.echo(f"  Domain: {match['domain']}")
        click.echo(f"  Invoke: {match['invoke']['method']} {match['invoke']['url']}")
        if match.get("reason"):
            click.echo(f"  Reason: {match['reason']}")

    result = data.get("invocation_result")
    if result:
        click.echo(f"\nInvocation: {result['status']}")
        if result.get("http_code") is not None:
            click.echo(f"  Code: {result['http_code']}")
        click.echo(f"  Latency: {result.get('latency_ms', 0)}ms")
        if result.get("error"):
            click.echo(f"  Error: {result['error']}")
        if result.get("response_body"):
            body = result["response_body"]
            if len(body) > 200:
                body = body[:200] + "..."
            click.echo(f"\n  Response:\n  {body}")


@experience.command("list")
@click.option("--page", default=1, help="Page number")
@click.option("--limit", default=20, help="Records per page")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output raw JSON")
@click.pass_context
def experience_list(ctx: click.Context, page: int, limit: int, as_json: bool) -> None:
    """List cached experience records."""
    base = _api_url(ctx)
    try:
        resp = httpx.get(
            f"{base}/v1/experience/records",
            params={"page": page, "limit": limit},
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.status_code} {e.response.text}", err=True)
        sys.exit(1)

    data = resp.json()

    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    records = data.get("records", [])
    if not records:
        click.echo("No experience records.")
        return

    for r in records:
        intent = r.get("intent", {})
        discovery = r.get("discovery", {})
        outcome = r.get("outcome", {})
        click.echo(
            f"  {r['id']:30s}  {intent.get('fingerprint', ''):30s}  "
            f"{discovery.get('manifest_matched', ''):15s}  "
            f"{outcome.get('status', ''):7s}  "
            f"uses={r.get('use_count', 0)}"
        )

    click.echo(f"\n{data.get('total', 0)} total records (page {data.get('page', 1)})")


@experience.command("show")
@click.argument("experience_id")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output raw JSON")
@click.pass_context
def experience_show(ctx: click.Context, experience_id: str, as_json: bool) -> None:
    """Show a specific experience record."""
    base = _api_url(ctx)
    try:
        resp = httpx.get(f"{base}/v1/experience/records/{experience_id}", timeout=10.0)
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.status_code} {e.response.text}", err=True)
        sys.exit(1)

    data = resp.json()

    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    click.echo(f"\nExperience: {data['id']}")
    click.echo(f"  Created:  {data['timestamp']}")
    click.echo(f"  Uses:     {data['use_count']}")
    click.echo(f"  Last used: {data['last_used']}")

    intent = data.get("intent", {})
    click.echo(f"\nIntent:")
    click.echo(f"  Raw:         {intent.get('raw', '')}")
    click.echo(f"  Fingerprint: {intent.get('fingerprint', '')}")
    click.echo(f"  Domain:      {intent.get('domain', '')}")

    disc = data.get("discovery", {})
    click.echo(f"\nDiscovery:")
    click.echo(f"  Manifest: {disc.get('manifest_matched', '')}")
    click.echo(f"  Confidence: {disc.get('confidence', 0):.4f}")

    inv = data.get("invocation", {})
    click.echo(f"\nInvocation:")
    click.echo(f"  Endpoint: {inv.get('endpoint', '')}")
    click.echo(f"  Method:   {inv.get('method', '')}")
    params = inv.get("parameter_mapping", {})
    if params:
        click.echo(f"  Parameters:")
        for name, mapping in params.items():
            click.echo(f"    {name}: {mapping.get('value_used', '')} (source: {mapping.get('source', '')})")

    outcome = data.get("outcome", {})
    click.echo(f"\nOutcome:")
    click.echo(f"  Status:  {outcome.get('status', '')}")
    if outcome.get("http_code") is not None:
        click.echo(f"  Code:    {outcome['http_code']}")
    click.echo(f"  Latency: {outcome.get('latency_ms', 0)}ms")
    click.echo(f"  Summary: {outcome.get('response_summary', '')}")


@experience.command("delete")
@click.argument("experience_id")
@click.pass_context
def experience_delete(ctx: click.Context, experience_id: str) -> None:
    """Delete an experience record."""
    base = _api_url(ctx)
    try:
        resp = httpx.delete(f"{base}/v1/experience/records/{experience_id}", timeout=10.0)
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.status_code} {e.response.text}", err=True)
        sys.exit(1)

    click.echo(f"Deleted: {experience_id}")


@experience.command("stats")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output raw JSON")
@click.pass_context
def experience_stats(ctx: click.Context, as_json: bool) -> None:
    """Show experience cache statistics."""
    base = _api_url(ctx)
    try:
        resp = httpx.get(f"{base}/v1/experience/stats", timeout=10.0)
        resp.raise_for_status()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to API at {base}", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.status_code} {e.response.text}", err=True)
        sys.exit(1)

    data = resp.json()

    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    click.echo(f"Experience Records: {data.get('total', 0)}")
    click.echo(f"Avg Confidence:     {data.get('avg_confidence', 0):.4f}")
    click.echo(f"Success Rate:       {data.get('success_rate', 0):.1%}")

    top_domains = data.get("top_domains", [])
    if top_domains:
        click.echo(f"\nTop Domains:")
        for d in top_domains:
            click.echo(f"  {d['domain']:30s}  {d['count']} records")

    top_manifests = data.get("top_manifests", [])
    if top_manifests:
        click.echo(f"\nTop Manifests:")
        for m in top_manifests:
            click.echo(f"  {m['manifest']:30s}  {m['count']} records")


if __name__ == "__main__":
    cli()

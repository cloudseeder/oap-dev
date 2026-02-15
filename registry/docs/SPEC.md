# Open Application Protocol (OAP) — Draft Specification v0.1

## Overview

The Open Application Protocol (OAP) is a lightweight, decentralized standard that enables
AI agents to discover, evaluate, and recommend web applications based on capability match
and verified trust signals — without any central registry or gatekeeper.

## Design Principles

1. **Five-minute adoption** — A solo developer using Claude Code can add OAP to their app in minutes
2. **Machine-first** — Designed for AI agent consumption, not human browsing
3. **Decentralized** — No central registry. Discovery via DNS + well-known paths
4. **Verifiable** — Claims are testable, not just declared
5. **Complementary** — Works alongside MCP (agent-to-tool) and A2A (agent-to-agent)

## How It Works

```
User: "I need a simple email-based support CRM for my 5-person team"
         |
    AI Agent queries DNS TXT records and/or crawl index
         |
    Finds domains with _oap TXT records
         |
    Fetches /.well-known/oap.json from each
         |
    Matches capabilities to user need
         |
    Recommends best fits with trust context
```

---

## 1. The Manifest

Every participating application hosts a JSON manifest at:

```
https://{domain}/.well-known/oap.json
```

### Schema

```json
{
  "$schema": "https://oap.dev/schema/v0.1.json",
  "oap_version": "0.1",

  "identity": {
    "name": "string — Application name",
    "tagline": "string — One-line description (max 120 chars)",
    "description": "string — What this app does, written for AI agent comprehension (max 500 chars)",
    "url": "string — Primary application URL",
    "logo": "string (optional) — URL to logo image",
    "version": "string (optional) — Current application version",
    "launched": "string (optional) — ISO 8601 date of initial launch"
  },

  "builder": {
    "name": "string — Person or organization name",
    "url": "string (optional) — Builder's website",
    "contact": "string (optional) — Contact email",
    "verified_domains": ["string — Other domains owned by this builder"]
  },

  "capabilities": {
    "summary": "string — Natural language description of what the app does, optimized for semantic matching by AI agents (max 1000 chars)",
    "solves": ["string — Problems this app addresses, as a user would describe them"],
    "ideal_for": ["string — Target user profiles"],
    "categories": ["string — Standardized category tags"],
    "differentiators": ["string — What makes this different from alternatives"]
  },

  "pricing": {
    "model": "string — free | freemium | subscription | one_time | usage_based",
    "starting_price": "string (optional) — Lowest tier, e.g. '$5/seat/month'",
    "trial": {
      "available": "boolean",
      "duration_days": "integer (optional)",
      "requires_credit_card": "boolean (optional)"
    },
    "pricing_url": "string (optional) — URL to full pricing page"
  },

  "trust": {
    "data_practices": {
      "collects": ["string — Types of data collected, e.g. 'email addresses', 'support ticket content'"],
      "stores_in": "string — Where data is stored, e.g. 'US-based cloud (AWS)', 'EU (GCP)'",
      "shares_with": ["string — Third parties data is shared with, or 'none'"],
      "retention": "string (optional) — Data retention policy summary",
      "encryption": "string (optional) — e.g. 'at rest and in transit'"
    },
    "security": {
      "authentication": ["string — e.g. 'email/password', 'SSO', 'OAuth'"],
      "compliance": ["string (optional) — e.g. 'SOC2', 'GDPR', 'HIPAA'"],
      "audit_log": "boolean (optional)",
      "multi_tenant_isolation": "boolean (optional)"
    },
    "external_connections": ["string — APIs and services the app connects to"],
    "privacy_url": "string (optional) — URL to privacy policy",
    "terms_url": "string (optional) — URL to terms of service"
  },

  "integration": {
    "mcp_endpoint": "string (optional) — MCP server URL if available",
    "api": {
      "available": "boolean",
      "docs_url": "string (optional)",
      "auth_method": "string (optional) — e.g. 'API key', 'OAuth2'"
    },
    "webhooks": "boolean (optional)",
    "import_from": ["string (optional) — Services users can import data from"],
    "export_formats": ["string (optional) — e.g. 'CSV', 'JSON', 'PDF'"]
  },

  "verification": {
    "status_url": "string (optional) — Public status/uptime page",
    "health_endpoint": "string (optional) — Deep health check URL returning HTTP 200. For apps that want to signal more than basic liveness (e.g. database, API, and dependency health). If omitted, the registry uses the manifest URL (/.well-known/oap.json) as a liveness check.",
    "demo_url": "string (optional) — URL to live demo or sandbox"
  }
}
```

---

## 2. DNS Discovery

Applications signal OAP participation via DNS TXT record:

```
_oap.example.com TXT "v=oap1; manifest=https://example.com/.well-known/oap.json"
```

### Why DNS?

- Fully decentralized — no registry needed
- Domain ownership is inherently verified
- AI agents and crawlers can discover manifests at scale
- Follows established patterns (_dmarc, _acme-challenge, etc.)

### Optional: DNS-based capability hints

For faster pre-filtering without fetching the full manifest:

```
_oap.example.com TXT "v=oap1; cat=crm,support,ai; price=subscription; manifest=https://example.com/.well-known/oap.json"
```

---

## 3. Discovery Mechanisms

OAP supports multiple discovery paths — no single point of failure:

### Primary: OAP Registry (npm model)
Builders register their app by submitting their URL to an open registry.
The registry fetches the manifest, validates it, verifies DNS, and indexes
it for search. Registration is instant, free, and requires no approval.

See the [Registry Specification](/registry) for the full registry specification.

```
POST registry.oap.dev/api/v1/register
{ "url": "https://myapp.com" }
```

**Key properties:**
- Anyone can register. No approval process.
- Anyone can run their own registry. The public one is the default, not the only one.
- The registry stores pointers and cached metadata. Truth lives at the source.
- AI agents query the registry to match user needs to app capabilities.
- Multiple registries can coexist. Deduplication is by domain.

### Secondary: Direct manifest fetch
Any agent encountering a domain can check `/.well-known/oap.json` — like checking robots.txt.

### Tertiary: DNS TXT verification
DNS TXT records at `_oap.domain.com` verify domain ownership and
participation. Used by registries during registration, and by agents
for independent verification.

### Future: OAP-aware search
As adoption grows, search engines and AI agents can prioritize OAP-enabled
applications in software recommendation queries.

---

## 4. Trust Scoring (Agent-Side)

OAP does NOT define a trust score. Trust evaluation is the responsibility of the
consuming AI agent. However, the protocol provides the raw materials for agents to
assess trust independently:

**Verifiable signals:**
- Domain age and history (via WHOIS/DNS)
- Liveness (manifest URL responds with 2xx) and optional deep health endpoint
- Consistency between declared practices and observable behavior
- SSL certificate validity
- Builder's verified domain portfolio
- Manifest staleness (last-modified headers)

**Declared signals (trust but verify):**
- Data practices and security claims
- Compliance certifications
- External connection list

**Community signals (future):**
- User reviews/ratings via decentralized reputation protocols
- Builder track record across multiple applications
- Third-party audit attestations

The key insight: OAP provides the *inputs* for trust evaluation without being
the trust *authority*. This eliminates the single-point-of-failure risk that
would make a centralized trust layer an unacceptable business.

---

## 5. Adoption Path

### Phase 1: Seed (Now)
- Publish spec, registry spec, and reference manifests
- Deploy registry reference implementation
- Build CLI generator and validator tools
- Implement on 3 reference apps (Xuru, ProveXa, myNewscast)
- Open-source all tooling

### Phase 2: Builder Community
- Evangelize in Claude Code, Cursor, and AI-builder communities
- Create framework plugins (Next.js, Remix, etc.)
- Build a simple open index that any agent can query

### Phase 3: Agent Integration
- Work with AI companies to recognize OAP manifests
- Demonstrate improved recommendation quality with OAP data
- Propose as complement to MCP/A2A ecosystem

### Phase 4: De Facto Standard
- Sufficient adoption that agents check for OAP by default
- Multiple competing index services
- Community governance formalized

---

## 6. What OAP Is Not

- **Not an app store** — No browsing, no curation, no gatekeeping
- **Not a rating system** — Trust evaluation is agent-side, not protocol-side
- **Not a payment processor** — Pricing is declared, transactions happen on the app
- **Not a competitor to MCP/A2A** — OAP is the discovery layer; MCP/A2A are the communication layers
- **Not a walled garden** — No registration required, no approval process, no fees

---

## License

This specification is released under Creative Commons CC0 1.0 Universal (Public Domain).
Anyone can use, modify, and build upon this specification without restriction.

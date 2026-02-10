# OAP Registry Specification v0.1

## Overview

The OAP Registry is an open, decentralized index for application discovery.
It follows the npm model: anyone can publish, no approval required, and
anyone can run their own registry instance.

The registry stores **pointers, not data**. All application information lives
in the manifest on the app's own domain. If any registry disappears, the data
survives and another registry can rebuild from any mirror.

## Design Principles

1. **Open registration** — No approval process. Submit your manifest URL and you're listed.
2. **Federated** — Anyone can run a registry. The public one is the default, not the only one.
3. **Pointers, not data** — The registry stores URLs and cached metadata. Truth lives at the source.
4. **Agent-optimized** — Query API designed for AI agents doing semantic capability matching.
5. **Zero cost to list** — Free forever for basic registration. No extraction.

## Architecture

```
┌────────────────────────────────────────────────┐
│                   AI AGENT                     │
│  "User needs email-native CRM for small team"  │
└────────┬──────────────────────────┬────────────┘
         │ semantic query            │ verify
         ▼                           ▼
┌──────────────────┐    ┌───────────────────────────┐
│  OAP REGISTRY    │    │  APP DOMAIN (DNS + TXT)   │
│                  │    │                           │
│ - Search index   │    │ _oap.xuru.ai TXT "v=oap1" │
│ - Cached metadata│    │ /.well-known/oap.json     │
│ - Category browse│    │                           │
│ - Health status  │    │ Source of truth            │
└──────────────────┘    └───────────────────────────┘
     Discoverable              Verifiable
```

## Registration Flow

```
1. Builder deploys manifest to /.well-known/oap.json
2. Builder adds DNS TXT record at _oap.domain.com
3. Builder calls: POST registry.oap.dev/api/v1/register { "url": "https://myapp.com" }
4. Registry fetches /.well-known/oap.json from the domain
5. Registry verifies DNS TXT record exists
6. Registry indexes the manifest for search
7. Done. No approval. No waiting. No fees.
```

## Verification on Registration

The registry performs automated verification (not approval) on registration:

- **Domain ownership**: The manifest must be served from the domain being registered
- **DNS TXT record**: _oap TXT record must exist and point to the manifest
- **Manifest validity**: Must pass schema validation
- **Liveness**: The app's URL must respond with 2xx
- **Health endpoint**: If declared, must respond with 2xx

These checks run on registration AND periodically (daily) thereafter.
Apps that fail checks get flagged, not removed.

## API Specification

### Base URL
```
https://registry.oap.dev/api/v1
```

### Register an App

```
POST /register
Content-Type: application/json

{
  "url": "https://myapp.com"
}

Response 201:
{
  "status": "registered",
  "domain": "myapp.com",
  "manifest_url": "https://myapp.com/.well-known/oap.json",
  "dns_verified": true,
  "manifest_valid": true,
  "health_ok": true,
  "indexed_at": "2026-02-10T12:00:00Z"
}

Response 400:
{
  "status": "error",
  "errors": ["Manifest not found at /.well-known/oap.json"]
}
```

### Search for Apps (Primary — for AI agents)

```
GET /search?q={natural language query}

Example: /search?q=email-native support CRM for small team under $10/seat

Response 200:
{
  "query": "email-native support CRM for small team under $10/seat",
  "results": [
    {
      "domain": "xuru.ai",
      "name": "Xuru",
      "tagline": "AI-powered support ticket CRM that answers first",
      "manifest_url": "https://xuru.ai/.well-known/oap.json",
      "match_score": 0.94,
      "match_reasons": [
        "Email-native: agents respond from their email client",
        "Pricing: $5/seat/month, under requested $10 threshold",
        "AI-first support with knowledge base learning"
      ],
      "trust_signals": {
        "domain_age_days": 180,
        "dns_verified": true,
        "health_ok": true,
        "last_checked": "2026-02-10T08:00:00Z",
        "uptime_30d": 99.8
      },
      "pricing": {
        "model": "subscription",
        "starting_price": "$5/seat/month"
      },
      "categories": ["crm", "support-tickets", "help-desk", "ai-support"]
    }
  ],
  "total": 1,
  "registry": "registry.oap.dev",
  "searched_at": "2026-02-10T12:00:00Z"
}
```

### Browse by Category

```
GET /categories
GET /categories/{category}?page=1&limit=20

Response 200:
{
  "category": "crm",
  "apps": [...],
  "total": 47,
  "page": 1
}
```

### Get App Details

```
GET /apps/{domain}

Response 200:
{
  "domain": "xuru.ai",
  "manifest": { ... full cached manifest ... },
  "registry_meta": {
    "registered_at": "2026-01-15T00:00:00Z",
    "last_verified": "2026-02-10T08:00:00Z",
    "dns_verified": true,
    "health_ok": true,
    "uptime_30d": 99.8,
    "manifest_hash": "sha256:abc123...",
    "builder_other_apps": ["provexa.ai", "mynewscast.com"]
  }
}
```

### List All (for mirrors and bulk access)

```
GET /all?page=1&limit=100

Response 200:
{
  "apps": [
    {
      "domain": "xuru.ai",
      "manifest_url": "https://xuru.ai/.well-known/oap.json",
      "manifest_hash": "sha256:abc123...",
      "last_verified": "2026-02-10T08:00:00Z"
    },
    ...
  ],
  "total": 1247,
  "page": 1
}
```

This endpoint enables anyone to mirror the full registry.

### Health/Stats

```
GET /stats

Response 200:
{
  "total_apps": 1247,
  "categories": 89,
  "verified_healthy": 1198,
  "registered_today": 12,
  "registry_version": "0.1"
}
```

## Freshness Model

The registry is a **cache**, not the source of truth.

- Manifests are re-fetched from source every 24 hours
- Health endpoints are checked every 6 hours
- DNS verification runs every 24 hours
- If source manifest changes, registry updates automatically
- If source goes down for 7+ days, app is flagged (not removed)
- If source goes down for 30+ days, app is delisted (can re-register)

## Federation

Anyone can run an OAP registry. The spec is open. The data is public.

**Why run your own registry?**
- Vertical-specific (e.g., a registry just for healthcare apps)
- Geographic (e.g., EU-only apps for GDPR-focused agents)
- Corporate (internal apps within an organization)
- Backup/mirror (resilience against single registry failure)

**Registry discovery:**
Registries can announce themselves so agents know where to look:
```
_oap-registry.yourdomain.com TXT "v=oap1; api=https://your-registry.com/api/v1"
```

**Cross-registry search:**
Agents can query multiple registries and merge results. Registries do NOT
need to be aware of each other. Deduplication is by domain — same domain
in multiple registries is the same app.

## Anti-Gaming

The registry does not rank by popularity, reviews, or payment. But gaming
is still possible. Defenses:

- **One app per domain** — Prevents bulk spam registration
- **Domain ownership verification** — DNS TXT must match
- **Manifest-source consistency** — Declared capabilities must match observable behavior
- **Builder reputation** — Cross-referencing verified_domains shows builder track record
- **Agent-side evaluation** — The registry provides data; AI agents decide trust
- **Community flagging** — API endpoint for reporting abusive or fraudulent listings

The registry is deliberately dumb. It indexes and verifies liveness.
Intelligence lives in the AI agents that query it.

## Cost & Sustainability

The public registry is free to use and free to list in. Sustainability options:

- **Donated infrastructure** — Like Let's Encrypt, backed by companies who benefit
- **Premium analytics** — Builders can pay for insights on how agents discover them
- **Sponsored verification** — Third-party auditors can offer paid trust attestations
- **Foundation model** — Non-profit with industry backers

The registry NEVER charges for listing or discovery. That's the line that
separates infrastructure from a gatekeeper.

## What the Registry Is Not

- ❌ Not an app store — No curation, no featured placements, no editorial
- ❌ Not an approval system — Registration is automated, not human-reviewed
- ❌ Not a payment processor — All transactions happen on the app
- ❌ Not a ranking system — Search returns capability matches, not rankings
- ❌ Not a monopoly — Anyone can run a registry
- ❌ Not a walled garden — Delisting only for prolonged downtime, never for content

## License

This specification is released under CC0 1.0 Universal (Public Domain).

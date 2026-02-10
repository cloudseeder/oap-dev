# OAP.dev — Product Requirements Document

## Project Overview

Build a single Next.js application that serves both the **oap.dev** marketing/documentation site and the **registry.oap.dev** API and search interface. This is the home of the Open Application Protocol — an open, decentralized standard for AI agent discovery of web applications.

**Stack:** Next.js (App Router), Tailwind CSS, Node.js, Firebase/Firestore
**Domains:** oap.dev (site + API), registry.oap.dev (CNAME to same deployment, routed to registry UI/API)
**Repo:** github.com/oap-dev (or similar)

---

## Architecture

### Single Deployment, Two Experiences

One Next.js app handles both domains:

- **oap.dev** — Marketing site, documentation, spec, manifesto
- **registry.oap.dev** — Registry search UI + API at `/api/v1/*`

Use Next.js middleware to detect the hostname and route accordingly:
- Requests to `registry.oap.dev` → registry pages and API routes
- Requests to `oap.dev` → marketing/documentation pages
- API routes at `/api/v1/*` are accessible from both domains

### Database

Use **Firebase Firestore** for the registry data store.

**Collections:**

```
apps/
  {domain}/                    # Document ID = domain (e.g., "xuru.ai")
    domain: string
    manifest_url: string
    manifest: object           # Full cached manifest JSON
    manifest_hash: string      # sha256 hash for change detection
    
    # Cached fields for search (denormalized from manifest)
    name: string
    tagline: string
    description: string
    app_url: string
    summary: string            # capabilities.summary
    solves: string[]           # capabilities.solves
    ideal_for: string[]        # capabilities.ideal_for
    categories: string[]       # capabilities.categories (lowercase)
    differentiators: string[]  # capabilities.differentiators
    pricing_model: string      # free | freemium | subscription | one_time | usage_based
    starting_price: string
    builder_name: string
    builder_verified_domains: string[]
    
    # Verification state
    dns_verified: boolean
    health_ok: boolean
    manifest_valid: boolean
    
    # Tracking
    registered_at: timestamp
    last_verified: timestamp
    last_fetched: timestamp
    uptime_checks_passed: number
    uptime_checks_total: number
    
    # Status
    flagged: boolean
    flag_reason: string | null
    delisted: boolean

categories/
  {category}/                  # Aggregate doc for category listing
    category: string
    count: number
    domains: string[]          # Array of domains in this category

stats/
  global/                      # Single doc for registry stats
    total_apps: number
    total_categories: number
    verified_healthy: number
    registered_today: number
    last_updated: timestamp
```

---

## Pages — oap.dev (Marketing Site)

### 1. Landing Page (`/`)

**Purpose:** Convince a developer to add OAP to their app in 5 minutes.

**Hero Section:**
- Headline: "The Open Application Protocol"
- Subheadline: "Let AI agents discover your app. No app store. No gatekeeper. No fees."
- Two CTAs: "Get Started in 5 Minutes" → `/docs/quickstart` | "Read the Spec" → `/spec`

**Problem Statement Section:**
- Brief version of the discovery gap argument
- The concrete example: AI agent recommends HubSpot over a better, cheaper alternative because it doesn't know the alternative exists
- "MCP tells agents how to talk to tools. A2A tells agents how to talk to each other. OAP tells agents what apps exist."

**How It Works Section:**
- Three steps with visual:
  1. Add a manifest file to your app (/.well-known/oap.json)
  2. Add a DNS TXT record
  3. Register with the registry (one API call)
- Code snippet showing the minimal manifest
- Code snippet showing the registration curl command

**Who It's For Section:**
- "Built for the new builder class" — domain experts using AI coding tools to create production software
- Brief mention of the three reference apps as proof

**Open Infrastructure Section:**
- CC0 license
- Anyone can run a registry
- npm model — no approval, no fees, no gatekeeping
- Backed by working code, not just a spec

**Footer:**
- Links to Spec, Registry, GitHub, Manifesto
- "OAP is open infrastructure. CC0 1.0 Universal."

### 2. Spec Page (`/spec`)

**Purpose:** The complete protocol specification, rendered from SPEC.md content.

- Render the full specification as formatted HTML
- Table of contents sidebar for navigation
- Code blocks with syntax highlighting for JSON examples
- The full manifest schema with field descriptions
- Link to download as markdown

### 3. Registry Spec Page (`/registry`)

**Purpose:** The registry specification, rendered from REGISTRY.md content.

- Full registry API documentation
- Endpoint descriptions with request/response examples
- Federation model explanation
- Anti-gaming measures

### 4. Quick Start Guide (`/docs/quickstart`)

**Purpose:** Get a developer from zero to registered in 5 minutes.

**Step-by-step walkthrough:**

1. **Create your manifest** — Show minimal example, explain each field, link to full schema
2. **Deploy it** — "Put oap.json at /.well-known/oap.json on your domain"
3. **Add DNS TXT record** — Show the record format, explain where to add it in common providers (Cloudflare, Namecheap, Route53, Google Domains)
4. **Register** — Single curl command: `POST https://registry.oap.dev/api/v1/register`
5. **Verify** — "Check your listing at registry.oap.dev/apps/{yourdomain}"

**Also mention:**
- "Or just tell your AI coding tool: 'Add an OAP manifest to my app. Here's the spec: https://oap.dev/spec'"
- Link to the interactive generator tool (future)
- Link to example manifests on GitHub

### 5. Manifesto Page (`/manifesto`)

**Purpose:** The full argument for why OAP exists.

- Rendered from the manifesto content (the white paper we wrote)
- Clean, readable long-form layout
- Can also link to downloadable .docx version

### 6. Examples Page (`/examples`)

**Purpose:** Show real manifests from real apps.

- Display the three reference manifests (Xuru, ProveXa, myNewscast) with syntax highlighting
- Brief description of each app and why the manifest is structured the way it is
- "View on GitHub" links

---

## Pages — registry.oap.dev (Registry Interface)

### 7. Registry Home (`/` on registry.oap.dev)

**Purpose:** Search and browse registered applications.

**Search Bar (prominent):**
- Large search input: "Describe what you need..."
- Example queries as placeholder or chips: "email-native CRM", "HOA management", "civic transparency"
- Search hits the `/api/v1/search` endpoint
- Results display as cards with: name, tagline, domain, categories, pricing, trust signals (DNS verified badge, health status, uptime)

**Stats Bar:**
- Total registered apps, total categories, healthy apps
- "Open. Decentralized. No gatekeepers."

**Category Browse:**
- Grid or list of categories with app counts
- Click through to filtered list

**Register CTA:**
- "Register your app" → link to quickstart or simple inline form
- Show the curl command

### 8. App Detail Page (`/apps/{domain}` on registry.oap.dev)

**Purpose:** Full details for a registered application.

**Display:**
- App name, tagline, logo (if provided)
- Link to app URL
- Builder name and other verified apps
- Full capabilities summary
- Problems it solves (as a list)
- Ideal user profiles
- Categories as tags
- Pricing details with trial info
- Trust section: data practices, security, external connections
- Integration details: API availability, webhooks, import/export
- Registry metadata: registered date, last verified, DNS status, health status, uptime

**Trust Signals (visual badges/indicators):**
- ✅ DNS Verified
- ✅ Health OK
- ✅ Manifest Valid
- Uptime percentage (if available)
- "Other apps by this builder" with links

### 9. Category Page (`/categories/{category}` on registry.oap.dev)

**Purpose:** Browse all apps in a category.

- Category name and app count
- List of app cards (same format as search results)
- Pagination

### 10. API Docs Page (`/docs` on registry.oap.dev)

**Purpose:** API reference for developers and AI agents.

- All endpoints documented with request/response examples
- Authentication: none required (open API)
- Rate limiting info
- "For AI Agents" section explaining how to integrate OAP queries

---

## API Routes (`/api/v1/*`)

All API routes return JSON. No authentication required for read operations.

### POST `/api/v1/register`

**Request:**
```json
{
  "url": "https://myapp.com"
}
```

**Process:**
1. Extract domain from URL
2. Check if already registered (return 409 if so)
3. Fetch `/.well-known/oap.json` from the domain (10s timeout)
4. Validate manifest against schema
5. Verify DNS TXT record at `_oap.{domain}` (non-blocking — register even if not set up yet)
6. Check health endpoint if declared (5s timeout)
7. Hash manifest content
8. Store in Firestore `apps/{domain}`
9. Update category counts
10. Update global stats
11. Return success with verification status

**Response 201:**
```json
{
  "status": "registered",
  "domain": "myapp.com",
  "manifest_url": "https://myapp.com/.well-known/oap.json",
  "dns_verified": true,
  "manifest_valid": true,
  "health_ok": true,
  "indexed_at": "2026-02-10T12:00:00Z"
}
```

**Error responses:** 400 (bad request/validation), 409 (already registered), 500 (server error)

### GET `/api/v1/search?q={query}`

**Process:**
1. Parse query string into keywords
2. Search across cached fields: name, tagline, description, summary, solves, ideal_for, categories, differentiators
3. Score results by keyword match density (reference implementation uses keyword matching; production can add vector embeddings later)
4. Return top 20 results with match scores

**Response 200:**
```json
{
  "query": "email-native support CRM for small team",
  "results": [
    {
      "domain": "xuru.ai",
      "name": "Xuru",
      "tagline": "AI-powered support ticket CRM that answers first",
      "manifest_url": "https://xuru.ai/.well-known/oap.json",
      "match_score": 0.75,
      "trust_signals": {
        "dns_verified": true,
        "health_ok": true,
        "last_checked": "2026-02-10T08:00:00Z"
      },
      "pricing": {
        "model": "subscription",
        "starting_price": "$5/seat/month"
      },
      "categories": ["crm", "support-tickets", "help-desk"]
    }
  ],
  "total": 1,
  "searched_at": "2026-02-10T12:00:00Z"
}
```

### GET `/api/v1/categories`

Returns all categories with app counts. Read from Firestore `categories` collection.

### GET `/api/v1/categories/{category}?page=1&limit=20`

Returns paginated list of apps in a category.

### GET `/api/v1/apps/{domain}`

Returns full app details including cached manifest and registry metadata.

### PUT `/api/v1/apps/{domain}/refresh`

Re-fetches manifest from source, re-validates, re-verifies DNS and health. Updates Firestore document.

### GET `/api/v1/all?page=1&limit=100`

Returns paginated list of all registered apps (domain, manifest_url, manifest_hash, last_verified). For mirroring and federation.

### GET `/api/v1/stats`

Returns global registry statistics. Read from Firestore `stats/global` document.

---

## Manifest Validation Logic

When registering or refreshing an app, validate the manifest against these rules:

**Required fields (return error if missing):**
- identity.name (string)
- identity.tagline (string, max 120 chars — warn if exceeded)
- identity.description (string, max 500 chars — warn if exceeded)
- identity.url (string, valid URL)
- builder.name (string)
- capabilities.summary (string, max 1000 chars — warn if exceeded)
- capabilities.solves (array, min 1 item)
- capabilities.ideal_for (array, min 1 item)
- capabilities.categories (array, min 1 item)
- capabilities.differentiators (array, min 1 item)
- pricing.model (string, one of: free, freemium, subscription, one_time, usage_based)
- pricing.trial.available (boolean)
- trust.data_practices.collects (array)
- trust.data_practices.stores_in (string)
- trust.data_practices.shares_with (array)
- trust.security.authentication (array)
- trust.external_connections (array)

**URL validation:** All URL fields must be valid URLs if present.

**One app per domain:** Enforced by using domain as the document ID.

---

## DNS Verification Logic

Check for TXT record at `_oap.{domain}`:

```javascript
const dns = require('dns').promises;

async function verifyDNS(domain) {
  try {
    const records = await dns.resolve(`_oap.${domain}`, 'TXT');
    const flat = records.map(r => r.join('')).join(' ');
    return flat.includes('v=oap1');
  } catch (e) {
    return false;
  }
}
```

DNS verification is non-blocking. Apps can register without a DNS record — the response will include `dns_verified: false` and a hint showing the exact TXT record to add.

---

## Search Implementation

### Phase 1 (MVP — ship now):
Keyword matching across all text fields. Split query into words, count matches against the concatenated searchable text of each app, normalize score.

### Phase 2 (future):
Add vector embeddings for semantic search. Generate embeddings for the `capabilities.summary` and `capabilities.solves` fields. Store in Firestore or a vector DB. Query with embedded user query for true semantic matching.

The keyword approach is sufficient to launch and demonstrate the concept. The Florida guy still finds Xuru because "email", "CRM", "support", and "small" all match.

---

## Background Jobs

These can be implemented as Firebase Cloud Functions or Next.js cron routes:

### Manifest Refresh (every 24 hours)
- Iterate all non-delisted apps
- Re-fetch manifest from source URL
- If manifest changed (different hash), update cached fields
- If fetch fails, increment failure counter
- If failed for 7+ consecutive days, set `flagged: true`
- If failed for 30+ consecutive days, set `delisted: true`

### Health Check (every 6 hours)
- For apps with a declared health endpoint
- Fetch endpoint, expect HTTP 2xx
- Update `health_ok`, `uptime_checks_passed`, `uptime_checks_total`

### DNS Re-verification (every 24 hours)
- Re-check DNS TXT records for all apps
- Update `dns_verified` flag

### Stats Update (every hour or on-write)
- Recount total_apps, total_categories, verified_healthy, registered_today
- Update `stats/global` document

---

## Design Guidelines

### General
- Clean, minimal, developer-focused
- Dark mode support (devs love dark mode)
- Monospace font for code/technical elements
- System/sans-serif for body text
- Fast — no heavy frameworks, minimal JS where possible

### Color Palette
- Primary: Deep blue (#2D5F8A) — trust, infrastructure
- Background: White / Dark gray for dark mode
- Accent: Teal or green for verification badges
- Text: Near-black for readability
- Code blocks: Dark background with syntax highlighting

### Trust Badges (used on app cards and detail pages)
- ✅ DNS Verified — green checkmark
- ✅ Health OK — green checkmark
- ⚠️ DNS Not Verified — yellow warning
- ❌ Health Down — red indicator
- Uptime shown as percentage with color coding (>99% green, >95% yellow, <95% red)

### Key Design Principle
This is infrastructure, not a consumer product. It should feel like docs.github.com or npmjs.com — credible, efficient, no-nonsense. The design should communicate "this is serious open infrastructure" not "this is a startup trying to get your attention."

---

## Deployment

### Firebase Project
- Create Firebase project for OAP
- Enable Firestore
- Set up Firebase Admin SDK for server-side access in Next.js API routes

### Hosting
- Deploy Next.js app to Vercel (or Firebase Hosting with Cloud Functions)
- Configure custom domains:
  - oap.dev → primary domain
  - registry.oap.dev → CNAME to same deployment
- Next.js middleware routes based on hostname

### DNS Configuration (at oap.dev registrar)
- A/CNAME records pointing to hosting provider
- registry subdomain CNAME
- Any other needed records

---

## MVP Scope — Ship This First

1. **Landing page** with hero, problem statement, how it works, and get started CTA
2. **Quick start page** with step-by-step instructions
3. **Spec page** rendered from spec content
4. **Registry API** — register, search, app details, categories, stats, all, refresh
5. **Registry search UI** — search bar, results cards, category browse
6. **App detail page** — full manifest display with trust badges
7. **Seed data** — Xuru, ProveXa, myNewscast pre-registered

### Defer to Post-MVP
- Manifesto page (link to downloadable docx for now)
- Examples page (link to GitHub)
- Background refresh jobs (run manually at first)
- Vector search / semantic matching upgrade
- Interactive manifest generator in browser
- Dark mode
- Rate limiting on API

---

## Success Metrics

- Registry has 100+ apps within 60 days of launch
- At least 3 categories with 10+ apps each
- Search returns relevant results for common software queries
- The Florida guy finds Xuru

---

## File/Folder Structure

```
oap-dev/
├── app/
│   ├── layout.tsx                 # Root layout
│   ├── page.tsx                   # Landing page (oap.dev)
│   ├── spec/
│   │   └── page.tsx               # Spec page
│   ├── registry/
│   │   └── page.tsx               # Registry spec page
│   ├── docs/
│   │   └── quickstart/
│   │       └── page.tsx           # Quick start guide
│   ├── manifesto/
│   │   └── page.tsx               # Manifesto page (post-MVP)
│   ├── examples/
│   │   └── page.tsx               # Examples page (post-MVP)
│   ├── r/                         # Registry UI pages (served on registry.oap.dev)
│   │   ├── page.tsx               # Registry home / search
│   │   ├── apps/
│   │   │   └── [domain]/
│   │   │       └── page.tsx       # App detail page
│   │   ├── categories/
│   │   │   ├── page.tsx           # All categories
│   │   │   └── [category]/
│   │   │       └── page.tsx       # Category listing
│   │   └── docs/
│   │       └── page.tsx           # API docs
│   └── api/
│       └── v1/
│           ├── register/
│           │   └── route.ts       # POST register
│           ├── search/
│           │   └── route.ts       # GET search
│           ├── categories/
│           │   ├── route.ts       # GET all categories
│           │   └── [category]/
│           │       └── route.ts   # GET category apps
│           ├── apps/
│           │   └── [domain]/
│           │       ├── route.ts   # GET app details
│           │       └── refresh/
│           │           └── route.ts # PUT refresh
│           ├── all/
│           │   └── route.ts       # GET full dump
│           └── stats/
│               └── route.ts       # GET stats
├── lib/
│   ├── firebase.ts                # Firebase admin init
│   ├── manifest.ts                # Manifest validation logic
│   ├── dns.ts                     # DNS verification
│   ├── search.ts                  # Search/scoring logic
│   └── types.ts                   # TypeScript types for OAP schema
├── components/
│   ├── AppCard.tsx                # App result card (used in search & category)
│   ├── TrustBadges.tsx            # DNS/health/uptime badges
│   ├── SearchBar.tsx              # Search input component
│   ├── CodeBlock.tsx              # Syntax-highlighted code
│   └── ManifestViewer.tsx         # Formatted manifest display
├── middleware.ts                   # Hostname-based routing
├── content/
│   ├── spec.md                    # Full OAP specification
│   └── registry-spec.md           # Registry specification
├── public/
│   ├── schema/
│   │   └── v0.1.json              # JSON schema file
│   └── examples/
│       ├── xuru.ai.json           # Reference manifest
│       ├── provexa.ai.json        # Reference manifest
│       └── mynewscast.com.json    # Reference manifest
├── tailwind.config.ts
├── next.config.ts
├── package.json
└── README.md
```

---

## Middleware Routing Logic

```typescript
// middleware.ts
import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
  const hostname = request.headers.get('host') || '';
  const { pathname } = request.nextUrl;

  // API routes are accessible from both domains
  if (pathname.startsWith('/api/')) {
    return NextResponse.next();
  }

  // Registry subdomain routes to /r/* pages
  if (hostname.startsWith('registry.')) {
    const url = request.nextUrl.clone();
    url.pathname = `/r${pathname}`;
    return NextResponse.rewrite(url);
  }

  // Default: oap.dev marketing site
  return NextResponse.next();
}
```

---

## Seed Data

On first deploy, seed the registry with the three reference applications. The manifest JSON files for Xuru, ProveXa, and myNewscast are included in the repo under `public/examples/`. A seed script reads these files and inserts them into Firestore with `dns_verified: false` and `health_ok: true` until DNS is configured and the apps have health endpoints.

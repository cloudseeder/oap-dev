# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Open Application Protocol (OAP) — a decentralized discovery and trust layer for web applications, designed for AI agents. Three components:

1. **Manifest** (`/.well-known/oap.json`) — JSON file apps host declaring identity, capabilities, pricing, trust signals
2. **DNS Discovery** — TXT record at `_oap.{domain}` signals protocol participation
3. **Registry** — Optional open registry (npm model: no approval, anyone can run one)

Protocol version: 0.1 (draft). License: CC0 1.0 (Public Domain).

## Repository Structure

### Next.js Application (oap.dev + registry.oap.dev)

- `app/(marketing)/` — Marketing site pages (oap.dev): landing, spec, registry spec, quickstart
- `app/r/` — Registry UI pages (registry.oap.dev): search, app detail, categories, API docs
- `app/api/v1/` — Registry API routes (shared across both domains)
- `components/` — Shared React components (Header, Footer, AppCard, SearchBar, etc.)
- `lib/` — Shared TypeScript libraries:
  - `lib/types.ts` — All TypeScript interfaces (OAPManifest, AppDocument, etc.)
  - `lib/firebase.ts` — Firebase Admin singleton
  - `lib/firestore.ts` — Firestore data access layer (CRUD, categories, stats)
  - `lib/manifest.ts` — Manifest validation (ported from tools/validate.js)
  - `lib/dns.ts` — DNS verification, manifest fetch, health check, hashing
  - `lib/search.ts` — Keyword search algorithm, result formatting
  - `lib/markdown.ts` — Markdown → HTML rendering with TOC extraction
- `middleware.ts` — Hostname-based routing (registry.* → /r/*)
- `scripts/seed.ts` — Firestore seed script for example data
- `public/schema/v0.1.json` — JSON Schema for IDE validation
- `public/examples/` — Example manifests for download

### Protocol & Reference Implementation

- `docs/SPEC.md` — Full protocol specification (the authoritative reference)
- `docs/REGISTRY.md` — Registry API specification
- `docs/OAP_PRD.md` — Product requirements document
- `registry/server.js` — Reference registry server (Express + SQLite)
- `registry/package.json` — Registry dependencies
- `tools/generate.js` — Interactive manifest generator CLI
- `tools/validate.js` — Manifest validator (file or URL)
- `examples/` — Reference manifests (xuru.ai, provexa.ai, mynewscast.com)

## Commands

### Next.js App

```bash
npm install
npm run dev          # Development server on http://localhost:3000
npm run build        # Production build
npm run start        # Start production server
npm run seed         # Seed Firestore with example apps
```

### Environment Variables (.env.local)

```
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CLIENT_EMAIL=your-client-email@your-project.iam.gserviceaccount.com
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
```

### Reference Registry Server

```bash
cd registry
npm install
npm start            # Runs on http://localhost:3000
```

### CLI Tools

```bash
node tools/validate.js examples/xuru.ai/oap.json
node tools/validate.js https://myapp.com/.well-known/oap.json
node tools/generate.js
```

## Architecture Notes

- **Next.js App Router** with TypeScript, Tailwind CSS, and Firebase Admin SDK
- **Two-domain architecture**: `oap.dev` (marketing) and `registry.oap.dev` (registry UI + API), routed via middleware hostname detection
- **Firestore collections**: `apps/{domain}`, `categories/{category}`, `stats/global`
- **Registry UI pages** call Firestore directly (server components, no HTTP round-trip to own API)
- **API routes** are identical to the reference Express implementation, ported to Next.js route handlers
- **Search** is keyword-based (split query, match across text fields, name/tagline bonus). Designed to be upgraded to vector/semantic search.
- **DNS verification is non-blocking** — apps can register without DNS records set up
- **Markdown rendering** uses unified/remark/rehype pipeline for spec pages with auto-generated TOC
- **No test framework** currently configured
- **No linter/formatter** currently configured

## Registry API Endpoints

- `POST /api/v1/register` — Register app (validates manifest, checks DNS)
- `GET /api/v1/search?q=...` — Keyword search
- `GET /api/v1/categories` — List categories with counts
- `GET /api/v1/categories/:category` — Browse by category
- `GET /api/v1/apps/:domain` — App details
- `PUT /api/v1/apps/:domain/refresh` — Force manifest re-fetch
- `GET /api/v1/all` — Paginated registry dump (for mirroring)
- `GET /api/v1/stats` — Registry statistics

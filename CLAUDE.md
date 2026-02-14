# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Open Application Protocol (OAP) — a cognitive API layer for artificial intelligence. A manifest spec that lets AI learn about capabilities that weren't in its training data, at runtime, without retraining.

OAP is a **pure spec** with a reference architecture for discovery. It is **not** a registry, service, or platform.

- **Manifest** (`/.well-known/oap.json`) — JSON file describing what a capability does, what it accepts, what it produces, and how to invoke it. Designed to be read and reasoned about by LLMs.
- **Discovery** — Not prescribed by the spec. Reference architecture uses crawlers + local vector DB + small LLM for intent-to-manifest matching. The web model, not the registry model.
- **Trust** — Separate companion overlay (like TLS is to HTTP). Graduated levels: domain attestation, capability attestation, compliance certification.

Protocol version: 1.0. License: CC0 1.0 (Public Domain).

## Repository Structure

### Spec & Documentation

- `README.md` — Project overview and vision (the public face)
- `docs/SPEC.md` — Manifest specification v1.0 (the authoritative reference)
- `docs/ARCHITECTURE.md` — Reference discovery architecture (local vector DB + small LLM + crawler)
- `docs/TRUST.md` — Trust overlay specification (companion protocol)
- `docs/MANIFESTO.md` — Why manifests are the cognitive API for AI
- `docs/old/` — Archived v0.1 registry-era docs (PRD, registry spec, etc.)

### Next.js Application (oap.dev)

The marketing/spec site is still a Next.js app, but the registry functionality has been moved to the `registry-v1` branch.

- `app/(marketing)/` — Marketing site pages (oap.dev): landing, spec
- `app/api/v1/` — API routes (legacy registry, preserved on `registry-v1` branch)
- `components/` — Shared React components
- `lib/` — Shared TypeScript libraries
- `middleware.ts` — Hostname-based routing

### Legacy Registry

The full registry implementation (Firestore-backed, with search, categories, health checks) is preserved on the **`registry-v1`** branch. It includes:
- Registry UI (registry.oap.dev)
- Registry API routes
- Firestore data layer
- CLI tools (manifest generator, validator)
- Reference Express server

## Commands

```bash
npm install
npm run dev          # Development server on http://localhost:3000
npm run build        # Production build
npm run start        # Start production server
```

## Key Design Principles

1. **One-page spec.** If it doesn't fit on one page, it's too complex.
2. **Five-minute adoption.** A solo developer can add OAP in the time it takes to write a README.
3. **No gatekeepers.** No registration, no approval, no fees. Publish and you're in.
4. **Machine-first, human-readable.** Designed for AI to consume, but any developer can read and write a manifest.
5. **Unix philosophy.** Describe what you accept and what you produce. Let the invoker handle composition.
6. **The web model.** Standardize the format. Let the ecosystem build the discovery.
7. **No agent/app distinction.** A capability is a capability — `grep` is an agent with a man page.

## Manifest Format (v1.0)

Only four fields are required: `oap`, `name`, `description`, `invoke`. The `description` field is the most important — it's the text an LLM reads to decide if a capability fits a task.

```json
{
  "oap": "1.0",
  "name": "Capability Name",
  "description": "Plain English description — write it like a man page.",
  "input": { "format": "text/plain", "description": "What this needs" },
  "output": { "format": "application/json", "description": "What this produces" },
  "invoke": { "method": "POST", "url": "https://example.com/api/endpoint" }
}
```

## Architecture Notes

- **Next.js App Router** with TypeScript and Tailwind CSS
- **Markdown rendering** uses unified/remark/rehype pipeline for spec pages with auto-generated TOC
- **No test framework** currently configured
- **No linter/formatter** currently configured

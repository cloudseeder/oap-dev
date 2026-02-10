# Open Application Protocol (OAP)

**The missing discovery and trust layer for web applications in the age of AI agents.**

MCP tells agents how to talk to tools. A2A tells agents how to talk to each other.
OAP tells agents what applications exist, what they do, and why they can be trusted.

## The Problem

AI coding tools like Claude Code are enabling a new class of builders — domain experts who can now create production software without engineering teams. But AI agents can't recommend what they don't know exists. A $5/seat CRM built by someone with 20 years of support experience will lose every recommendation to Zendesk, not because it's worse, but because no discovery mechanism exists for it.

## The Solution

A simple, decentralized protocol:

1. **A manifest file** at `/.well-known/oap.json` that declares what your app does, who it's for, and how it handles data
2. **A DNS TXT record** at `_oap.yourdomain.com` that signals participation
3. **No central registry.** No gatekeeper. No fees. No approval process.

That's it. Any AI agent can find you, evaluate you, and recommend you on merit.

## Quick Start

### Option 1: Generate interactively

```bash
npx oap-init
```

Answer the prompts. Your manifest appears at `.well-known/oap.json`.

### Option 2: Write it yourself

Create `.well-known/oap.json`:

```json
{
  "$schema": "https://oap.dev/schema/v0.1.json",
  "oap_version": "0.1",
  "identity": {
    "name": "My App",
    "tagline": "What it does in one line",
    "description": "Longer description for AI agents",
    "url": "https://myapp.com"
  },
  "builder": {
    "name": "Your Name"
  },
  "capabilities": {
    "summary": "Detailed description of capabilities for AI matching",
    "solves": ["problem 1 as a user would describe it", "problem 2"],
    "ideal_for": ["target user 1", "target user 2"],
    "categories": ["category1", "category2"],
    "differentiators": ["what makes you different"]
  },
  "pricing": {
    "model": "subscription",
    "starting_price": "$X/month",
    "trial": { "available": true, "duration_days": 30, "requires_credit_card": false }
  },
  "trust": {
    "data_practices": {
      "collects": ["what data you collect"],
      "stores_in": "where",
      "shares_with": ["none"]
    },
    "security": {
      "authentication": ["email/password"]
    },
    "external_connections": ["APIs you connect to"]
  }
}
```

### Option 3: Ask your AI coding tool

> "Add an OAP manifest to my app. Here's the spec: https://oap.dev/spec"

This is how most adoption will happen.

## Add DNS Discovery

Add a TXT record to your domain's DNS:

```
Host:  _oap.myapp.com
Value: v=oap1; cat=crm,support; price=subscription; manifest=https://myapp.com/.well-known/oap.json
```

## Validate

```bash
node tools/validate.js .well-known/oap.json
# or validate a live URL:
node tools/validate.js https://myapp.com/.well-known/oap.json
```

## How Discovery Works

```
User → AI Agent → "I need a support CRM for my small team"
                        │
              Query OAP Registry
              registry.oap.dev/api/v1/search
                        │
              Registry matches capabilities
              to user's described need
                        │
              Verify via DNS TXT + health check
                        │
              Recommend best fits with trust context
```

The registry is open (npm model): anyone can register, no approval needed,
anyone can run their own instance. It stores pointers — truth lives on your domain.

## Register Your App

After deploying your manifest and DNS record:

```bash
curl -X POST https://registry.oap.dev/api/v1/register \
  -H "Content-Type: application/json" \
  -d '{"url": "https://myapp.com"}'
```

That's it. Your app is now discoverable by any AI agent that queries the registry.

## Run Your Own Registry

The registry is open source. Run your own for your vertical, region, or company:

```bash
cd registry/
npm install
npm start
# Registry running at http://localhost:3000
```

See [REGISTRY.md](REGISTRY.md) for the full registry specification.

## Reference Implementations

See `examples/` for complete manifests:
- [xuru.ai](examples/xuru.ai/oap.json) — AI-first support CRM
- [provexa.ai](examples/provexa.ai/oap.json) — HOA management with 7 AI agents
- [mynewscast.com](examples/mynewscast.com/oap.json) — Civic transparency platform

## What OAP Is Not

- ❌ Not an app store
- ❌ Not a rating system
- ❌ Not a payment processor
- ❌ Not a competitor to MCP or A2A
- ❌ Not a walled garden

## Full Specification

See [SPEC.md](SPEC.md) for the complete protocol specification.

## Why This Matters

The web was supposed to democratize software. For a brief moment, it did. Then walled gardens captured distribution and extracted 30% of every transaction. AI coding tools are creating a new wave of builders — domain experts turning decades of knowledge into software. They need an open way to be found.

Read the full argument: *[Working Title] — An Open Protocol for Application Discovery and Trust*

## License

CC0 1.0 Universal — Public Domain. Use it, fork it, build on it. No restrictions.

## Contributing

This is v0.1. Everything is open for discussion.
File issues, propose changes, or join the conversation.

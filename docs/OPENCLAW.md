# OAP + OpenClaw: The Reference Integration

**How a personal agent goes from computer-bound to internet-capable.**

---

## What OpenClaw Gets Right

In January 2026, an Austrian developer named Peter Steinberger published an open-source project that accidentally proved the personal agent thesis. Within weeks, it had over 100,000 GitHub stars and made Mac Minis hard to buy.

OpenClaw gets three things right that nobody else has:

**The interface is messaging, not a browser.** You text your agent on WhatsApp, Telegram, iMessage, Signal, or Slack — the same apps you already live in. No new interface to learn. No tab to keep open. The agent meets you where you are. This is a genuine UX breakthrough. Every other AI assistant forces you into *its* interface. OpenClaw lives in *yours*.

**The agent runs locally.** Your data, your memory, your configuration — all folders and markdown files on your machine. The agent only reaches out to the internet to call an LLM. Everything else is local-first. This is the right architecture for trust: the agent's brain is in the cloud, but its body is on your hardware.

**It has persistent memory and proactive behavior.** Tell it you only drink oat milk lattes. Next week, when you ask it to order coffee, it remembers. Set it to summarize your unread emails every morning at 8am. It does it without being asked. This shifts the dynamic from "human uses tool" to "agent works for human." That's a real distinction.

145,000+ developers have voted with their stars: people want a personal agent that *does things*, not a chatbot that *talks about things*.

## Where OpenClaw Is Stuck

But here's the problem. Ask your OpenClaw to do something that isn't on your computer, and it hits a wall.

"Find me a contractor who does pool resurfacing in Conroe, Texas."

OpenClaw can search the web. It can draft an email. It can even make a phone call through ElevenLabs. What it can't do is find a *service* purpose-built for contractor matching — one that knows which contractors are licensed, insured, available, and within range. A service like GetaBid, which matches contractors to homeowners by skill and proximity. OpenClaw doesn't know GetaBid exists. It has no way to find out.

"Get me transcripts from last Tuesday's Portland city council meeting."

OpenClaw can search YouTube. It can try to find a recording. What it can't do is find a civic transparency platform that has already processed the video into structured transcripts with speaker identification, topic segmentation, and voting records. A service like myNewscast. OpenClaw doesn't know it exists either.

"File my HOA's quarterly report with the state of Texas."

OpenClaw can read documents and fill forms. But it can't find a community association management platform that knows Texas HOA statutes, maintains your community's financial history, and produces compliant filings. That service exists somewhere. OpenClaw will never find it.

The pattern is always the same: **OpenClaw is powerful on the computer and blind to the internet.**

### The ClawHub Bottleneck

OpenClaw's answer to this problem is ClawHub — a centralized skill registry where the community publishes pre-built integrations. Need Spotify control? There's a skill. Need calendar management? There's a skill. Need to check flight status? Someone might build a skill.

This is the App Store model. It has the same problems the App Store has always had:

**It doesn't scale.** There are millions of specialized services on the internet. ClawHub will never have skills for all of them. It can't. Each skill requires someone to write OpenClaw-specific code, test it, publish it, and maintain it. The world creates new capabilities faster than any community can wrap them.

**It creates a gatekeeper.** If your service isn't on ClawHub, OpenClaw can't use it. GetaBid doesn't have an OpenClaw skill. myNewscast doesn't have an OpenClaw skill. Most services never will. The registry becomes a bottleneck — not because it's poorly built, but because registries are the wrong abstraction.

**It's a walled garden.** A skill built for OpenClaw doesn't work in any other agent framework. A skill built for LangChain doesn't work in OpenClaw. Every agent platform builds its own skill registry, its own format, its own ecosystem. Developers have to choose which walled garden to publish in — or build the same integration six times.

This is exactly the problem the web solved thirty years ago. HTML didn't require a registry of web pages. You published a page. Crawlers found it. Search engines matched it to queries. The format was standardized. Discovery was left to the ecosystem.

## How OAP Changes the Game

OAP replaces the registry model with the web model. Instead of building OpenClaw-specific skills, services publish a manifest — a JSON file at `/.well-known/oap.json` — that describes what they do in plain English. Any agent can read it. Any agent can use it. No platform-specific code. No registry submission. No gatekeeper.

The integration is straightforward because OpenClaw already has the right architecture. It already runs locally. It already routes to LLMs. It already has a skills concept. The change is in *how it discovers what to use*.

### Before OAP

```
User texts: "Find me a pool resurfacing contractor in Conroe"
    ↓
OpenClaw searches ClawHub for relevant skill
    ↓
No skill found
    ↓
Falls back to web search
    ↓
Returns a list of Google results
    ↓
User does the work themselves
```

### After OAP

```
User texts: "Find me a pool resurfacing contractor in Conroe"
    ↓
OpenClaw's discovery layer searches local OAP manifest index
    ↓
Finds GetaBid manifest:
  "Matches homeowners with licensed, insured contractors
   by trade specialty and proximity. Input: service type
   and location. Output: matched contractors with
   availability, ratings, and contact info."
    ↓
OpenClaw reasons: "This matches the user's intent"
    ↓
Invokes GetaBid API with {service: "pool resurfacing", location: "Conroe, TX"}
    ↓
Returns matched contractors directly in the chat
    ↓
User picks one. Done.
```

No one built a GetaBid skill for OpenClaw. GetaBid just published a manifest on its own domain. OpenClaw's crawler indexed it. The discovery layer matched it. The agent invoked it. The user got what they needed without knowing or caring how.

## The Architecture

Integrating OAP into OpenClaw requires three components, all of which align with OpenClaw's local-first philosophy.

### 1. A Local Manifest Index

OpenClaw already stores memory and configuration as local files. The manifest index is the same pattern — a local vector database containing embedded OAP manifests from across the internet.

```
~/.openclaw/
├── config/           # Existing config
├── memory/           # Existing memory
├── skills/           # Existing ClawHub skills
└── oap/
    ├── manifests/    # Raw JSON manifests (cached)
    ├── index.db      # Vector database (ChromaDB or LanceDB)
    └── crawler.log   # Discovery activity
```

The vector database is small. Ten thousand manifests consume less than 100MB. It runs on the same Mac Mini that runs everything else. No additional hardware. No cloud service.

### 2. A Background Crawler

A lightweight process that periodically fetches `/.well-known/oap.json` from domains. Seed discovery from:

- Domains the user visits frequently (browser history, with permission)
- Domains mentioned in conversations
- Referrals from other manifests
- Community-curated seed lists
- DNS TXT record scanning

The crawler runs in the background, same as OpenClaw's existing cron jobs. New manifests get embedded and added to the vector index. Stale manifests get re-checked. Dead ones get pruned.

```javascript
// Pseudocode: crawler integration with OpenClaw's existing cron system
schedule('0 */6 * * *', async () => {
  const domains = await getSeedDomains();
  for (const domain of domains) {
    const manifest = await fetch(`https://${domain}/.well-known/oap.json`);
    if (manifest.oap === '1.0') {
      await vectorIndex.upsert(manifest);
      await cache.store(domain, manifest);
    }
  }
});
```

### 3. A Discovery Skill

OAP discovery integrates as a skill — OpenClaw's native extension mechanism. But unlike other skills, this one is a *meta-skill*: it finds capabilities that replace the need for individual skills.

```markdown
# OAP Discovery Skill

## Description
Before falling back to web search, query the local OAP manifest
index for capabilities that match the user's intent. Use a small
local LLM to evaluate manifest descriptions against the task.
If a match is found, invoke the capability directly.

## Trigger
Any user request that implies a service or capability that isn't
available as a local skill or native LLM ability.

## Flow
1. Embed user intent as vector
2. Similarity search against manifest index (top 5)
3. Small LLM reads candidate manifests, evaluates fit
4. If match found: invoke capability, return result
5. If no match: fall back to existing behavior (web search)
```

The discovery skill sits *between* the existing skill lookup and the web search fallback. The priority chain becomes:

```
User request
    ↓
1. Can OpenClaw do this natively? (shell, files, calendar)
    → Yes: do it
    ↓
2. Is there a ClawHub skill for this?
    → Yes: use it
    ↓
3. Does an OAP manifest match this intent?
    → Yes: invoke the capability
    ↓
4. Fall back to web search + LLM reasoning
```

ClawHub isn't replaced — it still works for deep, purpose-built integrations like Spotify control or smart home management that require persistent local state. OAP handles everything else: the long tail of specialized services that no one will ever build a dedicated skill for.

## The Manifests OpenClaw Would Find

Here are real capabilities that would exist as OAP manifests — services a personal agent could discover and use without anyone building platform-specific integrations:

### Contractor Matching

```json
{
  "oap": "1.0",
  "name": "GetaBid",
  "description": "Matches homeowners with licensed, insured contractors by trade specialty and geographic proximity. Unlike review-based platforms, matching is based on verified skills, active licensing, insurance status, and real-time availability. Covers residential trades including plumbing, electrical, HVAC, roofing, pool services, landscaping, painting, and general contracting. Input a service type and location. Returns matched contractors with license verification, insurance status, proximity, availability windows, and contact information.",
  "input": {
    "format": "application/json",
    "description": "Service type (trade/specialty), location (address, city, or zip code), optional: urgency level, project description, preferred schedule"
  },
  "output": {
    "format": "application/json",
    "description": "Array of matched contractors with name, trade, license number, insurance status, distance, availability, contact info, and match confidence score"
  },
  "invoke": {
    "method": "POST",
    "url": "https://api.getabid.com/v1/match",
    "auth": "api_key",
    "auth_url": "https://getabid.com/developers"
  },
  "examples": [
    {
      "input": {"service": "pool resurfacing", "location": "Conroe, TX"},
      "output": {"contractors": [{"name": "AquaTech Pools", "distance_miles": 4.2, "licensed": true, "insured": true, "available": "next week"}]},
      "description": "Finding a pool resurfacing contractor near Conroe, Texas"
    }
  ],
  "tags": ["contractors", "home services", "matching", "licensed", "insured"]
}
```

### Civic Transparency

```json
{
  "oap": "1.0",
  "name": "myNewscast",
  "description": "Processes government meeting videos into structured, searchable civic records. Covers city councils, county commissions, planning boards, school boards, water districts, and other public bodies. Produces transcripts with speaker identification, topic segmentation, voting records, motion tracking, and agenda item correlation. Currently covers Portland, OR metro area agencies with expanding coverage. Input is a municipality name and date range, or a direct video URL. Output is structured JSON with full transcript, identified speakers, extracted motions and votes, and topic segments with timestamps.",
  "input": {
    "format": "application/json",
    "description": "Either a municipality name + date range to search processed meetings, or a video URL for on-demand processing. Optional: specific agenda topics to filter for."
  },
  "output": {
    "format": "application/json",
    "description": "Structured meeting record: full transcript, speakers, topics with timestamps, motions, votes, agenda items. Includes confidence scores for speaker identification."
  },
  "invoke": {
    "method": "POST",
    "url": "https://api.mynewscast.com/v1/meetings",
    "auth": "bearer",
    "auth_url": "https://mynewscast.com/api/access"
  },
  "examples": [
    {
      "input": {"municipality": "Portland City Council", "date": "2026-02-11"},
      "output": {"meeting": {"date": "2026-02-11", "duration_minutes": 187, "speakers": 14, "motions": 3, "votes": 2}},
      "description": "Retrieving a recent Portland City Council meeting record"
    }
  ],
  "tags": ["civic", "government", "transcripts", "meetings", "transparency", "local government"]
}
```

### Community Association Management

```json
{
  "oap": "1.0",
  "name": "ProveXa COA Manager",
  "description": "Manages community association operations including financial tracking, expense allocation between associated entities, violation management, and regulatory compliance. Encodes state-specific HOA/COA statutes for governing document compliance. Processes receipts against community chart of accounts with historical categorization learning. Handles shared-expense allocation between legally separate associations with configurable ratios and full audit trails. Maintains AI legal experts grounded in community-specific declarations and bylaws. Input varies by operation: financial processing, compliance queries, violation tracking, or board reporting. Covers Texas and Oregon HOA/COA regulations with expanding state coverage.",
  "input": {
    "format": "application/json",
    "description": "Operation type and parameters. Financial: receipt images or transaction data for categorization and allocation. Compliance: questions about governing documents or state statutes. Reporting: report type and date range."
  },
  "output": {
    "format": "application/json",
    "description": "Operation-specific structured output. Financial: categorized transactions with allocation breakdowns and audit entries. Compliance: cited answers grounded in governing documents and current state law. Reporting: formatted board reports with financial summaries."
  },
  "invoke": {
    "method": "POST",
    "url": "https://api.provexa.ai/v1/operations",
    "auth": "oauth2",
    "auth_url": "https://provexa.ai/oauth/authorize"
  },
  "tags": ["HOA", "COA", "community association", "property management", "compliance", "accounting"]
}
```

### What an Agent Sees

When a user texts their OpenClaw: "My HOA board meeting is Thursday. Can you pull together the financial summary and check if we're compliant on the new Texas disclosure requirements?"

The agent has never encountered ProveXa. It wasn't in any training data. There's no ClawHub skill for it. But the OAP discovery layer finds two manifests:

1. **ProveXa COA Manager** — matches "HOA financial summary" and "Texas compliance"
2. **myNewscast** — matches "board meeting" (in case the user meant minutes from a *previous* meeting)

The small LLM reads both manifests, reasons about the context, and decides ProveXa is the right match. It invokes the API, gets the financial summary and compliance check, and delivers both to the user in their WhatsApp chat.

One text message. Two capabilities the agent didn't know existed five seconds ago. No one built anything OpenClaw-specific. The services just published manifests.

## The Trust Connection

OpenClaw has over 500 open security issues on GitHub. The community's own advice is "don't install it on your main computer." An agent with full shell access and no guardrails is exactly as dangerous as it sounds.

OAP's trust overlay directly addresses this. When OpenClaw discovers a capability through a manifest, the trust layer tells it how much to trust that capability:

**Layer 0 — Unverified.** The manifest exists. That's all you know. OpenClaw should ask the user before invoking. "I found a service called GetaBid that matches contractors. Want me to use it?"

**Layer 1 — Domain Attested.** The manifest publisher has verified their identity. OpenClaw can invoke with more confidence but should still confirm for actions that involve the user's data or money.

**Layer 2 — Capability Attested.** The service has been tested. Its behavior matches its description. No prompt injection in the manifest. OpenClaw can invoke autonomously for read-only operations.

**Layer 3 — Compliance Certified.** SOC2, HIPAA, or other certifications. OpenClaw can invoke autonomously even for sensitive operations within the certified scope.

The trust level determines agent autonomy:

```
Trust Level 0 → Always ask user before invoking
Trust Level 1 → Ask for write operations, auto-invoke for reads
Trust Level 2 → Auto-invoke, report results
Trust Level 3 → Auto-invoke, integrate silently into workflow
```

This maps directly onto OpenClaw's existing permission model. Skills already have different trust levels — some can execute shell commands, others are sandboxed. OAP trust levels extend that model to *discovered* capabilities, not just pre-installed ones.

The combination of OAP discovery + trust overlay gives OpenClaw something no personal agent has today: the ability to find capabilities it's never seen before *and* make informed decisions about how much to trust them — without the user having to configure anything.

## What This Means for the Ecosystem

OpenClaw is the most popular personal agent framework in the world right now. 145,000 GitHub stars. 200+ contributors. A developer community that's already building skills, sharing configurations, and evangelizing the personal agent future.

But it's hitting the ceiling that every walled garden hits: the world is bigger than any registry can catalog.

OAP doesn't compete with OpenClaw. It completes it. OpenClaw is the agent runtime — the local gateway, the messaging interface, the memory system, the skill execution engine. OAP is the discovery layer — how that agent finds capabilities that exist beyond its computer, beyond ClawHub, beyond anything its developers anticipated.

The integration doesn't require OpenClaw to change its architecture. It's a skill. One skill that gives the agent access to every manifest on the open internet. ClawHub continues to exist for deep, stateful, platform-specific integrations. OAP handles the long tail — the millions of specialized services that nobody will ever build a dedicated skill for.

This is also the pattern for *every* personal agent framework. What works for OpenClaw works for any agent runtime that can read a JSON file and call an HTTP endpoint. The integration story is the same whether the agent runs on a Mac Mini, in a Docker container, on a phone, or in the cloud.

One manifest format. Every agent framework. No walled gardens.

---

## For OpenClaw Developers

If you want to add OAP discovery to your OpenClaw instance today:

1. **Publish your own manifests.** If you've built something useful — a service, an API, a tool — put an `oap.json` at `/.well-known/` on your domain.

2. **Build the discovery skill.** A ChromaDB instance, a manifest crawler, and a small LLM for intent matching. The [OAP Architecture](ARCHITECTURE.md) doc has the full stack. It runs on the same Mac Mini.

3. **Seed the index.** Start with manifests from services you already use. Add community-curated lists. Let the crawler expand from there.

4. **Set trust thresholds.** Use the [OAP Trust Overlay](TRUST.md) to configure how much autonomy your agent gets based on manifest trust levels.

5. **Share what you find.** When your agent discovers a useful capability, the manifest is a URL. Share it. The index grows by word of mouth, same as the early web.

The goal isn't to replace ClawHub. It's to make your agent capable of discovering things ClawHub will never have — because the internet is bigger than any registry.

---

*This document is part of the [Open Application Protocol](README.md) suite. OAP is released under CC0 1.0 Universal — no rights reserved.*

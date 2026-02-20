# OAP + A2A: Discovery Meets Conversation

OAP and Google's Agent-to-Agent (A2A) protocol solve different problems. OAP is the manifest layer — what exists, what it does, how to find it. A2A is the conversation layer — how agents talk to each other once they've connected. They complement each other cleanly.

## The separation

| Concern | Protocol | Analogy |
|---------|----------|---------|
| **What exists** | OAP manifest | A man page |
| **How to find it** | OAP discovery | A search engine |
| **How to talk to it** | A2A | A phone call |

OAP tells an agent: "There's a government meeting transcription service at mynewscast.com. Here's what it does, what it accepts, and where to call it."

A2A tells an agent: "Here's how to send it a task, handle multi-turn clarifications, receive streaming artifacts, and track task status."

Neither protocol needs to solve the other's problem.

## The layered architecture

```
┌─────────────────────────────────────────────┐
│  Agent reasoning ("I need meeting data")    │
├─────────────────────────────────────────────┤
│  Discovery layer (OAP)                      │
│  Crawl → embed → match intent to manifest   │
├─────────────────────────────────────────────┤
│  Communication layer (A2A)                  │
│  Tasks → messages → artifacts → streaming   │
├─────────────────────────────────────────────┤
│  Transport (HTTP/HTTPS)                     │
└─────────────────────────────────────────────┘
```

An agent that needs to "find Portland city council votes on housing" goes through each layer:

1. **OAP discovery** matches the intent to mynewscast's manifest (vector similarity on the description)
2. **The manifest** tells the agent: this service speaks A2A, here's the Agent Card URL
3. **A2A protocol** handles the actual conversation — sending the task, receiving results, handling follow-ups

## Integration patterns

### Pattern 1: OAP manifest with A2A endpoint

The most common pattern. Publish an OAP manifest for discovery. Point the invoke URL at your A2A Agent Card or endpoint. Agents that speak A2A get the full conversational experience. Agents that don't can still POST and get a response.

```json
{
  "oap": "1.0",
  "name": "myNewscast",
  "description": "Government meeting intelligence agent. Processes meeting videos into structured transcripts with speaker identification, topic segmentation, and voting records. Searches past meetings by keyword, topic, or speaker. Retrieves full transcripts. Tracks voting patterns over time. Understands natural language requests and can handle follow-up questions for refinement.",
  "input": {
    "format": "application/json",
    "description": "A2A task message or plain JSON with a 'task' field describing what you need in natural language. The agent handles routing internally."
  },
  "output": {
    "format": "application/json",
    "description": "A2A task response with artifacts, or plain JSON with results. Response includes a 'type' field: transcript, search_results, summary, or vote_record."
  },
  "invoke": {
    "method": "POST",
    "url": "https://api.mynewscast.com/v1/agent",
    "auth": "bearer",
    "headers": {
      "X-Agent-Protocol": "a2a"
    }
  },
  "tags": ["a2a", "agent", "government", "meetings", "civic", "transcription"],
  "docs": "https://mynewscast.com/docs/agent",
  "health": "https://api.mynewscast.com/health"
}
```

The `tags` and `headers` signal A2A support. An A2A-aware agent sees these and uses the full protocol. A basic HTTP client just POSTs JSON and gets a response.

### Pattern 2: Pure OAP (one-shot capabilities)

Not everything needs to be an agent. A text summarizer, an image resizer, a currency converter — these are stateless functions. One request, one response. OAP handles these directly without A2A overhead.

```json
{
  "oap": "1.0",
  "name": "Summarize",
  "description": "Accepts any text and returns a concise summary. Handles documents up to 100,000 words.",
  "input": { "format": "text/plain", "description": "The text to summarize." },
  "output": { "format": "text/plain", "description": "A concise summary." },
  "invoke": { "method": "POST", "url": "https://summarize.example.com/api/v1/summarize" }
}
```

No A2A needed. The calling agent reads the manifest, POSTs text, gets a summary back. Done.

### Pattern 3: Single endpoint, agent discriminator

A middle ground. One invoke URL that accepts natural language. The service has an LLM (or router) behind it that interprets the request and handles it. Not full A2A, but smarter than a simple API.

```json
{
  "oap": "1.0",
  "name": "myNewscast",
  "description": "Government meeting intelligence service. Accepts natural language requests about civic meetings. Can process videos, search transcripts, retrieve records, and summarize decisions. Input is a plain English task description.",
  "input": {
    "format": "text/plain",
    "description": "Natural language description of what you need. Examples: 'Find Portland votes on housing in January 2026', 'Transcribe this meeting: https://youtube.com/watch?v=abc'."
  },
  "output": {
    "format": "application/json",
    "description": "Structured JSON with a 'type' field indicating result kind and corresponding data."
  },
  "invoke": {
    "method": "POST",
    "url": "https://api.mynewscast.com/v1/agent",
    "auth": "bearer"
  }
}
```

This is the "grep is an agent with a man page" philosophy. The agent behind the endpoint reasons about the request. The manifest doesn't need to enumerate every action — the description tells the calling LLM what's possible, and the endpoint handles the rest.

## When to use what

**Pure OAP** when your capability is a function: deterministic input → output, no conversation needed. Most capabilities fit here. A currency converter, a PDF renderer, a regex search tool.

**OAP + natural language endpoint** when your service handles multiple related tasks and you want the simplicity of a single manifest. The service has enough intelligence to interpret requests. No multi-turn conversation needed.

**OAP + A2A** when your service is genuinely conversational: it needs to ask clarifying questions, stream long-running results, manage task state, or coordinate with other agents. A meeting transcription agent that says "this video is 4 hours — full transcript or highlights?" is a real conversation.

The decision tree:

```
Does the caller need to have a conversation?
├── No  → Pure OAP manifest
│         Does it handle multiple task types?
│         ├── No  → Simple invoke (Pattern 2)
│         └── Yes → Natural language endpoint (Pattern 3)
└── Yes → OAP manifest + A2A (Pattern 1)
          OAP handles discovery, A2A handles conversation
```

## What OAP provides that A2A doesn't

**Discovery.** A2A defines Agent Cards but doesn't prescribe how agents find each other. OAP's manifest + crawler + vector DB architecture solves this. An agent that needs "something that can transcribe government meetings" queries the OAP discovery index and gets mynewscast back — without knowing the domain in advance.

**Simplicity.** Not every capability needs the A2A protocol stack. A text summarizer doesn't need task management, streaming artifacts, or multi-turn messaging. OAP gives it a manifest and a direct invoke URL. Five minutes to adopt, zero protocol overhead.

**Universal format.** OAP manifests describe any capability — HTTP APIs, command-line tools (`stdio`), A2A agents, MCP servers. The manifest is the common language. Discovery works the same regardless of what protocol the capability speaks.

## What A2A provides that OAP doesn't

**Multi-turn conversation.** OAP is one-shot: request in, response out. A2A supports ongoing task dialogues where the agent can ask questions, provide partial results, and refine output based on feedback.

**Streaming and artifacts.** A2A defines structured artifact delivery — an agent can stream back multiple documents, images, or data files as part of a single task response.

**Task lifecycle.** A2A manages task states (submitted, working, input-needed, completed, failed). Useful for long-running operations where the caller needs to check back.

**Agent-to-agent coordination.** A2A is designed for agents to delegate to other agents. If mynewscast needs to call a translation agent to handle a Spanish-language meeting, A2A provides the protocol for that delegation.

## The philosophy

OAP's core principle is separation of concerns:

- **The manifest describes.** What exists, what it does, what it accepts, what it produces.
- **Discovery finds.** Crawlers, vector DBs, LLMs match intents to manifests.
- **The protocol communicates.** HTTP for simple capabilities. A2A for conversational agents. MCP for tool-use contexts.

OAP is the DNS of capabilities — it resolves "I need X" to "here's where X lives and how to reach it." What happens after resolution is up to the communication protocol. A2A is one excellent answer for the conversation layer, and OAP makes sure agents can find A2A agents in the first place.

---

*This document accompanies the [Open Application Protocol specification](SPEC.md), [reference architecture](ARCHITECTURE.md), [trust overlay](TRUST.md), [manifesto](MANIFESTO.md), [robotics](ROBOTICS.md), [OpenClaw integration](OPENCLAW.md), and [Ollama tool bridge](OLLAMA.md). OAP is released under CC0 1.0 Universal — no rights reserved.*

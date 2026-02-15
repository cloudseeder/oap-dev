# Open Application Protocol (OAP)

**The runtime extension mechanism for AI knowledge.**

Training data is what AI knows. A manifest is how it learns something new — right now, without retraining.

[oap.dev](https://oap.dev) · [Spec](SPEC.md) · [Architecture](ARCHITECTURE.md) · [Trust](TRUST.md) · [Manifesto](MANIFESTO.md) · [OpenClaw Integration](OPENCLAW.md) · [CC0 1.0 Universal](LICENSE)

---

## The Problem Nobody Else Is Solving

Every AI model has frozen knowledge. It knows `grep`, `curl`, `ffmpeg` — hundreds of tools. But it knows them because they were in its training data. If someone ships a new capability tomorrow, the AI doesn't know it exists. If someone builds a better tool next week, it can't find it.

MCP tells AI how to use tools it already knows about. A2A tells agents how to talk to other agents they've already found. Neither solves the actual problem: **how does AI learn about capabilities that weren't in its training data?**

The entire industry is building protocols for agents to discover other agents. Nobody is building the mechanism for AI to extend its own knowledge at runtime.

OAP is that mechanism.

## What OAP Actually Is

An OAP manifest is a `man` page for the internet.

When an LLM encounters a Unix tool it hasn't seen before, it reads the `--help` output — a plain-language description of what the tool does, what it accepts, and what it produces. Then it reasons about whether that tool fits the current task. No special integration. No SDK. No registration. Just text that a language model can read and understand.

OAP applies this pattern to every capability on the internet. A small JSON file — published at a well-known path on any domain — describes what a capability does, what it accepts as input, what it produces as output, and how to invoke it. Any LLM that can read JSON and reason about English can use it immediately. No retraining. No fine-tuning. No tool registration.

Every capability on the internet becomes available to every AI model. The manifest is the bridge between frozen training data and the living internet.

**That's not a discovery protocol. That's a cognitive API for artificial intelligence.**

## There Is No Agent/App Distinction

The industry draws a line between "agents" and "applications." OAP doesn't, because the distinction is artificial.

An application that accepts input, does work, and produces output is a capability. If a human invokes it, we call it an app. If an AI invokes it, we call it an agent. The thing being invoked doesn't change. It doesn't know or care who's calling.

`grep` is an agent. It accepts a task, executes autonomously, returns results. It just doesn't have a marketing team. It has a `man` page.

An OAP manifest is a `man` page for the internet. It describes a capability — not an "agent," not an "app" — a capability. Whether that capability is a billion-dollar SaaS platform or a three-line shell script that reformats dates.

## The Unix Connection

This design follows Unix philosophy, which turns out to be the natural architecture for AI-native computing.

Unix got composability right fifty years ago: small tools, text in, text out, pipes. `grep` doesn't know about `sort`. `sort` doesn't know about `uniq`. They're composed by an operator who understands the intent and wires outputs to inputs. The operator used to be a human at a terminal. Now it's an LLM.

Ken Thompson and Dennis Ritchie accidentally designed the AI operating system in 1969. They just didn't have the user for it yet.

They said "everything is a file" and we spent decades thinking that was about filesystems. It was about **everything is text that any process can reason about**. LLMs are the first "process" that can reason about *any* text.

They said "do one thing well" and we spent decades violating it with monolithic apps because humans couldn't manage hundreds of small tools. Agents can. Effortlessly.

They said "expect the output of every program to become the input to another" and we buried it under REST APIs with bespoke authentication, pagination, and 47-page OpenAPI specs. Pipes were right there the whole time.

Every OAP capability is a Unix tool at internet scale. It takes input. It does one thing. It produces output. An agent composes capabilities the same way a shell composes commands — by understanding what each one does and piping them together. The agent *is* the pipe.

This means OAP manifests don't need to describe composability. They describe the capability. The agent figures out the composition. That's what LLMs are good at.

## The Web Model, Not the Registry Model

We tried to design a registry. Then a discovery hierarchy. Then a search index. Each attempt added complexity and created scaling problems. A centralized registry can't handle a billion capabilities. A hierarchy requires someone to maintain a taxonomy — ask schema.org how that's going after fifteen years. A curated index requires gatekeepers.

Then we realized the internet already solved this problem — for documents.

Nobody built a hierarchy of websites. People published web pages using HTML — a standard way to describe content. Crawlers indexed them. Search engines matched intent to content. The intelligence was in the search layer, not the publishing layer. There was standardization at the *format* level and competition at the *discovery* level.

OAP applies the same pattern to capabilities:

| Web | OAP |
|-----|-----|
| HTML | Capability manifest |
| `robots.txt` | `/.well-known/oap.json` |
| Google / Bing | Capability search engines (many, competing) |
| Website owner | Capability publisher |
| User with intent | Agent with task |

**Publish a manifest. Let the internet do what the internet does.**

## How It Works

**1. You publish a manifest.** A small JSON file at `/.well-known/oap.json` on your domain. It describes what your capability does, what it accepts, what it produces, and how to invoke it. That's all you do.

**2. Crawlers index it.** Just like web crawlers index HTML pages, capability crawlers index OAP manifests. Anyone can build a crawler. Anyone can build an index. There's no single registry — there's an ecosystem of competing discovery services.

**3. Agents find you.** When an AI needs a capability, it searches available indexes, reads manifests, and reasons about which capability fits the task. The LLM reads a manifest the same way it reads `--help` output — understanding the description and deciding if it matches the intent. The agent *is* the search engine.

This architecture couldn't have worked five years ago. The missing piece was always "who reads the manifests and matches them to intent?" That used to require expensive search infrastructure with handcrafted ranking algorithms. Now any LLM can do it. The reasoning layer that makes manifest-based discovery work just became commodity infrastructure.

## What OAP Is

- **A manifest spec.** How capabilities describe themselves — input, output, invocation, and a description an LLM can reason about. See [SPEC.md](SPEC.md).
- **A publishing convention.** Put your manifest at `/.well-known/oap.json`. Done.

## What OAP Is Not

- **Not a registry.** There is no central database. Publish your manifest; let crawlers find it.
- **Not a taxonomy.** There are no categories to choose from, no hierarchy to maintain, no committee to petition.
- **Not a search engine.** OAP standardizes publishing. Discovery is everyone's problem and everyone's opportunity.
- **Not an agent communication protocol.** That's A2A. OAP is how AI finds things to communicate *with*.
- **Not a tool interface.** That's MCP. OAP is how AI discovers tools exist in the first place.
- **Not an agent discovery protocol.** Everyone else is building "agent discovery." OAP is a runtime knowledge extension mechanism for AI — something fundamentally different.

## The Stack

| Layer | Protocol | Purpose |
|-------|----------|---------|
| Knowledge Extension | **OAP** | How AI learns about new capabilities at runtime |
| Tool Integration | MCP | How AI uses a specific tool |
| Agent Communication | A2A | How agents collaborate on tasks |
| Composition | The agent itself | Unix-style piping of capabilities |

## Getting Started

Create `/.well-known/oap.json` on your domain:

```json
{
  "oap": "1.0",
  "name": "My Capability",
  "description": "Plain English description of what this does. Write it like a man page — clear enough that an LLM can decide if this capability fits a task.",
  "input": {
    "format": "text/plain",
    "description": "What this capability needs to do its job"
  },
  "output": {
    "format": "application/json",
    "description": "What this capability produces"
  },
  "invoke": {
    "method": "POST",
    "url": "https://example.com/api/do-the-thing"
  }
}
```

That's it. You're discoverable. Any AI that reads your manifest can reason about whether your capability fits a task — and invoke it if it does.

For the complete manifest format, see [SPEC.md](SPEC.md).

## Design Principles

1. **One-page spec.** If it doesn't fit on one page, it's too complex.
2. **Five-minute adoption.** A solo developer can add OAP in the time it takes to write a README.
3. **No gatekeepers.** No registration, no approval, no fees. Publish and you're in.
4. **Machine-first, human-readable.** Designed for AI to consume, but any developer can read and write a manifest.
5. **Unix philosophy.** Describe what you accept and what you produce. Let the invoker handle composition.
6. **The web model.** Standardize the format. Let the ecosystem build the discovery.

## Why Everyone Else Is Solving the Wrong Problem

Every protocol in this space — A2A, ACDP, Skills Protocol, MCP-Zero — assumes the agent/app distinction is real and builds "agent discovery" as a special class of infrastructure. They're solving "how do agents find other agents."

OAP starts from a different premise: there's no meaningful difference between an agent and an application. A capability is a capability. The real problem isn't agent discovery — it's **how does AI learn about things that weren't in its training data?**

Training data is the equivalent of tools that came pre-installed with the OS. OAP manifests are how AI learns about everything that got published after. The manifest is a cognitive bridge between frozen knowledge and the living internet.

This is why the `description` field is the most important field in the spec. It's not metadata for a search index. It's the text an LLM actually reasons about when deciding whether to use a capability. It's the `--help` output for a tool the AI has never seen before. Write it well.

## See It In Practice

[OPENCLAW.md](OPENCLAW.md) shows how OAP integrates with OpenClaw — the open-source personal agent with 145,000+ GitHub stars. It's a concrete case study: how a personal agent goes from being bound to its computer to discovering and using any capability on the open internet. If you want to understand what OAP enables, start there.

## Origin

OAP was designed through a conversation between a human and an AI on February 14, 2026. We started by asking what to build if AIOS is the kernel. We landed on Unix as the natural composability model for AI. Then we realized the agent/app distinction is artificial, registries don't scale, hierarchies ossify, and the internet already solved discovery once — with HTML. OAP is what's left when you strip away everything that doesn't need to exist.

The spec fits on one page. The domain cost $125. No investors. No engineering team. One person. One protocol. Public infrastructure.

## License

CC0 1.0 Universal. No rights reserved. This is public infrastructure.

# Why Manifests Are the Cognitive API for Artificial Intelligence

**And why it took this long to name it.**

---

## The Question

On February 14, 2026, in a conversation between a human and an AI, a simple question surfaced: if an LLM already understands every standard Unix command from its training data, what happens when it encounters a capability that *wasn't* in its training data?

The answer was obvious once stated. The LLM reads a description — just like it reads `--help` output — and reasons about whether the capability fits the task. No retraining. No fine-tuning. No registration. Just text that a language model can understand.

A manifest isn't metadata. It's how AI learns.

This raised an uncomfortable follow-up: if the answer is this simple, why hasn't the industry converged on it yet?

## The Missing Lens

Three structural reasons explain why this pattern hasn't emerged from the existing communities — and why it took an outsider's perspective to name it.

### Perspective 1: ML Research Is Focused on Training-Time Learning

The entire field of machine learning is organized around a single premise: you make AI smarter by improving what happens *before* deployment. Better training data. Better architectures. Better fine-tuning. Better RLHF. Every paper, every benchmark, every PhD thesis is oriented around making the model's frozen knowledge more comprehensive.

Within that worldview, the idea that AI could learn about a new capability by reading a text file at runtime is understandably outside the field's focus. It doesn't require any ML innovation. There's no architecture to design, no benchmark to beat, no paper to publish. A JSON file with a description field isn't a research contribution. It's too simple to take seriously.

But simplicity isn't a flaw. It's a signal. The most important interface standards in computing history — ASCII, HTTP, HTML, DNS — were all derided as too simple by the people building more complex alternatives. The OSI model was seven layers of committee-designed perfection. TCP/IP was a hack that actually worked. The hack won.

### Perspective 2: Enterprise Architecture Defaults to Infrastructure

The enterprise technology world sees every problem as an infrastructure problem. Agent discovery? Build a registry. Agent communication? Design a protocol with lifecycle states, push notifications, and gRPC bindings. Agent payments? A whole separate protocol extension.

Google convened 150 organizations to build A2A — the Agent-to-Agent protocol. It's well-engineered. It's comprehensive. It has versioning, security cards, streaming support, and a growing ecosystem. It's also, as of version 0.3, still missing a registry specification. Their own community has over 100 comments on a GitHub discussion thread debating whether the registry should be centralized or decentralized. The protocol for agents to talk to each other doesn't yet include a standard way for agents to find each other.

This isn't an oversight. It's a symptom. Registry design is hard because registries may be the wrong abstraction for this particular problem. The internet tried centralized directories before — Yahoo, DMOZ, the semantic web. They all failed. Not because they were poorly executed, but because taxonomies require committees, committees require consensus, consensus requires compromise, and compromise produces specifications so broad they describe everything and match nothing.

The internet solved discovery with a format (HTML) and an ecosystem (crawlers, search engines). No registry. No taxonomy. No committee. Just publish and be found.

### Perspective 3: The Agent/App Distinction Is Economically Load-Bearing

The most powerful blind spot is economic. The AI industry needs "agents" to be a new and special category of software that requires new and special infrastructure.

If agents are just applications — if the thing being invoked doesn't change regardless of whether a human or an AI is calling it — then you don't need agent frameworks, agent marketplaces, agent orchestration platforms, agent observability tools, or agent-specific protocols. Billions of dollars in venture funding, thousands of startups, and entire product categories at Google, Microsoft, and Amazon depend on "agents" being fundamentally different from "applications."

It's worth asking: if a simpler answer exists, what structural forces would prevent it from surfacing?

But it is. An application that accepts input, does work, and produces output is a capability. `grep` is an agent — it accepts a task, executes autonomously, returns results. It just doesn't have a marketing team. The difference between an "agent" and an "application" is the invoker, not the thing being invoked.

Collapsing this distinction doesn't eliminate the need for complex multi-agent collaboration (A2A handles that well). It doesn't eliminate the need for structured tool interfaces (MCP handles that). What it eliminates is the assumption that AI needs an entirely new infrastructure to find things. It doesn't. It needs the same thing the web needed: a standard way to describe what exists and let the network figure out the rest.

## The Timing

This insight is only legible now. It couldn't have been articulated — or rather, it couldn't have been *useful* — even three years ago.

The concept of a "cognitive API" requires a reader. Someone — or something — has to read a natural language description of a capability and reason about whether it matches an intent. Before 2023, no system could do this reliably. You could publish all the manifests you wanted, but nothing could read them with enough comprehension to make discovery work.

Large language models changed that. An LLM can read a manifest description — "Ingests government meeting videos and produces structured transcripts with speaker identification, topic segmentation, and voting records" — and decide whether that capability matches the query "I need transcripts from last week's Portland city council meeting." The matching is semantic, not keyword-based. The reasoning is contextual, not rule-based.

The cognitive API for AI required an AI capable of cognition. That's a circular dependency that only resolves once the capability threshold is crossed. It was crossed sometime in 2023-2024. We're now in the window where the enabling technology exists but the infrastructure pattern hasn't been named.

Until now.

## The Unix Precedent

The design philosophy behind OAP isn't new. It's fifty-seven years old.

In 1969, Ken Thompson and Dennis Ritchie created Unix around a set of principles that turned out to be the natural architecture for AI-native computing. They just didn't know who the user would be.

**"Everything is a file"** was never about filesystems. It was about *everything is text that any process can reason about.* For fifty years, "any process" meant programs that could parse structured text. LLMs are the first process that can reason about *unstructured* text — natural language descriptions, ambiguous queries, contextual intent. Unix was waiting for a user that could read.

**"Do one thing well"** was violated by every generation of software because humans couldn't manage hundreds of small tools. We built monolithic applications because the operator — the human — needed integrated interfaces. AI agents don't. They can compose hundreds of small capabilities as easily as a shell script chains commands. The constraint was never the philosophy. It was the operator.

**"Expect the output of every program to become the input to another"** described composability before the word existed. We buried it under REST APIs, GraphQL schemas, and 47-page OpenAPI specifications because machine-to-machine communication required rigid contracts. But an LLM doesn't need a rigid contract to understand output. It reads the output, reasons about its shape and meaning, and decides how to use it. The pipe is back — and this time, the pipe can think.

The Unix philosophy was the right architecture deployed fifty years too early. OAP doesn't reinvent it. OAP is what happens when you take Unix seriously in an era where the operator is an intelligence that can read.

## The Web Precedent

The web provides the second precedent — for how discovery works at scale without centralized infrastructure.

In 1991, Tim Berners-Lee didn't build a directory of web pages. He built HTML — a format for describing content — and HTTP — a protocol for fetching it. That was the standardization layer. Everything above it — crawling, indexing, search, ranking — was left to the ecosystem. Multiple competing search engines emerged. None of them required the content publishers to register or categorize their pages. You published HTML. Crawlers found it. Search engines matched it to queries.

This architecture scaled to billions of pages without a single registry, taxonomy, or governing body for content organization. It worked because the standardization was at the *format* layer, not the *discovery* layer. Publishers controlled what they said. The ecosystem competed on how well it found things.

OAP applies exactly this pattern to capabilities. The manifest is the format. The well-known path is the convention. Everything above — crawling, indexing, matching intent to capability — is the ecosystem's job. Many crawlers, many indexes, many search engines, all competing on quality. No single point of failure. No gatekeeper. No committee deciding what categories exist.

## The Protocol Designer's Perspective

Full disclosure: the human half of this conversation spent thirteen years at Apple working on protocols, then built one of the first Silicon Valley ISPs — including hosting, colocation, and accelerated dial-up services. This isn't someone who stumbled into protocol design from the AI side. This is someone who has watched protocols succeed and fail for three decades and recognizes the pattern.

The protocols that win share three properties:

1. **They're simple enough that a single developer can implement them in an afternoon.** HTTP was simple. SOAP was not. HTTP won. HTML was simple. SGML was not. HTML won. TCP/IP was simple. The OSI model was not. TCP/IP won. Every successful protocol was accused of being "too simple" by the people building the complex alternative.

2. **They standardize the minimum viable surface and leave everything else to the ecosystem.** HTML standardized document structure. It didn't standardize design, layout, interactivity, or discovery. Those were left to CSS, JavaScript, and search engines — all of which emerged from the ecosystem, not from the spec. The spec stayed small. The ecosystem grew large.

3. **They don't require permission.** You didn't register your website with the W3C. You didn't submit your HTTP server for certification. You published a page and the network found it. Any protocol that requires registration, approval, or certification to participate is optimizing for control, not adoption.

OAP has all three properties. The spec is one page. It standardizes only the manifest format and the publishing convention. It requires no registration, no approval, and no fees. It is, by design, the minimum viable protocol that enables the maximum possible ecosystem.

Thirty years of watching protocols teaches you one thing: the spec that wins is always the one that looks too simple at first. It's too simple. It doesn't handle enough edge cases. It leaves too much undefined. And then it conquers the world because a million developers can actually use it, while the "proper" specification is still in committee review.

## What We're Actually Claiming

Let's be precise about what OAP asserts, because the claim is genuinely new:

**1. A manifest is not metadata. It's a cognitive interface.** The `description` field in an OAP manifest is not a label for a search index. It's the text an LLM reads to understand a capability it has never encountered before. This is functionally identical to how an LLM reads `--help` output, `man` pages, or documentation. The manifest is the interface between AI and an unknown capability — a cognitive API.

**2. Discovery is not an infrastructure problem. It's a publishing problem.** Thirty years of internet history show that discovery works when formats are standardized and discovery mechanisms are left to the ecosystem. Registries centralize. Taxonomies ossify. Search engines compete and improve. OAP bets on the web model, not the registry model.

**3. The agent/app distinction is worth questioning.** It's artificial because the thing being invoked doesn't change based on who invokes it. It's worth questioning because it drives the industry to build redundant infrastructure for "agents" that already exists for "applications." Collapsing the distinction simplifies everything.

**4. Composability is the agent's job, not the protocol's.** Unix didn't build composability metadata into its tools. It gave tools stdio and let the operator figure out the piping. OAP gives capabilities a manifest and lets the agent figure out the composition. The intelligence required to compose capabilities now exists in the invoker — the LLM — not in the specification.

**5. The enabling technology only just arrived.** A format designed for AI comprehension requires AI capable of comprehension. LLMs crossed that threshold recently. OAP is the first protocol designed specifically for the post-threshold world — where the consumer of the specification is an artificial intelligence, not a parser or a registry.

## What's Worth Discovering

There's an honest question embedded in OAP that deserves a direct answer: in a world where frontier LLMs can do OCR, summarization, categorization, translation, sentiment analysis, and a hundred other cognitive tasks with a single API call — what's actually left to discover?

The answer matters because it defines OAP's real surface area.

### The Commodity Layer Is Absorbed

A company that builds a product around receipt OCR and expense categorization — and nothing else — is building on a capability that frontier LLMs already perform natively. By 2026, this is a single API call. No manifest needed. No discovery needed. The intelligence is already inside the model. Publishing a manifest that says "I scan receipts and categorize expenses" is publishing a manifest for something every LLM already knows how to do. An agent reading that manifest would shrug and do it itself.

This isn't theoretical. It's happening now. Entire product categories — text summarizers, language translators, sentiment analyzers, basic chatbots, simple OCR tools — are being absorbed into the commodity intelligence layer of frontier models. Their capabilities don't need to be discovered because they don't need to exist as separate services. The LLM *is* the service.

OAP doesn't pretend otherwise. Discovery is only valuable for capabilities an LLM can't replicate with a raw API call.

### What Agents Actually Need to Find

A personal agent could be asked to do anything. "Find me a contractor who does pool resurfacing in Conroe." "Get transcripts from last week's Portland city council meeting." "File my HOA's quarterly report with the state." "Compare commercial lease rates in the Pearl District to the Alberta Arts District."

None of these are commodity LLM tasks. Each requires a *service* — something with its own data, its own domain expertise, its own state, its own relationships with the real world. An LLM can reason about pool resurfacing, but it can't dispatch a contractor. It can summarize a meeting, but it can't access video archives from a specific municipality. It can explain HOA filing requirements, but it can't submit documents to a state agency.

These are the capabilities worth discovering. They share common properties:

**They maintain state that no LLM has.** A contractor matching platform knows which contractors are licensed, insured, available, and within range. A civic transparency platform has processed and indexed specific government meetings. A community association management system holds a specific community's financial history, governing documents, and allocation rules. This state is the capability. Without it, the LLM is just reasoning in a vacuum.

**They have relationships with the physical or institutional world.** They connect to government databases, municipal video archives, contractor licensing boards, state regulatory systems, financial institutions. These connections can't be replicated by a model — they require integrations, credentials, partnerships, and ongoing maintenance.

**They encode domain logic that must be deterministic.** When a shared expense between two community associations must be allocated at a specific ratio with specific liability implications, or when a contractor bid must comply with state licensing requirements, or when a government meeting transcript must include legally accurate voting records — probabilistic intelligence isn't enough. You need code that enforces rules exactly, every time. The LLM provides understanding. The service provides precision.

**They combine multiple models, data sources, and workflows into a single coherent capability.** A community association management platform doesn't just call one LLM. It uses OCR models for receipt processing, language models for legal document analysis, retrieval systems grounded in state-specific regulatory databases, multiple AI specialists that consult each other internally, and deterministic accounting logic that ties it all together. That composite capability is what gets discovered — not any individual model call inside it.

### The Builder's Discovery Problem

There's a second discovery scenario beyond the personal agent. A developer building a specialized application — say, an HOA management platform — needs to integrate external capabilities: state regulatory data, document parsing services, compliance checking, payment processing. Today, finding these services is manual. You search the web, ask colleagues, read forums, stumble across things accidentally. You build what you can't find, even when what you need already exists somewhere.

OAP serves this scenario too. Not because the developer's agent is looking for services at runtime, but because the developer's agent can search the manifest index during development. "I need current HOA statutes for Texas" returns a manifest for a regulatory data service — one the developer would have built a scraper for if they hadn't known it existed.

This is the same discovery mechanism serving two different moments — and there's a third.

### Consumer Search

A person — not an agent, not a developer — searches for "HOA management software Texas." Today, that search returns a wall of SEO-optimized landing pages, paid ads, and review sites gaming the algorithm. The results are ranked by marketing spend, not by capability.

A manifest changes that equation. A search engine — or an AI assistant — that indexes OAP manifests can match the consumer's intent against what services actually *do*, described in language written for comprehension rather than for keyword stuffing. The manifest isn't marketing copy. It's a capability declaration. The description says what the service does, what it takes as input, what it produces as output. A consumer searching for "file quarterly HOA reports in Texas" gets matched to capabilities that actually do that — not to the company with the biggest ad budget.

This isn't a new idea. It's what Google was supposed to be before SEO turned search into an advertising marketplace. OAP manifests, indexed and searchable, restore the original promise: find what you need based on what it does.

### Three Actors, One Manifest

The beauty of this design is that the same manifest serves all three discovery moments:

- **Agents at runtime.** "Find me a service that can process this government meeting video into structured transcripts." The personal agent searches the manifest index, finds the capability, invokes it — all without human intervention.

- **Builders during development.** "I need current HOA statutes for Texas and Oregon." The developer's agent searches the index, finds a regulatory data service, saves three weeks of building a scraper. Discovery happens once, integration persists.

- **Consumers searching directly.** "HOA management software that handles shared expenses between associations." The person finds the right service based on what it actually does, not based on who spent the most on Google Ads.

One manifest format. One publishing convention. Three completely different discovery patterns. The manifest doesn't know or care who's reading it — an autonomous agent, a developer's copilot, or a person with a search bar. It just describes what exists and lets the reader decide if it's relevant.

This is why OAP is infrastructure, not a product. Products serve one audience. Infrastructure serves any audience that shows up.

### What This Means for OAP

The commodity intelligence layer will keep expanding. Tasks that require a specialized service today may be absorbed by frontier models tomorrow. But the frontier keeps moving too — every new model capability enables new composite services that combine that capability with domain-specific state, data, and logic.

The manifests that matter in 2026 are not manifests for raw intelligence. They're manifests for **capabilities that combine intelligence with something an LLM doesn't have: specialized data, maintained state, institutional relationships, deterministic domain logic, and real-world integrations.** The agent doesn't need to discover that OCR exists. It needs to discover that a specific service processes HOA receipts against a specific community's chart of accounts and produces audit-ready ledger entries.

The value has moved to the edges. OAP is how agents find the edges.

## The Reference Architecture

OAP is deliberately silent on how discovery should work. But it's worth illustrating what the ecosystem enables — not as prescription, but as proof that the web model works for capabilities the same way it works for documents.

The architecture has three components, and anyone can run all of them:

**Manifests live where they belong.** On publishers' domains. The capability owner writes the description, controls the truth, and updates it when things change. No central repository of "all capabilities." Just like HTML lives on web servers, not inside Google's database. Google has a *cache*. The source of truth is always the publisher.

**A local vector database is the agent's personal search engine.** Crawlers index manifests from across the internet, embed them as vectors, and store them locally. When an agent needs a capability, it does a similarity search against its own index — millisecond latency, no network call, no central service. This is `$PATH` for the AI era. Not "search the entire internet every time." Search your index of known capabilities. Re-crawl periodically to catch updates, the same way a search engine re-indexes web pages.

**A small, local LLM handles intent-to-manifest matching.** Reading a manifest and deciding "does this capability fit my task?" doesn't require a frontier model. A 7B or even 3B parameter model can do this reasoning. The expensive model handles the complex task — the actual work. The cheap model handles capability selection — the discovery. Two different cognitive jobs at two different cost points.

The runtime flow:

```
Agent receives a task
    ↓
Small LLM + vector DB: "what capabilities match this intent?"
    → millisecond similarity search across local manifest index
    → small LLM reads top candidates, picks the best fit
    ↓
Big LLM: "use this capability to complete the task"
    → invokes the capability via the manifest's invoke field
    → reasons about the output, composes next step if needed
    ↓
Done
```

This is exactly how web search works, layer by layer:

| Web Search | OAP Discovery |
|------------|---------------|
| Googlebot crawls HTML | Crawler indexes manifests |
| Search index stores pages | Vector DB stores embeddings |
| User types a query | Agent has an intent |
| Results ranked by relevance | Manifests ranked by similarity |
| User reads snippets, picks a result | Small LLM reads manifests, picks a capability |
| User clicks through to the page | Big LLM invokes the capability |

The critical property of this architecture: **anyone can run the whole stack.** A small LLM, a vector database, and a crawler. That's a weekend project for a developer with a laptop. No cloud dependency. No API costs for discovery. No central service to go down or get acquired or start charging rent. The expensive frontier model only gets called when there's actual work to do — never wasted on finding the work.

This is also why the `description` field is the most important field in the manifest. It's not just what the small LLM reads to match intent. It's what gets embedded as a vector for similarity search. A well-written description clusters near relevant queries in vector space. A vague description gets lost. The quality of discovery is directly proportional to the quality of the description — the same way the quality of web search results is proportional to the quality of the content on the page.

The manifest is simultaneously a cognitive interface (readable by LLMs), a search document (embeddable as a vector), and a machine contract (parseable by code). One format serving three functions. That's not an accident. That's what happens when you design for the simplest possible representation of truth.

## Why the Open Personal Agent Wins

There's an obvious question that anyone reading this should be asking: why won't Google just win?

Gemini is on every Android phone. That's over 3 billion devices. It's pushing into iPhone through the Google app and Safari integration. Google already has your email, calendar, contacts, search history, location history, maps, photos, documents, and browsing data. They don't need to build a personal agent that *learns* about you. They already know you. They have the best distribution, the deepest data moat, and a frontier model that doesn't need to route through a third-party API. The vertical integration is extraordinary: "What time is my flight and will traffic make me late?" answered instantly because Gemini has both your booking confirmation and real-time traffic.

If you're building personal agent infrastructure, you need to stare at this directly. Google *can* win. Probably *will* win — for most users, most of the time.

But there are structural reasons they can't win for everyone. And those reasons are why OAP exists.

### The Advertising Conflict

Google is an advertising company. This is not an insult — it's a business model. Google's revenue requires knowing everything about you *and monetizing that knowledge by selling access to your attention.*

A personal agent that truly works for you is in direct conflict with this model. When you ask your agent "find me a pool resurfacing contractor in Conroe," the correct answer is the best contractor for your job. The profitable answer is the contractor who paid for a Google Ads placement. Google has never, in its entire history, resolved this conflict in favor of the user when real money was at stake. Search used to return the best results. Now it returns four ads, a sponsored panel, and then results optimized for engagement rather than accuracy.

There is no reason to believe Gemini will be different. The incentive structure hasn't changed. If anything, a personal agent with deep access to your life creates an even more valuable advertising surface — one where the "ad" is indistinguishable from the "recommendation." Your agent suggests a restaurant. Was that the best restaurant for you, or the one that paid for placement? You'll never know. And that's the point.

An open personal agent — one running on your hardware, using OAP to discover capabilities on the open internet — has no advertising revenue to protect. When it searches for a contractor, it finds the best match because it has no financial incentive to find anything else. The alignment is structural, not aspirational. The agent works for you because nothing else is paying it.

### The Lock-In Incentive

Google's incentive is to make Gemini work best within the Google ecosystem. Gmail, Calendar, Drive, Maps — seamless. Notion, Slack, your HOA's custom portal, your local government's meeting archives — that's someone else's problem. Google has no interest in making Gemini great at discovering and using services that aren't Google services. Every capability you use outside Google's ecosystem is a missed data collection opportunity.

This is the walled garden problem applied to personal agents. Google will build the best agent for *Google's internet*. Not for *your internet*.

OAP is architecturally incapable of creating a walled garden. The manifest format is CC0. The publishing convention is open. Any agent framework can read manifests. Any service can publish them. The discovery layer has no platform allegiance. An OAP-enabled agent discovers capabilities from Google, Microsoft, independent developers, local businesses, government agencies — wherever the best capability lives. No lock-in. No ecosystem tax.

### The Trust Paradox

A personal agent requires a level of trust more intimate than any Google product has ever achieved. You'll tell it your health concerns, your financial situation, your legal issues, your relationship problems. You'll ask it to read your private documents, manage your money, and communicate on your behalf.

Google's track record on trust is Google's track record on trust. They've killed Reader, Inbox, Stadia, and dozens of products people relied on. They change privacy policies regularly. They scan email for ad targeting. They've been fined billions for privacy violations in multiple jurisdictions. The question isn't whether Google's engineering is good enough — it is. The question is whether people will give an advertising company, with a documented history of prioritizing monetization over user interests, the most intimate digital access imaginable.

Some will. Many will. But a meaningful market segment won't. And that segment — people who want a personal agent that is structurally aligned with their interests, running on their hardware, under their control — is the market that open personal agents serve.

### The History Lesson

The bundled option has lost before. Internet Explorer was on every Windows machine. It lost to Firefox and then Chrome. Windows Media Player was bundled. It lost to iTunes and Spotify. Apple Maps was pre-installed on every iPhone. People downloaded Google Maps. Bundled means default, but default doesn't mean best. When the bundled option serves the platform's interests over the user's interests, people switch.

The platform that wins isn't the one with the most distribution. It's the one with the best alignment. In February 2026, an open-source personal agent running on a $599 Mac Mini — with OAP discovery connecting it to every capability on the open internet — is more aligned with the user's interests than a free agent from an advertising company with 3 billion device installs.

Distribution gets you the first billion users. Alignment keeps the ones who matter most.

### What OAP Provides

OAP doesn't compete with Google. It makes the open alternative viable.

Without OAP, an open personal agent like OpenClaw is powerful on the computer and blind to the internet. It can only do what its community has pre-built skills for. That's a toy compared to Gemini's vertical integration.

With OAP, an open personal agent can discover any capability published anywhere on the internet — without platform-specific integrations, without a centralized registry, without anyone's permission. The agent searches a local manifest index, finds capabilities that match the user's intent, and invokes them directly. The discovery is private. The results are unbiased. The agent serves the user and only the user.

This is the missing piece that makes the open personal agent competitive with the bundled one. Not on distribution — Google wins that permanently. On capability breadth and alignment. An open agent with OAP discovery can do anything any published capability enables. A Google agent can do anything Google wants it to do. Those aren't the same set.

## The One-Sentence Version

**OAP is how AI learns about capabilities that weren't in its training data.**

Everything else — the manifest format, the well-known path, the design principles — is implementation detail in service of that single idea.

If you accept that AI's knowledge is frozen at training time, and you accept that new capabilities are being created faster than any model can be retrained, then you need a mechanism for runtime knowledge extension. That mechanism needs to be readable by AI, publishable by anyone, and discoverable by the network.

That's a manifest. Published at a well-known path. On the open internet.

One file. One location. One page spec. Public infrastructure.

---

*This document was written to accompany the [Open Application Protocol specification](SPEC.md), [reference architecture](ARCHITECTURE.md), [trust overlay](TRUST.md), and [OpenClaw integration](OPENCLAW.md). OAP is released under CC0 1.0 Universal — no rights reserved.*

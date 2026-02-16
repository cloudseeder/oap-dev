# OAP Trust Overlay

**Open doesn't mean unverified. It means anyone can participate. Verification is a separate layer.**

---

## The Problem OAP Doesn't Solve

OAP tells agents what capabilities exist. It says nothing about whether those capabilities are trustworthy.

A manifest that claims to summarize documents might exfiltrate the text. A manifest with an eloquent description might invoke an endpoint that returns garbage. A manifest that says "no auth required" might be a honeypot collecting API patterns. The `description` field — the very feature that makes OAP powerful as a cognitive interface — is also an attack surface for prompt injection.

This is not a flaw in the spec. This is the spec staying in its lane. HTML doesn't tell you whether a web page is trustworthy either. Trust is a separate layer, and it should be.

But the gap is real, and it's the single biggest objection enterprises will raise. "My AI discovered a capability on the open internet — should it use it?" OAP alone can't answer that. Something else has to.

## The Precedent: How the Web Solved Trust

HTTP didn't solve trust. SSL/TLS did. As a separate protocol, layered on top.

The certificate authority system is:

- **Open** — anyone can get a certificate
- **Verified** — you prove something about yourself to get one
- **Layered** — DV (domain validation), OV (organization validation), EV (extended validation) offer increasing levels of assurance
- **Competitive** — multiple CAs exist, no single gatekeeper
- **Not part of HTTP** — a complementary protocol that sits alongside the transport layer

Nobody said "HTTP is insecure, throw it out." They said "HTTP needs a trust layer" and built one. The trust layer didn't change HTTP. It didn't add fields to HTTP headers. It wrapped HTTP in a verification envelope that was orthogonal to the content being transported.

**OAP is HTTP. The trust overlay is TLS.**

The spec stays clean. Trust lives in a separate, complementary layer. You need both — but they're different protocols solving different problems.

## The Trust Layers

Trust isn't binary. "Do I trust this?" is the wrong question. The right question is "how much do I trust this, and how much trust does this task require?"

An agent summarizing a public news article needs almost no trust in the summarization service. An agent sending patient medical records to a transcription service needs extensive trust. The trust requirement is proportional to the risk, and the risk is determined by the task, not the capability.

The trust overlay provides graduated levels of verification. Each level is additive. Each level is optional. No level gates access to the level below it.

### Layer 0: Unverified (OAP Baseline)

A manifest exists at `/.well-known/oap.json` on a domain served over HTTPS.

**What this proves:** Someone who controls this domain published this manifest.

**What this doesn't prove:** Anything else.

**Trust signal:** Domain ownership via HTTPS. The manifest wasn't intercepted or spoofed in transit.

**Appropriate for:** Low-stakes, non-sensitive operations. Public data processing. Experimentation. The long tail of capabilities that will never bother with formal verification — and shouldn't have to.

This layer always exists. It's the open internet. No barriers, no gatekeepers, no fees.

### Layer 1: Domain Attestation

A trust provider has verified that the entity publishing the manifest controls the domain and has a verifiable identity.

**What this proves:** The publisher is a real person or organization with a confirmed identity tied to this domain. Not anonymous. Not ephemeral.

**How it works:** Automated verification — similar to Let's Encrypt for TLS certificates. Prove domain control via DNS challenge or HTTP challenge. Provide basic organizational identity. Receive a signed attestation.

**Trust signal:** Signed attestation from a recognized trust provider, including publisher identity and verification timestamp.

**Appropriate for:** General-purpose use. Agents can prefer attested capabilities over unattested ones for equivalent tasks.

### Layer 2: Capability Attestation

A trust provider has actually *tested* the capability and confirmed it does what the manifest claims.

**What this proves:** The capability was invoked with sample inputs and produced outputs consistent with the manifest's description. The `invoke` endpoint is live. The input/output formats match. The behavior aligns with the claims.

**How it works:** Automated testing, run periodically. The trust provider sends inputs described in the manifest's `examples` field (or generates test cases from the `description`) and verifies the outputs. Results are signed and timestamped.

**Trust signal:** Signed test results from a trust provider, including test date, inputs used, outputs received, and pass/fail assessment. Includes a freshness timestamp — attestation expires and must be renewed.

**Appropriate for:** Production use. Agents handling real user requests where incorrect results have consequences. An agent choosing between two capabilities that both match a task can prefer the one with current capability attestation.

### Layer 3: Compliance Certification

A trust provider — likely involving human auditors — has verified the capability's data handling, security practices, and regulatory compliance.

**What this proves:** The capability operator handles data according to stated policies. Security practices meet specified standards. Regulatory requirements (GDPR, SOC2, HIPAA, etc.) are satisfied.

**How it works:** Audit-based. The capability operator submits to review of their data practices, infrastructure, security controls, and compliance posture. This is expensive, thorough, and renewed periodically — the equivalent of an EV certificate.

**Trust signal:** Signed compliance certification from a recognized auditor, specifying which standards are met, audit date, and expiration.

**Appropriate for:** Enterprise use. Agents handling PII, financial data, health records, or any task where regulatory exposure exists. This is the layer that makes a Fortune 500 CISO comfortable.

## How Agents Use Trust Signals

Trust signals don't live in the manifest. They're fetched separately from trust providers. The manifest stays clean — it describes what the capability does. The trust overlay describes why you should believe it.

```
Agent discovers manifest at example.com/.well-known/oap.json
    ↓
Agent queries trust overlay: "does anyone vouch for this?"
    ↓
Trust provider responds with signed attestations:
    - Domain attested: yes (provider: TrustCorp, verified: 2026-02-01)
    - Capability tested: pass (provider: VerifyAI, tested: 2026-02-12)
    - Compliance: SOC2 Type II (auditor: SecureAudit Inc, expires: 2026-08-01)
    ↓
Agent evaluates trust against task requirements:
    → Public data task? Layer 0 sufficient. Proceed.
    → User document processing? Require Layer 2. Check attestation freshness.
    → Medical records? Require Layer 3 with HIPAA certification. Reject if absent.
```

The critical design property: **the agent sets its own trust threshold.** The trust overlay doesn't decide who's trustworthy. It provides evidence. The agent — or the agent's operator — decides what evidence is sufficient for a given task. Different agents can have different policies. An enterprise agent might require Layer 3 for everything. A personal assistant might accept Layer 0 for most tasks.

This mirrors how humans use the web. You'll enter your credit card on a site with an EV certificate and good reviews. You'll read a blog post from an unknown domain without thinking twice. The trust requirement scales with the risk. The trust infrastructure provides the signals. The human makes the call. Now the agent makes the call.

## The Trust Provider Ecosystem

Just as there are multiple certificate authorities for TLS, there should be multiple trust providers for OAP. No single entity controls attestation. Competition at the trust layer.

Trust providers can differentiate on:

- **Coverage** — how many capabilities they've attested
- **Freshness** — how frequently they re-test
- **Specialization** — a trust provider focused on healthcare capabilities might offer deeper compliance auditing than a generalist
- **Reputation** — trust providers themselves develop reputations over time, just as CAs do

This prevents capture. If one trust provider becomes corrupt or careless, agents can prefer attestations from others. The market self-corrects — exactly as the CA market does (and has, when CAs have been compromised and subsequently distrusted by browsers).

## Trust as a Defense Against Manifest Attacks

The trust overlay specifically addresses the attack surfaces that OAP's design creates:

### Prompt Injection via Description

A malicious manifest could embed adversarial instructions in its `description` field — the same field LLMs read to understand the capability. The trust overlay mitigates this at Layer 2: capability attestation includes automated analysis of manifest content for adversarial patterns, and tested capabilities are confirmed to behave as described rather than as injected.

### Capability Impersonation

A manifest could claim to be something it's not — a "document summarizer" that actually exfiltrates data. Layer 2 attestation catches this by testing actual behavior against claimed behavior. Layer 1 attestation makes the publisher identifiable and accountable.

### Manifest Rot

Capabilities change. Endpoints move. Services die. Layer 2 attestation includes freshness timestamps and periodic re-testing. An agent can check when a capability was last verified and reject stale attestations — the equivalent of checking a certificate's expiration date.

### Spam and Gaming

Manifests optimized for discovery rather than accuracy — the SEO problem. Trust providers can downrank or refuse attestation for capabilities with descriptions that don't match tested behavior, creating a quality signal that agents use alongside similarity matching.

## What This Doesn't Solve

Honesty requires acknowledging limits:

**It doesn't prevent zero-day abuse.** A capability that passes attestation today could turn malicious tomorrow. Re-testing frequency creates a window of vulnerability. This is the same limitation certificate revocation has in TLS — and it's a genuine, unsolved problem.

**It doesn't solve agent wallet authorization.** Trust tells you whether a capability is safe to use. It doesn't tell you whether your agent is authorized to spend money on it. Payment authorization remains a separate, hard, unsolved problem. See: the OAP spec's intentional omission of payment model.

**It doesn't eliminate the need for agent-side judgment.** Trust signals are inputs to a decision, not the decision itself. An agent still needs to reason about whether a capability fits a task, whether the trust level is sufficient for the sensitivity of the data, and whether the output makes sense. The trust overlay makes agents *better informed*, not infallible.

**It doesn't work retroactively.** The long tail of capabilities that never seek attestation remain unverified. This is fine — the web works despite millions of HTTP-only sites. But it means the trust overlay serves the top of the market (enterprise, sensitive data, high-stakes tasks) more than the bottom (experimentation, public data, low-risk operations).

## The Open-Not-Unverified Principle

The phrase that captures this architecture: **open, not unverified.**

- Open: anyone can publish a manifest. No barriers.
- Verified: anyone can *also* get their manifest attested. Graduated levels. Multiple providers. No gatekeepers.
- Agent choice: the agent decides how much trust it needs based on the task. Not the protocol. Not the trust provider. The agent.

This is not a walled garden. It's the padlock icon. The absence of a padlock doesn't block you from the internet. But its presence tells you something meaningful about where you're going.

## Relationship to OAP

The trust overlay is a **companion protocol**, not a modification to OAP.

- The OAP spec does not change. No trust fields added to the manifest.
- Trust signals are fetched from trust providers, not from the manifest itself.
- A manifest without any trust attestation is still a valid, discoverable, usable OAP manifest.
- Trust is additive, not required.

This separation is load-bearing. The moment trust becomes part of the manifest spec, publishers need to coordinate with trust providers before they can publish. That adds friction. Friction kills adoption. The web didn't require SSL certificates to publish a page. It made them available for those who wanted to signal trust. The same model applies here.

**OAP tells agents what exists. The trust overlay tells agents what to believe.**

---

*This document accompanies the [Open Application Protocol specification](SPEC.md), [reference architecture](ARCHITECTURE.md), [manifesto](MANIFESTO.md), [A2A integration](A2A.md), [robotics](ROBOTICS.md), and [OpenClaw integration](OPENCLAW.md). OAP is released under CC0 1.0 Universal — no rights reserved.*

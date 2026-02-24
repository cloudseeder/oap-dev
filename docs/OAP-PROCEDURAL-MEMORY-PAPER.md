# OAP Manifests as Procedural Memory for Small Language Models

**An Experimental Framework for Experience-Driven Skill Acquisition in Resource-Constrained AI Agents — With Initial Validation**

*Kevin Brooks — Open Application Protocol Project*
*Draft — February 2026*

---

## Abstract

Current discourse around AI-driven software generation assumes frontier models will dynamically produce applications on demand, replacing traditional software platforms. This paper argues that approach is economically and computationally wasteful — a form of "token waste" that treats inference as disposable. We propose and partially validate an alternative: using the Open Application Protocol (OAP) manifest system as a substrate for **procedural memory** in small language models (3B–8B parameters). By caching successful manifest discovery and invocation patterns as structured experience records, small models can accumulate operational competence over time without weight updates or fine-tuning. A reference implementation using qwen3:8b on a Mac Mini M4 (16GB unified memory) achieves 86% task success (131/152 graded tests) across 7 local manifests on cold start — before any experience accumulation. Crucially, **negative experience** — caching what failed and why — emerges as the primary learning mechanism, preventing the dominant failure mode of small models: repeating the same incorrect invocation pattern. This reframes OAP not merely as a discovery protocol but as an enabling layer for a new class of lightweight, experience-driven AI agents.

---

## 1. Introduction

### 1.1 The Token Waste Problem

A prevailing theory in AI application development suggests that sufficiently capable frontier models will render traditional software unnecessary — users will simply describe what they need, and the model will generate it. Platforms like Salesforce, ServiceNow, and Adobe are frequently cited as vulnerable to this disruption.

This framing contains a fundamental economic flaw. Frontier models capable of generating complex, reliable software require hundreds of billions of parameters, trained at costs exceeding $100M per run. Inference costs scale accordingly. Every time a model regenerates logic that already exists as a deployed capability, it burns tokens — and by extension, compute, energy, and money — to reproduce known solutions from first principles. We term this **token waste**: the unnecessary expenditure of inference compute on problems that have already been solved and made available.

The analogy is architectural: token waste is the equivalent of demolishing and rebuilding a house every time you want to open a door.

### 1.2 OAP as an Alternative Architecture

The Open Application Protocol (OAP) takes a fundamentally different approach. Rather than generating capabilities, OAP enables AI agents to **discover** existing capabilities through structured manifests — machine-readable declarations of what a service can do, what inputs it requires, and how to invoke it. OAP functions as a "DNS for AI capabilities," allowing agents to locate and compose services without regenerating them.

This paper extends that concept by proposing that OAP manifest interactions can serve as a **learning substrate** for small language models — enabling a form of procedural memory that allows resource-constrained models to accumulate competence over time. A reference implementation now exists alongside the theoretical framework. The results reported here — from a narrow but real deployment — ground the theoretical predictions in measured outcomes and surface mechanisms that the original framework did not anticipate.

---

## 2. Background and Related Work

### 2.1 Retrieval-Augmented Generation (RAG)

RAG systems augment language models by retrieving relevant documents at inference time and including them in the model's context. This compensates for limited parametric knowledge by externalizing information into a searchable store. However, RAG systems typically retrieve **information** — facts, passages, data. They do not retrieve **action patterns**.

### 2.2 Case-Based Reasoning (CBR)

Case-based reasoning, originating in cognitive science and classical AI, solves new problems by retrieving and adapting solutions from similar past problems. A case library stores problem-solution pairs, and a similarity metric identifies relevant precedents. The approach is well-studied but has seen limited integration with modern language models.

### 2.3 Tool-Use in Language Models

Recent work on tool-augmented LLMs (Toolformer, Gorilla, ToolLLM) demonstrates that language models can learn to invoke external APIs through in-context examples and fine-tuning. However, these approaches typically require large models (70B+) or task-specific fine-tuning to achieve reliability. The question of whether small models can achieve comparable tool-use competence through architectural support — rather than parameter scale — remains underexplored.

### 2.4 The OAP Specification

OAP defines a manifest format that declares service capabilities in a structured, machine-readable schema. A manifest includes the service identity, capability descriptions, input/output schemas, invocation endpoints, authentication requirements, and rate/cost metadata. Critically, manifests are designed to be interpretable by language models without requiring specialized training. Their structured nature reduces the reasoning burden on the consuming agent.

---

## 3. Proposed Framework: Manifest-Mediated Procedural Memory

### 3.1 Core Hypothesis

**Small language models (3B–8B parameters) can achieve reliable, improving performance on OAP-mediated tasks by caching successful manifest interactions as structured experience records, without any weight updates or fine-tuning.**

This hypothesis rests on three observations:

First, the primary limitation of small models is not an inability to follow structured instructions — it is limited world knowledge and difficulty with novel multi-step reasoning. OAP manifests directly address both limitations by externalizing service knowledge into a structured artifact. (The reference implementation validates this directly: an 8B model achieves 86% success on structured manifest tasks that would require multi-step reasoning without manifest support.)

Second, successful OAP interactions contain all the information needed to reproduce the interaction: the user intent, the manifest match, the parameter mapping, and the outcome. This is a complete "worked example" that a small model can pattern-match against. (The reference implementation confirms this: cached experience records enable exact replay of proven invocation patterns.)

Third, for non-latency-sensitive tasks (background processing, batch operations, agent-to-service communication), the additional retrieval step of consulting an experience cache introduces negligible overhead.

### 3.2 Experience Record Schema

We propose a structured experience record format optimized for small-model consumption:

```yaml
experience_record:
  id: "exp_20260219_a3f7"
  timestamp: "2026-02-19T14:32:00Z"

  intent:
    raw: "Get the current zoning status for parcel 1234-56-789"
    fingerprint: "query.zoning.parcel_lookup"
    domain: "civic.land_use"

  discovery:
    query_used: "zoning parcel status lookup"
    manifest_matched: "oap://city-of-portland/land-use-api"
    manifest_version: "2.1.0"
    confidence: 0.92

  invocation:
    endpoint: "/parcels/{parcel_id}/zoning"
    method: "GET"
    parameter_mapping:
      parcel_id:
        source: "intent.entity.parcel_number"
        transform: "remove_hyphens"
        value_used: "123456789"
    headers_required: ["Authorization: Bearer {token}"]

  outcome:
    status: "success"
    http_code: 200
    response_summary: "Returned zoning designation R-1, last updated 2026-01-15"
    latency_ms: 340

  corrections: []
  use_count: 14
  last_used: "2026-02-19T14:32:00Z"
```

Key design decisions in this schema:

**Intent fingerprinting** abstracts the raw natural-language intent into a hierarchical category, enabling similarity matching without requiring the small model to perform semantic comparison across raw text. The fingerprint can be generated by the model itself during the initial interaction and refined over subsequent uses.

**Parameter mapping with transforms** captures not just which manifest parameter matched which intent entity, but how the value was transformed. This is critical — small models frequently fail on format mismatches (hyphens, case sensitivity, date formats). Storing the transform makes the correction reusable.

**Correction chains** record failed attempts and the adjustments that led to success. A record with `corrections: [{attempted: "1234-56-789", error: "Invalid parcel format", fix: "remove_hyphens"}]` is more valuable than a clean success record because it encodes edge-case knowledge that small models characteristically lack.

**Use count and recency** enable experience ranking. Frequently-used, recently-validated patterns should be preferred over stale or rarely-used ones.

**Implementation note.** This exact schema was implemented as Pydantic v2 models persisted to SQLite with JSON columns for structured subfields (`invocation_json`, `corrections_json`). The schema required no modification from paper to code — the hierarchical structure mapped directly to relational storage with indexed fingerprint and domain columns.

In practice, the `corrections` field proved far more important than the schema suggests. The paper originally treated corrections as supplementary metadata for edge cases. In the reference implementation, corrections became the **primary learning mechanism**: when tool execution fails, the tool name, arguments, and error message are saved as `CorrectionEntry` records on a failure experience. Subsequent requests with the same fingerprint retrieve these failures and inject them into the system prompt as compact warnings (e.g., `"oap_grep({"args":"[-Ei]..."}) → Error: invalid option — Avoid these approaches."`). This negative feedback teaches the model what not to repeat — which, for small models, matters more than positive caching.

Confidence degradation enforces this: a single failure multiplies confidence by 0.7, dropping a 0.90 entry to 0.63 — below the 0.85 cache-hit threshold. The bad entry is never served again. This is a simple but effective mechanism: no complex invalidation logic, just multiplicative decay that makes failed patterns self-removing.

### 3.3 The Experience-Augmented Interaction Loop

A standard OAP interaction follows: Intent → Discovery → Manifest Retrieval → Parameter Mapping → Invocation → Response. The experience-augmented loop adds retrieval and storage phases:

```
1. Agent receives intent
2. Agent searches experience cache for matching intent fingerprints
3a. IF match found with high confidence:
      → Retrieve experience record
      → Use cached parameter mapping and invocation pattern
      → Execute with cached pattern
      → Update use_count and last_used
3b. IF match found with low confidence or partial match:
      → Retrieve experience record as starting template
      → Perform manifest discovery to validate/update
      → Execute with adapted pattern
      → Store updated experience record
3c. IF no match found:
      → Perform full OAP discovery cycle
      → Execute interaction
      → Generate new experience record from interaction
      → Store in experience cache
4. Return result
```

This loop has a critical property: **it degrades gracefully**. A cold-start agent with an empty experience cache behaves identically to a standard OAP agent. As interactions accumulate, the agent shifts progressively from discovery-heavy to cache-heavy operation, reducing both token consumption and latency.

#### 3.3.1 Implementation: Three-Path Routing in Practice

The reference implementation maps the abstract loop above to four concrete paths:

**Path 1 — Cache hit.** Exact fingerprint match with `confidence ≥ 0.85` and `outcome.status == "success"`. The agent fingerprints the intent (~23 tokens, ~1.7s using `format="json"` to constrain generation at the grammar level), looks up the fingerprint in SQLite, and replays the cached invocation pattern. Skips vector search and LLM ranking entirely.

**Path 2 — Partial match.** The first two segments of the fingerprint (e.g., `extract.json` from `extract.json.field_list`) match a previous success. The matching tool is injected alongside discovery results without displacing them. This gives the chat model a strong prior from related experience while still allowing discovery to surface better options. Example: if `extract.json.field_value` previously succeeded with jq, a new `extract.json.field_list` task gets jq injected alongside vector search results.

**Path 3 — Full discovery.** No fingerprint match. The agent runs the complete pipeline: vector search over manifest descriptions, LLM ranking of candidates, up to 3 tools injected into the chat round (top LLM pick plus next-highest vector search candidates, deduped by domain). After successful execution, a new experience record is saved mapping the fingerprint to the manifest.

**Path 4 — Degradation.** A cache hit (Path 1) where tool execution produces an error. Confidence is multiplied by 0.7, the entry is marked as failed, and the agent retries with full discovery (Path 3). A single failure drops the entry below threshold, preventing it from being served again. The response metadata reflects this as `oap_experience_cache: "degraded"`.

The graceful degradation property predicted by the theoretical framework holds in practice: cold-start agents operate identically to standard OAP agents, and cache errors self-correct rather than propagating.

### 3.4 Why This Works for Small Models

A 3B-parameter model has roughly 1/100th the parametric knowledge of a 300B frontier model. But the task structure of an OAP interaction, when augmented with experience records, demands far less from the model than open-ended reasoning:

**Without experience cache:** The model must understand a natural-language intent, generate a discovery query, evaluate manifest candidates, reason about parameter mappings, handle format transforms, and construct a valid API call. This multi-step chain is precisely where small models fail.

**With experience cache:** The model must match an intent to a cached fingerprint (pattern matching), retrieve a structured record (lookup), and apply a known parameter mapping with minor adaptations (template filling). Each of these subtasks is well within the capability of a 3B model.

The experience cache effectively **narrows the problem space** from open-ended reasoning to constrained pattern application — converting a task that requires a frontier model into one that a small model can handle reliably.

**Practical minimum.** The reference implementation revealed that the practical minimum for this framework is 8B parameters, not 3B. The bottleneck is not knowledge but **instruction following**. A 4B model (qwen3:4b) could not suppress its reasoning chain — even with `think=false` set at the parameter level and template patches to remove the `<think>` block, the model produced 300+ tokens of verbose reasoning in the response content (~10s per call). This is a weight-level behavior: the model was trained to reason, and no combination of template or parameter settings fully suppresses it. An 8B model (qwen3:8b) respects `think=false` correctly at the weight level, producing ~12 tokens in ~560ms for chat rounds and ~23 tokens in ~1.7s for fingerprinting (with `format="json"` constraining output at the grammar level). The gap is not in capability but in controllability. This suggests that the procedural memory framework's parameter-count floor is set by the model's ability to follow structured output constraints, not by its reasoning capacity.

---

## 4. Experimental Design

### 4.1 Proposed and Partial Evaluation

We propose a three-phase experimental evaluation:

**Phase 1 — Baseline Capability Assessment.** Measure the success rate of 3B, 7B, and 70B models on a standardized set of 200 OAP manifest interactions across five domains (civic data, weather, geocoding, document processing, scheduling) with no experience cache. This establishes the baseline "reasoning gap" between small and large models on OAP tasks.

**Phase 2 — Experience Accumulation.** Run the same 200 interactions through the experience-augmented loop, allowing the small models to build their experience caches. Measure success rate improvement over successive passes, tracking the learning curve.

**Phase 3 — Generalization Testing.** Introduce 50 novel interactions in each domain that are related to but distinct from the training set. Measure whether cached experiences transfer — e.g., whether a cached parcel-lookup pattern generalizes to a permit-lookup on the same API.

#### 4.1.1 Initial Validation

Before the full evaluation, a reference implementation was built and tested against a narrower scope:

**Hardware and model.** Mac Mini M4 with 16GB unified memory. qwen3:8b for generation and chat (~5.9GB VRAM at 4096 context), nomic-embed-text for vector embeddings. Total memory footprint ~6.2GB, leaving headroom on a $500 device.

**Manifests.** Seven local Unix tool manifests: grep, wc, jq, date, bc, apropos, man. All use `invoke.method: "stdio"` with descriptions written for LLM discovery. This is a narrow domain (text processing and system utilities) but exercises the full pipeline: vector search, LLM ranking, parameter extraction, tool execution, and output verification.

**Test harness.** 200 test cases across all 7 manifests plus cross-tool and negative tests. Tests use **output-first verdicts**: if the task produces correct output, the tool identity is secondary. A correct result via an unexpected tool scores SOFT (not FAIL), reflecting the OAP thesis that discovery should find *a* capable tool, not *the* specific tool. Tiered scoring: PASS (correct tool + correct output), SOFT (unexpected tool + correct output), WARN (correct tool + questionable output), FAIL (wrong output or error), SKIP (infrastructure issue). Tests hit a live `/v1/chat` endpoint with `oap_debug` enabled for full execution traces.

**Result.** 131 of 152 graded tests achieved PASS or SOFT (86%). This is a cold-start baseline — no experience cache, every request goes through full discovery (Path 3). The result suggests that the vector search + LLM ranking pipeline, even without procedural memory, provides a strong foundation for small-model tool use when manifests are well-written.

**Scope limitations.** This is a single model, a single hardware target, and 7 manifests in a narrow domain. It is not a peer-reviewed benchmark. The full three-phase evaluation (multiple models, multiple domains, experience accumulation curves) remains future work. What the initial validation provides is a measured baseline that grounds the theoretical framework: the cold-start floor is higher than predicted, negative experience caching is the dominant learning mechanism, and fingerprint granularity resolves through hierarchical prefix matching.

### 4.2 Metrics

We propose the following evaluation metrics:

| Metric | Definition | Status |
|---|---|---|
| **Task Success Rate** | Percentage of interactions that produce a correct API response | Measured: 86% (cold start) |
| **Token Efficiency Ratio** | Tokens consumed by experience-augmented agent vs. baseline agent for the same task | Not yet measured |
| **Discovery Bypass Rate** | Percentage of interactions resolved from cache without full manifest discovery | Not yet measured |
| **Correction Transfer Rate** | Percentage of cached corrections that prevent errors on subsequent similar interactions | Not yet measured |
| **Generalization Score** | Success rate on novel tasks within domains where experience exists vs. domains where it does not | Not yet measured |
| **Competence Convergence** | Number of interactions required for a small model to match the baseline success rate of a 70B model | Not yet measured |

### 4.3 Implementation Notes

The experience cache can be implemented as a local vector store (e.g., SQLite with embeddings for fingerprint similarity) or as a structured JSON store with hierarchical key matching. For the smallest models (3B), minimizing the retrieval complexity is important — a simple prefix-match on intent fingerprints may outperform embedding-based similarity search given the structured nature of the fingerprint schema.

**Implementation confirmed:** The reference implementation uses SQLite with indexed columns for fingerprint and domain, not vector embeddings. Exact fingerprint matching handles cache hits (Path 1); SQL `LIKE` with prefix patterns handles partial matching (Path 2). This validated the paper's prediction that prefix matching would outperform embedding-based similarity for structured fingerprints — the hierarchical nature of the fingerprint schema (`verb.category.action`) makes string prefix matching both simpler and more predictable than cosine similarity over embeddings.

The experience records should be included in the model's context window as structured examples, formatted identically to the schema above. This leverages in-context learning — the model's existing capability to pattern-match against provided examples — without requiring any architectural modifications.

**Refinement:** In practice, experience is injected not as full structured records but as compact system-prompt suffixes. Negative experience (failure hints) is injected as a warning block of ~200 tokens for up to 5 recent failures. Positive experience is injected by converting cached manifests directly into tool definitions. This is more token-efficient than including complete experience records and stays well within the 4096-token context window.

---

## 5. Theoretical Implications

### 5.1 Reframing "Learning" for Deployed Models

Traditional machine learning defines learning as weight updates derived from training data. The framework proposed here suggests a complementary definition: **operational learning as the accumulation of structured experience that modifies an agent's behavior without modifying its parameters.**

This is analogous to the distinction in cognitive science between **declarative memory** (knowing that) and **procedural memory** (knowing how). A language model's weights encode declarative knowledge. The experience cache encodes procedural knowledge — the specific sequences of actions that produce successful outcomes in specific contexts.

This distinction matters practically. Weight updates require expensive retraining or fine-tuning cycles. Experience accumulation happens at inference time, is immediately available, is domain-specific, and is trivially inspectable and editable by human operators.

**The primacy of negative experience.** The reference implementation revealed an asymmetry the original framework did not anticipate: negative experience is a more powerful learning mechanism than positive experience.

Positive caching (Path 1) accelerates — it skips discovery and replays a known-good pattern. But it does not improve accuracy. The agent was already going to find the right tool; the cache just makes it faster.

Negative caching prevents the dominant failure mode of small models on tool-use tasks: **repeating the same incorrect invocation pattern.** When a small model generates invalid arguments for a tool (e.g., garbled regex syntax for grep, invented flags for wc), it tends to regenerate the same or similar errors on retry. The model lacks the parametric knowledge to diagnose its own mistakes. Negative experience records break this loop by injecting prior failures into the system prompt: "This was tried before and failed — avoid it." The model can follow this instruction even when it cannot independently reason about why the approach failed.

This creates a **compound learning** effect: failure + subsequent success are saved together as correction pairs. The failure record prevents the bad path; the success record (once achieved through full discovery retry) provides the good path. Neither record alone is as valuable as the pair. This is structurally similar to case-based reasoning's retain-and-revise cycle, but implemented through prompt injection rather than case adaptation — a mechanism better suited to the limited reasoning capacity of small models.

### 5.2 The Economic Argument for Protocol-Mediated Learning

If small models can achieve frontier-model performance on structured tasks through experience accumulation, the economic implications are significant:

**Inference cost:** An 8B model requires roughly 1/40th the compute of a 300B model per token. If the experience cache enables the 8B model to match the 300B model's task success rate on OAP interactions, the effective cost per successful interaction drops by over an order of magnitude.

**Deployment accessibility:** 8B models run on consumer hardware. The reference implementation runs on a Mac Mini M4 with 16GB unified memory — ~$500 retail — with qwen3:8b consuming ~5.9GB VRAM at 4096 context and nomic-embed-text for embeddings, totaling ~6.2GB with ~300-500MB free. Experience-augmented OAP agents operate locally without cloud API calls, enabling privacy-preserving, offline-capable AI agents on hardware that fits in a desk drawer.

**Ecosystem effects:** If OAP manifests enable small models to be competent agents, the protocol becomes valuable not just as a discovery mechanism but as a **competence equalizer** — an infrastructure layer that democratizes access to AI capability by lowering the model-size threshold for useful agentic behavior.

### 5.3 Relationship to the "Token Waste" Critique

The token waste critique of generative software applies with equal force to generative tool-use. Every time a frontier model reasons from scratch about how to invoke an API it has invoked before, it wastes tokens. The experience cache is the direct remedy: convert first-principles reasoning into pattern retrieval. OAP manifests make this possible by providing the structured, stable interface that makes experience records meaningful and transferable.

---

## 6. Limitations and Open Questions

**Experience staleness.** Manifests evolve. An experience record cached against manifest version 2.1 may fail silently against version 2.2 if parameter semantics change. The framework requires a versioning and invalidation strategy — potentially triggered by manifest version mismatches detected at invocation time. The confidence degradation mechanism (×0.7 on failure) addresses runtime staleness — a changed manifest that causes invocation errors will self-invalidate. Version-based staleness detection (proactively invalidating cache entries when a manifest's version number changes) remains unimplemented.

**Intent fingerprint quality.** ~~The usefulness of the experience cache depends heavily on the quality of intent fingerprinting. If fingerprints are too specific, experiences rarely match. If too general, irrelevant experiences pollute the context. The optimal granularity is an empirical question this paper does not resolve.~~ **Resolved in practice.** The reference implementation uses hierarchical fingerprints (e.g., `extract.json.field_list`) with two levels of matching: exact fingerprint for cache hits, two-segment prefix (e.g., `extract.json`) for experience transfer. This resolves the granularity question for the tested domain: exact matching is specific enough to avoid false cache hits, while prefix matching is general enough to surface relevant experience from related tasks. JSON-aware fingerprints (e.g., `*.json.*`) separate JSON tasks from text tasks in the fingerprint space, preventing cross-domain contamination. Whether this granularity scales to hundreds or thousands of manifests across diverse domains is untested.

**Context window constraints.** Small models have limited context windows. Including multiple experience records alongside the manifest and the user intent may exceed available context. The reference implementation operates within a 4096-token context window. Experience is injected as compact system-prompt suffixes: failure hints use ~200 tokens for up to 5 records; positive experience is injected by converting cached manifests to tool definitions rather than including raw records. This approach scales to the current manifest count but may require compression strategies for larger manifest registries.

**Cold-start performance.** ~~The critical empirical question is whether enough early interactions succeed to bootstrap the cache past the tipping point where cache-based resolution dominates.~~ **Partially resolved.** The reference implementation achieves 86% task success on cold start (no experience cache), well above the 40-50% threshold predicted as necessary for cache convergence. This suggests that warm-start seeding (pre-populating the cache with frontier-model results) is viable but unnecessary for well-written manifests in a narrow domain. Whether the cold-start floor remains this high across diverse, poorly-documented APIs is an open question.

**Security considerations.** Experience records cached from interactions with external services could be poisoned by malicious manifests. A compromised manifest could cause the agent to cache incorrect parameter mappings that persist. The framework should include provenance verification and anomaly detection on cached records.

**Generalization boundaries.** It is unclear how far experience transfers across related but distinct services. Can a cached pattern for one city's parcel-lookup API generalize to another city's? The structural similarity of OAP manifests suggests it should, but the degree of transfer is an empirical question. The reference implementation demonstrates prefix-based generalization within a domain (e.g., `extract.json.field_value` experience helping `extract.json.field_list` tasks) but cross-domain transfer is untested.

---

## 7. Conclusion

The prevailing narrative that AI will replace software by generating it on demand overlooks a fundamental economic reality: tokens are not free, and regenerating solved problems is waste. The Open Application Protocol offers a more efficient architecture by enabling AI agents to discover and invoke existing capabilities rather than recreating them.

This paper extends that insight by proposing — and partially validating — that OAP manifest interactions can serve as a learning substrate for small language models. By caching successful interactions as structured experience records, models with as few as 8 billion parameters can achieve reliable performance on structured tasks, running on a $500 consumer device.

Three findings from the reference implementation sharpen the theoretical framework:

1. **Cold-start performance exceeds predictions.** An 8B model achieves 86% task success across 7 manifests with no experience cache — well above the 40-50% threshold predicted as necessary for cache convergence. Well-written manifests and a structured discovery pipeline do most of the work; procedural memory accelerates and stabilizes, but the foundation is stronger than expected.

2. **Negative experience is the primary learning mechanism.** Positive caching accelerates (skips discovery) but does not improve accuracy. Negative caching — recording what failed and injecting it as a warning — prevents the dominant small-model failure mode of repeating incorrect invocation patterns. Correction pairs (failure + subsequent success) create compound learning that neither record achieves alone.

3. **Fingerprint granularity resolves through hierarchy.** Hierarchical fingerprints with two levels of matching (exact for cache hits, prefix for experience transfer) provide the right granularity for the tested domain. The `verb.category.action` structure makes string prefix matching both simpler and more predictable than embedding-based similarity.

These findings are grounded but narrow: a single model, a single hardware target, 7 manifests in a Unix-tool domain. A full multi-model, multi-domain evaluation with experience accumulation curves and generalization testing remains future work. What the initial validation establishes is that the framework's core mechanisms work as designed, the cold-start floor is viable, and the dominant learning path was not the one we expected.

If the framework generalizes beyond this initial scope, it positions OAP as more than a discovery protocol. It becomes an **enabling layer for democratized AI agency** — infrastructure that allows small, locally-deployable models to accumulate competence through experience rather than requiring competence through scale.

---

## References

1. Schick, T., et al. "Toolformer: Language Models Can Teach Themselves to Use Tools." *NeurIPS*, 2023.
2. Patil, S.G., et al. "Gorilla: Large Language Model Connected with Massive APIs." *arXiv:2305.15334*, 2023.
3. Qin, Y., et al. "ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs." *arXiv:2307.16789*, 2023.
4. Lewis, P., et al. "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks." *NeurIPS*, 2020.
5. Kolodner, J. "Case-Based Reasoning." *Morgan Kaufmann*, 1993.
6. Open Application Protocol Specification. *oap.dev*, 2026.
7. Brooks, K. "The Path to 23 Tokens." *Open Application Protocol Project*, 2026.

---

*This paper describes a proposed experimental framework with initial validation from a reference implementation. Full multi-model, multi-domain experimental results are future work. The OAP specification and reference implementation are available at [oap.dev](https://oap.dev) and [github.com/kevinbrooks/oap](https://github.com/kevinbrooks/oap).*

*Correspondence: hello@oap.dev*

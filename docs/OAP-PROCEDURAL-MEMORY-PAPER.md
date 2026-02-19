# OAP Manifests as Procedural Memory for Small Language Models

**An Experimental Framework for Experience-Driven Skill Acquisition in Resource-Constrained AI Agents**

*Kevin Brooks — Open Application Protocol Project*
*Draft — February 2026*

---

## Abstract

Current discourse around AI-driven software generation assumes frontier models will dynamically produce applications on demand, replacing traditional software platforms. This paper argues that approach is economically and computationally wasteful — a form of "token waste" that treats inference as disposable. We propose an alternative: using the Open Application Protocol (OAP) manifest system as a substrate for **procedural memory** in small language models (3B–7B parameters). By caching successful manifest discovery and invocation patterns as structured experience records, small models can accumulate operational competence over time without weight updates or fine-tuning. This reframes OAP not merely as a discovery protocol but as an enabling layer for a new class of lightweight, experience-driven AI agents.

---

## 1. Introduction

### 1.1 The Token Waste Problem

A prevailing theory in AI application development suggests that sufficiently capable frontier models will render traditional software unnecessary — users will simply describe what they need, and the model will generate it. Platforms like Salesforce, ServiceNow, and Adobe are frequently cited as vulnerable to this disruption.

This framing contains a fundamental economic flaw. Frontier models capable of generating complex, reliable software require hundreds of billions of parameters, trained at costs exceeding $100M per run. Inference costs scale accordingly. Every time a model regenerates logic that already exists as a deployed capability, it burns tokens — and by extension, compute, energy, and money — to reproduce known solutions from first principles. We term this **token waste**: the unnecessary expenditure of inference compute on problems that have already been solved and made available.

The analogy is architectural: token waste is the equivalent of demolishing and rebuilding a house every time you want to open a door.

### 1.2 OAP as an Alternative Architecture

The Open Application Protocol (OAP) takes a fundamentally different approach. Rather than generating capabilities, OAP enables AI agents to **discover** existing capabilities through structured manifests — machine-readable declarations of what a service can do, what inputs it requires, and how to invoke it. OAP functions as a "DNS for AI capabilities," allowing agents to locate and compose services without regenerating them.

This paper extends that concept by proposing that OAP manifest interactions can serve as a **learning substrate** for small language models — enabling a form of procedural memory that allows resource-constrained models to accumulate competence over time.

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

**Small language models (3B–7B parameters) can achieve reliable, improving performance on OAP-mediated tasks by caching successful manifest interactions as structured experience records, without any weight updates or fine-tuning.**

This hypothesis rests on three observations:

First, the primary limitation of small models is not an inability to follow structured instructions — it is limited world knowledge and difficulty with novel multi-step reasoning. OAP manifests directly address both limitations by externalizing service knowledge into a structured artifact.

Second, successful OAP interactions contain all the information needed to reproduce the interaction: the user intent, the manifest match, the parameter mapping, and the outcome. This is a complete "worked example" that a small model can pattern-match against.

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

### 3.4 Why This Works for Small Models

A 3B-parameter model has roughly 1/100th the parametric knowledge of a 300B frontier model. But the task structure of an OAP interaction, when augmented with experience records, demands far less from the model than open-ended reasoning:

**Without experience cache:** The model must understand a natural-language intent, generate a discovery query, evaluate manifest candidates, reason about parameter mappings, handle format transforms, and construct a valid API call. This multi-step chain is precisely where small models fail.

**With experience cache:** The model must match an intent to a cached fingerprint (pattern matching), retrieve a structured record (lookup), and apply a known parameter mapping with minor adaptations (template filling). Each of these subtasks is well within the capability of a 3B model.

The experience cache effectively **narrows the problem space** from open-ended reasoning to constrained pattern application — converting a task that requires a frontier model into one that a small model can handle reliably.

---

## 4. Experimental Design

### 4.1 Proposed Evaluation

We propose a three-phase experimental evaluation:

**Phase 1 — Baseline Capability Assessment.** Measure the success rate of 3B, 7B, and 70B models on a standardized set of 200 OAP manifest interactions across five domains (civic data, weather, geocoding, document processing, scheduling) with no experience cache. This establishes the baseline "reasoning gap" between small and large models on OAP tasks.

**Phase 2 — Experience Accumulation.** Run the same 200 interactions through the experience-augmented loop, allowing the small models to build their experience caches. Measure success rate improvement over successive passes, tracking the learning curve.

**Phase 3 — Generalization Testing.** Introduce 50 novel interactions in each domain that are related to but distinct from the training set. Measure whether cached experiences transfer — e.g., whether a cached parcel-lookup pattern generalizes to a permit-lookup on the same API.

### 4.2 Metrics

We propose the following evaluation metrics:

| Metric | Definition |
|---|---|
| **Task Success Rate** | Percentage of interactions that produce a correct API response |
| **Token Efficiency Ratio** | Tokens consumed by experience-augmented agent vs. baseline agent for the same task |
| **Discovery Bypass Rate** | Percentage of interactions resolved from cache without full manifest discovery |
| **Correction Transfer Rate** | Percentage of cached corrections that prevent errors on subsequent similar interactions |
| **Generalization Score** | Success rate on novel tasks within domains where experience exists vs. domains where it does not |
| **Competence Convergence** | Number of interactions required for a small model to match the baseline success rate of a 70B model |

### 4.3 Implementation Notes

The experience cache can be implemented as a local vector store (e.g., SQLite with embeddings for fingerprint similarity) or as a structured JSON store with hierarchical key matching. For the smallest models (3B), minimizing the retrieval complexity is important — a simple prefix-match on intent fingerprints may outperform embedding-based similarity search given the structured nature of the fingerprint schema.

The experience records should be included in the model's context window as structured examples, formatted identically to the schema above. This leverages in-context learning — the model's existing capability to pattern-match against provided examples — without requiring any architectural modifications.

---

## 5. Theoretical Implications

### 5.1 Reframing "Learning" for Deployed Models

Traditional machine learning defines learning as weight updates derived from training data. The framework proposed here suggests a complementary definition: **operational learning as the accumulation of structured experience that modifies an agent's behavior without modifying its parameters.**

This is analogous to the distinction in cognitive science between **declarative memory** (knowing that) and **procedural memory** (knowing how). A language model's weights encode declarative knowledge. The experience cache encodes procedural knowledge — the specific sequences of actions that produce successful outcomes in specific contexts.

This distinction matters practically. Weight updates require expensive retraining or fine-tuning cycles. Experience accumulation happens at inference time, is immediately available, is domain-specific, and is trivially inspectable and editable by human operators.

### 5.2 The Economic Argument for Protocol-Mediated Learning

If small models can achieve frontier-model performance on structured tasks through experience accumulation, the economic implications are significant:

**Inference cost:** A 3B model requires roughly 1/100th the compute of a 300B model per token. If the experience cache enables the 3B model to match the 300B model's task success rate on OAP interactions, the effective cost per successful interaction drops by two orders of magnitude.

**Deployment accessibility:** 3B models run on consumer hardware — laptops, phones, edge devices. Experience-augmented OAP agents could operate locally without cloud API calls, enabling privacy-preserving, offline-capable AI agents.

**Ecosystem effects:** If OAP manifests enable small models to be competent agents, the protocol becomes valuable not just as a discovery mechanism but as a **competence equalizer** — an infrastructure layer that democratizes access to AI capability by lowering the model-size threshold for useful agentic behavior.

### 5.3 Relationship to the "Token Waste" Critique

The token waste critique of generative software applies with equal force to generative tool-use. Every time a frontier model reasons from scratch about how to invoke an API it has invoked before, it wastes tokens. The experience cache is the direct remedy: convert first-principles reasoning into pattern retrieval. OAP manifests make this possible by providing the structured, stable interface that makes experience records meaningful and transferable.

---

## 6. Limitations and Open Questions

**Experience staleness.** Manifests evolve. An experience record cached against manifest version 2.1 may fail silently against version 2.2 if parameter semantics change. The framework requires a versioning and invalidation strategy — potentially triggered by manifest version mismatches detected at invocation time.

**Intent fingerprint quality.** The usefulness of the experience cache depends heavily on the quality of intent fingerprinting. If fingerprints are too specific, experiences rarely match. If too general, irrelevant experiences pollute the context. The optimal granularity is an empirical question this paper does not resolve.

**Context window constraints.** Small models have limited context windows. Including multiple experience records alongside the manifest and the user intent may exceed available context. Experience selection and compression strategies — such as including only the most relevant record rather than all candidates — require further investigation.

**Security considerations.** Experience records cached from interactions with external services could be poisoned by malicious manifests. A compromised manifest could cause the agent to cache incorrect parameter mappings that persist. The framework should include provenance verification and anomaly detection on cached records.

**Generalization boundaries.** It is unclear how far experience transfers across related but distinct services. Can a cached pattern for one city's parcel-lookup API generalize to another city's? The structural similarity of OAP manifests suggests it should, but the degree of transfer is an empirical question.

---

## 7. Conclusion

The prevailing narrative that AI will replace software by generating it on demand overlooks a fundamental economic reality: tokens are not free, and regenerating solved problems is waste. The Open Application Protocol offers a more efficient architecture by enabling AI agents to discover and invoke existing capabilities rather than recreating them.

This paper extends that insight by proposing that OAP manifest interactions can serve as a learning substrate for small language models. By caching successful interactions as structured experience records, models with as few as 3 billion parameters may achieve reliable performance on structured, non-latency-sensitive tasks — performance that would otherwise require models 100x their size.

If validated experimentally, this framework positions OAP as more than a discovery protocol. It becomes an **enabling layer for democratized AI agency** — infrastructure that allows small, cheap, locally-deployable models to accumulate competence through experience rather than requiring competence through scale.

The implications extend beyond efficiency. In a world where AI capability is gated by model size, only organizations that can afford frontier-model inference participate. In a world where structured protocols enable small models to learn from experience, the barrier to capable AI agency drops to the cost of a consumer device and an internet connection.

---

## References

1. Schick, T., et al. "Toolformer: Language Models Can Teach Themselves to Use Tools." *NeurIPS*, 2023.
2. Patil, S.G., et al. "Gorilla: Large Language Model Connected with Massive APIs." *arXiv:2305.15334*, 2023.
3. Qin, Y., et al. "ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs." *arXiv:2307.16789*, 2023.
4. Lewis, P., et al. "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks." *NeurIPS*, 2020.
5. Kolodner, J. "Case-Based Reasoning." *Morgan Kaufmann*, 1993.
6. Open Application Protocol Specification. *oap.dev*, 2026.

---

*This paper describes a proposed experimental framework. Experimental results are forthcoming. The OAP specification is available at [oap.dev](https://oap.dev).*

*Correspondence: hello@oap.dev*

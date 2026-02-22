# The Path to 23 Tokens

*How to make a small LLM stop thinking*

---

OAP's experience cache needs intent fingerprinting — a fast classification of what the user wants so we can skip expensive vector search and LLM ranking when we've seen a similar task before. The fingerprint model is qwen3:4b, a 4-billion parameter reasoning model running locally on a $500 Mac Mini. We need it to emit ~20 tokens of JSON. It insists on emitting ~3,600 tokens of step-by-step reasoning.

This is the story of five approaches to making it stop, what failed, why, and the one-line fix that took 12 hours to find.

## The numbers

| # | Approach | Tokens out | Latency | Result |
|---|----------|-----------|---------|--------|
| 1 | `think=false` on `/api/generate` | 3,674 | ~112s | No effect |
| 2 | Switch to `/api/chat` | 319 | ~10s | Reduced but still thinking |
| 3 | Patch the model template | 1,217 | ~30s | Model generates `<think>` from weights |
| 4 | Empty `<think></think>` trick | ~1,200 | ~30s | Model ignores it, reasons in content |
| 5 | `format="json"` | **23** | **1.7s** | Constrained decoding wins |

## Act 1: think=false

Ollama's documentation says the `think` parameter controls whether reasoning models emit their chain-of-thought. Set `think: false`, get concise output. Simple.

```bash
curl -s http://localhost:11434/api/generate -d '{
  "model": "qwen3:4b",
  "prompt": "classify this task as JSON",
  "think": false,
  "stream": false
}'
```

3,674 tokens. ~112 seconds. The model reasons through every possible interpretation, considers edge cases, debates with itself, then finally emits the JSON we wanted — buried in paragraphs of explanation.

`think=false` on `/api/generate` does nothing. The parameter exists but the generate endpoint doesn't apply it the way you'd expect. The thinking pours into the `response` field regardless.

## Act 2: /api/chat

The `/api/chat` endpoint handles the chat template — the structured format that tells the model where system prompts, user messages, and assistant responses begin and end. Maybe the think parameter works here because the template can actually interpret it.

```bash
curl -s http://localhost:11434/api/chat -d '{
  "model": "qwen3:4b",
  "messages": [{"role":"user","content":"classify this task"}],
  "think": false,
  "stream": false
}'
```

319 tokens. ~10 seconds. Progress — but still 10x more than we need. The model is still reasoning, just less verbosely. The thinking is leaking into the `content` field instead of the `thinking` field.

## Act 3: The template

Time to look under the hood. Every Ollama model has a Go template that formats the conversation into the token sequence the model expects. Here's the relevant part of the stock qwen3:4b template:

```
{{- if (and $.IsThinkSet ...) -}}
<think>{{ .Thinking }}</think>
{{ end }}
```

The problem: the template's final block unconditionally injects `<think>` at the start of every assistant response. When the model sees `<think>` as the first token of its response, it does what it was trained to do — think.

`think=false` is a no-op because the template always starts the response with a think block.

The fix seemed obvious: make the `<think>` injection conditional.

```bash
ollama create qwen3t:4b  # patched copy
```

New template:

```
{{ if or (not $.IsThinkSet) $.Think }}<think>{{ end }}
```

Now `think=false` actually suppresses the `<think>` tag. The model should stop thinking. Right?

1,217 tokens. ~30 seconds. Better than the stock template, but the model is still reasoning. Without the `<think>` tag to open a thinking block, it just... reasons directly in the content. Step-by-step analysis, consideration of alternatives, then the JSON.

Thinking isn't a feature of the template. It's baked into the weights. Alibaba spent millions training qwen3 to reason through problems step by step. No template change can undo that.

## Act 4: The empty think block trick

What if we trick the model into thinking it already finished thinking? Inject an empty `<think></think>` block at the start of the response — a closed thinking section with nothing in it. The model should see "thinking is done" and move on to the answer.

The model ignores it. It reasons in the content field anyway, because reasoning is what it does. The empty tags are just tokens — the model's weights don't treat them as a state machine. There's no "thinking mode" switch to flip.

## Act 5: format=json

```python
raw, _ = await self._ollama.chat(
    task, system=FINGERPRINT_SYSTEM, timeout=120,
    think=False, temperature=0, format="json",
)
```

23 tokens. 1.7 seconds.

```
oap.ollama INFO ollama chat model=qwen3t:4b tokens_in=405 tokens_out=23 ms=1787
oap.tool_api INFO Experience cache hit: compute.math.calculation → local/bc
```

One parameter. The entire debugging session — template patches, API endpoint switches, prompt engineering, empty tag tricks — resolved by `format="json"`.

## Why format=json works

Every approach before this tried to change what the model *wants* to do. They all failed because the model wants to reason — it's trained to reason, the weights encode reasoning, and no amount of parameter tweaking or template patching can override that.

`format="json"` works at a completely different level. It uses **constrained decoding** — a grammar mask applied to the token logits at each generation step. At every point where the model is about to select the next token, Ollama checks which tokens would produce valid JSON and zeros out everything else.

The model still "wants" to reason. Its internal activations still fire the same way. But the only tokens it can emit are ones that form valid JSON. It can't write "Let me think about this step by step" because that's not valid JSON. It can't write `<think>` because angle brackets aren't valid JSON tokens.

It's like guardrails on a highway. The engine is the same, but the car can only go where the road allows.

The model produces exactly what we need:

```json
{"domain": "compute.math.calculation", "operation": "arithmetic"}
```

No reasoning. No preamble. No debate. Just the JSON.

## The lesson

We spent 12 hours anchored on the wrong problem. Every fix was a variation of "how do I make the model stop thinking?" — suppress the think parameter, fix the template, trick it with empty tags. All of these try to change what the model wants to do.

The right question was: "how do I enforce the output format I already need?"

**When a model won't follow an instruction, don't keep trying to convince it — constrain the output space.**

This is a general principle. Prompt engineering tries to steer model behavior through persuasion. Constrained decoding enforces it through structure. When the two conflict, structure wins. Always.

There's an irony here: Alibaba spent millions deliberately training qwen3:4b to think step-by-step through reasoning chains. We spent 12 hours trying to make it stop. `format=json` doesn't undo the training — the model is still thinking internally as it selects each token. We're just not letting it write it down.

## What we were building

OAP's experience cache gives a small LLM procedural memory — the ability to remember what worked before. When a user asks "count the words in this file," the system fingerprints that intent and checks if it's seen something similar. If it has, it skips the full discovery pipeline (vector search + LLM ranking) and goes straight to the cached tool.

The fingerprint needs to be fast — it's the gate that decides whether to use the cache or do full discovery. At 112 seconds, the fingerprint took longer than the discovery it was supposed to skip. At 1.7 seconds, it's a genuine fast path.

A 4-billion parameter model on a $500 Mac Mini discovering tools it's never seen, executing them, summarizing the output, and synthesizing a coherent answer — all through a protocol that didn't exist in its training data. The fingerprint is one small piece, but getting it right meant the difference between a demo and something you'd actually use.

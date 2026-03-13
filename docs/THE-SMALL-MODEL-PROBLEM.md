# The Small Model Problem

_When your 9B-parameter assistant decides to read every meeting transcript instead of checking the news._

## The Promise

Run everything locally. No API keys, no cloud bills, no privacy concerns. A Mac Mini with 16GB of RAM, an 8B model, and a manifest spec that lets AI discover capabilities at runtime. The whole stack fits on your desk.

It works. Most of the time.

## What Happened

We switched from `qwen3:8b` to `qwen3.5:9b` — a newer, "better" model. Same hardware, same manifests, same code. Here's what broke.

### The News Task

A cron task runs every hour: _"Get the current civic, business, transit and restaurant news from Portland Oregon."_

The manifest for the news service (mynewscast.org) has five intents:

| Intent | Purpose |
|--------|---------|
| `stories` | AI-generated news articles |
| `events` | Government meeting schedules |
| `inspections` | Restaurant health data |
| `search` | Full-text search of raw meeting transcripts (RAG) |
| `trending` | Top civic topics |

**qwen3:8b** called `stories`, got zero results (no new articles that day), and said: _"No new stories for Portland. Try checking back shortly."_ One tool call. Done.

**qwen3.5:9b** called `stories`, got zero results, then called `search` with a broad query, got 102,000 characters of raw TriMet board meeting transcripts (speech-to-text with "um" and "uh"), then called `events` and got more raw transcripts. Three tool calls. The output was gibberish.

The 3.5 model wasn't wrong to try harder — it was _too helpful_. It saw empty results and went looking for _something_ to return, falling into the `search` intent which returns raw transcript chunks, not news articles.

### The Fix

We updated the manifest descriptions. Before:

```
"stories" for AI-generated news
"search" for transcript full-text search via RAG
```

After:

```
"stories" for current news articles and summaries — use this for general news queries
"search" for full-text search of raw meeting transcripts
  (returns unprocessed speech-to-text excerpts, not news articles —
   only use when looking for specific quotes or discussion topics)
```

One description change. No code. The model stopped reaching for `search` on news queries.

**Lesson: Manifests are the steering wheel.** When a model misbehaves with a tool, the first fix is always the manifest description — not code, not prompts, not retry logic.

### The Email Check

A task checks for personal email: _"Tell me if Amy, Keric or Kai sent me an email."_

**qwen3:8b** called the email API, got results, summarized them.

**qwen3.5:9b** sometimes summarized, sometimes dumped raw JSON: `{"messages":[{"id":"INBOX_235879","message_id":"DFDC1C42-8799-...`

The model was non-deterministic about whether to summarize tool results or pass them through. The notification system dutifully stored the raw JSON as the notification body. The morning briefing read it aloud.

### The Follow-Up Bug

User asks: _"What day is it?"_ Then: _"Do I have any email from real people from today?"_

The tool bridge has follow-up detection — if the second message looks like a continuation ("do it", "yes please", "correct that"), it prepends the first message for context. The regex matched "**Do** I have any email..." because `do` was in the pattern.

Two unrelated questions got combined into one discovery query. The fingerprint engine classified it as `query.system.date_time`, which cache-hit to `builtin/exec`. The model saw a complex multi-part question, refused to call any tools, and the force-invoke fallback picked `newsapi_everything` and `sunrise-sunset` — neither of which had anything to do with email.

The model eventually gave up and responded: _"I'm afraid I don't have a way to actually read your email inbox right now."_

It does. It did it five minutes ago.

## The Compensating Logic

The OAP tool bridge is ~1,700 lines of orchestration code. Here's what it does and why:

| Feature | Why It Exists |
|---------|--------------|
| **Experience cache** | Small models re-discover the same tools every time. Cache the mapping so "check my email" → `oap-email` is instant after the first success. |
| **Force-invoke** | When the model refuses to call tools despite having them available, extract arguments via a separate LLM call and invoke directly. |
| **Retry with re-discovery** | Cache hit but wrong tool? Degrade confidence and try fresh discovery. |
| **Stdio suppression** | Small models prefer "named" tools (like `oap_date`) over generic `oap_exec`, but produce worse results with them. Suppress stdio tools and only offer `oap_exec`. |
| **Follow-up expansion** | Short messages like "do it" have no context for discovery. Prepend the previous message so fingerprinting works. |
| **Big LLM escalation** | When tool results are too large for the small model's context window, send to Claude or GPT for the final summary. |
| **Duplicate detection** | Same task, same result, different phrasing. MD5 the normalized output to skip redundant notifications. |
| **No-news filtering** | "No new emails found" isn't worth a notification. Regex-match common "nothing happened" phrases. |
| **Raw JSON detection** | Model dumped tool output without summarizing? Skip the notification. |
| **Conditional thinking** | Some tasks need `think: true` for the model to reason about tool output. Others get worse with thinking enabled. Per-fingerprint toggle. |

Every line was earned. Every feature exists because a specific failure happened in production. Remove any of them and the failure comes back — maybe not with this model, but with the next one.

## The Fragility

Switch models and you get _different_ failure modes:

- **qwen3:8b** — reliable tool caller, accepts empty results gracefully, but weaker at complex reasoning
- **qwen3:14b** — better reasoning, but skips `stories` intent entirely, goes straight to `events` and `inspections`
- **qwen3.5:9b** — best overall, but fires parallel tool calls aggressively, falls back to `search` on empty results, sometimes refuses to call tools at all, and requires thinking enabled for tool calls (making everything 2-3x slower)

The compensating logic helps all three models, but each model needs it for different reasons. There's no configuration that's optimal for all of them.

## The Cost

All of this runs on a Mac Mini M4 with 16GB RAM. The 9B model uses ~6GB VRAM at 4K context. That leaves room for the embedding model (nomic-embed-text) but not much else. Loading a second model means swapping. Swapping means latency. Latency means timeouts. Timeouts mean the force-invoke cascade. The cascade means wrong tools. Wrong tools mean bad results.

The whole chain from "not enough RAM" to "your morning briefing is TriMet board meeting transcripts" is about four hops.

## What Would Help

1. **Better small models.** This is the real fix. As 8-14B models improve at structured tool calling, the compensating logic can be _removed_, not added. The gap between qwen3 and qwen3.5 was mixed — better at some things, worse at others. The next generation might be the one where force-invoke becomes unnecessary.

2. **Better manifest descriptions.** This is the fix that's available today. The mynewscast manifest change — three sentences of description — completely changed model behavior. Manifests are the interface between human intent and model behavior. Writing them well matters more than any amount of retry logic.

3. **Acceptance.** Small local models are unreliable tool callers. The compensating logic isn't technical debt — it's the cost of running locally. The alternative is cloud APIs with their own fragility (cost, latency, privacy, availability). Pick your trade-off.

## The Bet

OAP bets that manifests — simple JSON files describing what a capability does — are the right abstraction layer between AI and tools. The spec doesn't care what model reads it. The manifest for mynewscast.org works the same whether it's qwen3:8b, Claude, or whatever ships next year.

The fragility isn't in the spec. It's in the gap between what small models _can_ do and what we _need_ them to do. That gap is closing. Every model generation closes it a little more.

In the meantime, we ship 1,700 lines of compensating logic and fix manifests one description at a time.

---

_Written March 13, 2026. Based on real failures from switching qwen3:8b to qwen3.5:9b on a Mac Mini M4 running the full OAP stack._

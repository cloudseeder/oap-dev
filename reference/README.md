# OAP Reference Discovery Stack

A working implementation of the [OAP architecture](../docs/ARCHITECTURE.md): crawl manifests, index as vectors, query with natural language, match intent to capability.

Runs on a laptop. No cloud. No API keys for discovery.

## Stack

| Component | Role |
|-----------|------|
| **ChromaDB** (embedded) | Vector storage — cosine similarity search over manifest descriptions |
| **Ollama** (local) | `nomic-embed-text` for embeddings, `qwen3:4b` for manifest reasoning |
| **FastAPI** | Discovery API |
| **Click** | CLI |

## Quick Start

### 1. Install Ollama and pull models

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull nomic-embed-text
ollama pull qwen3:4b
```

### 2. Install the package

```bash
cd reference
pip install -e ".[dev]"
```

### 3. Index the seed manifests

```bash
oap-crawl --seed
```

This loads the 4 example manifests from `seeds/` (grep, jq, summarizer, mynewscast) into ChromaDB. Works without Ollama running — uses dummy embeddings.

For real embeddings (requires Ollama running):

```bash
# Not yet implemented — seed mode currently uses dummy embeddings when Ollama is unavailable
```

### 4. Start the API

```bash
oap-api
```

Runs on `http://localhost:8300` by default.

### 5. Discover capabilities

```bash
oap discover "search text files for a regex pattern"
# → grep

oap discover "transcribe a government meeting"
# → myNewscast Meeting Processor

oap discover "transform JSON data" --json
# → raw JSON response

oap status
# → API health, Ollama status, index count

oap list-manifests
# → all indexed manifests
```

## Configuration

Edit `config.yaml` or use environment variables:

```bash
export OAP_OLLAMA_BASE_URL=http://remote-host:11434
export OAP_API_PORT=9000
export OAP_CHROMADB_PATH=/tmp/oap_data
```

## Crawling Remote Domains

Add domains to `seeds.txt` (one per line), then:

```bash
# Crawl once
oap-crawl --once

# Continuous crawl (default: every hour)
oap-crawl
```

The crawler fetches `https://<domain>/.well-known/oap.json` for each domain, validates the manifest, embeds the description, and stores it in ChromaDB.

## Tests

```bash
pytest
```

Tests mock Ollama and ChromaDB — no external services needed.

## Architecture

```
Task ("search for regex")
  │
  ├─ 1. Embed task → nomic-embed-text (Ollama)
  │
  ├─ 2. Vector search → ChromaDB (cosine similarity)
  │     Returns top-k candidate manifests
  │
  ├─ 3. LLM reasoning → qwen3:4b (Ollama)
  │     Picks best match from candidates, explains why
  │
  └─ Result: manifest + reasoning
```

See [ARCHITECTURE.md](../docs/ARCHITECTURE.md) for the full design.

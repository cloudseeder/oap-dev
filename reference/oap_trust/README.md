# OAP Reference Trust Provider

Reference implementation of the [OAP Trust Overlay](../../docs/TRUST.md) — domain and capability attestation for OAP manifests. Same philosophy as the [discovery reference stack](../oap_discovery/): don't prescribe, prove.

Implements Layers 0–2 of the trust overlay. Layer 3 (compliance certification) requires human auditors and is out of scope for a reference implementation.

## How it works

```
Publisher: POST /v1/attest/domain {"domain": "example.com"}
    → Trust provider fetches /.well-known/oap.json (Layer 0 checks)
    → Returns challenge: "Add TXT record: _oap-verify.example.com oap-challenge={token}"

Publisher adds DNS TXT record, then:
    GET /v1/attest/domain/example.com/status
    → Trust provider queries DNS, finds token
    → Signs JWS attestation (Ed25519)
    → Stores and returns attestation

Agent later:
    GET /v1/attestations/example.com
    → Returns signed attestation(s)
    → Agent verifies signature using GET /v1/keys (JWKS)
```

## Trust Layers

| Layer | What it proves | How | Expiry |
|-------|---------------|-----|--------|
| 0 | Manifest exists at `/.well-known/oap.json` over HTTPS, valid JSON, required fields | Automated fetch + validation | N/A |
| 1 | Publisher controls the domain | DNS TXT or HTTP challenge (SPF/DKIM pattern) | 90 days |
| 2 | Capability does what the manifest claims | Endpoint liveness, health check, example invocation | 7 days |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

Start the API (port 8301 by default):

```bash
oap-trust-api
```

### CLI

```bash
# Initiate domain attestation (Layer 1)
oap-trust attest example.com

# Check challenge status / retrieve attestation
oap-trust verify example.com

# Run capability tests (Layer 2)
oap-trust test-capability example.com

# Check API health
oap-trust status

# Fetch JWKS public keys
oap-trust keys
```

All commands accept `--json` for machine-readable output and `--api` to override the API URL (default: `http://localhost:8301`, or set `OAP_TRUST_API_URL`).

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/attest/domain` | Initiate Layer 1 attestation (returns challenge) |
| `GET` | `/v1/attest/domain/{domain}/status` | Verify challenge, issue attestation |
| `POST` | `/v1/attest/capability` | Run Layer 2 capability tests |
| `GET` | `/v1/attestations/{domain}` | Fetch attestations (what agents query) |
| `GET` | `/v1/keys` | JWKS public keys for signature verification |
| `GET` | `/health` | Health check |

## Configuration

Edit `config.yaml` or use environment variables (`OAP_<SECTION>_<KEY>`):

```yaml
keys:
  path: ./oap_trust_data/keys
  rotation_days: 365

database:
  path: ./oap_trust_data/trust.db

attestation:
  layer1_expiry_days: 90
  layer2_expiry_days: 7
  challenge_ttl_seconds: 3600
  request_timeout: 10

api:
  host: 0.0.0.0
  port: 8301
```

## Design Decisions

- **JWS with Ed25519** — JSON-native signatures, no external CA dependency
- **DNS TXT + HTTP challenges** — proven pattern from SPF/DKIM, not ACME (which is TLS-specific)
- **SQLite** — no vector search needed here, simpler than ChromaDB
- **SSRF protection** — private IP blocking on all outbound requests, ported from `lib/security.ts`
- **Separate package** — independent `pyproject.toml`, no coupling to the discovery stack

## Tests

```bash
pytest tests/ -v
```

## License

CC0 1.0 Universal — no rights reserved.

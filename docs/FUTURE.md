# Future Work

Ideas and improvements to revisit after the reference implementation is built.

## Spec Improvements

### ~~Add "Writing Effective Descriptions" guidance~~
Done. Added to SPEC.md — guidance on writing descriptions that work as cognitive interfaces, search documents, and trust signals.

### ~~Revisit `invoke` section for real-world completeness~~
Done. SPEC.md now includes `auth_url`, `auth_in`, `auth_name`, and `headers` fields, plus a full invocation procedure section.

## Trust Overlay

### Solve the bootstrapping problem
The trust overlay has a bootstrapping problem: who are the first trust providers? The answer is the same as discovery — build the first one as a reference architecture. Don't prescribe it in the spec; prove it works by running it. A reference trust provider demonstrates the attestation flow end-to-end and gives the ecosystem something concrete to build against or replace.

## Messaging & Positioning

### ~~Reconsider manifesto tone for adoption~~
Done. Reframed from confrontational ("blind spots," "nobody is incentivized") to observational ("perspectives," "what structural forces would prevent it from surfacing"). Sharp voice preserved, accusatory framing removed.

"""Core attestation orchestrator — ties verification, signing, and storage together."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .capability_test import test_capability
from .config import Config
from .db import TrustStore
from .dns_challenge import (
    challenge_expiry,
    challenge_instructions,
    generate_token,
    verify_challenge,
)
from .keys import KeyManager
from .manifest import check_layer0, fetch_manifest, hash_manifest
from .models import (
    AttestationRecord,
    CapabilityTestResult,
    ChallengeResponse,
    ChallengeStatusResponse,
    Layer0Result,
)

log = logging.getLogger("oap.trust.attestation")

ISSUER = "oap-trust-reference"


class AttestationService:
    """Orchestrates the full attestation flow across all layers."""

    def __init__(self, cfg: Config, keys: KeyManager, store: TrustStore) -> None:
        self._cfg = cfg
        self._keys = keys
        self._store = store

    # --- Layer 0 ---

    async def check_layer0(
        self, domain: str, *, allow_http: bool = False
    ) -> Layer0Result:
        """Run Layer 0 verification."""
        return await check_layer0(domain, self._cfg.attestation, allow_http=allow_http)

    # --- Layer 1: Domain Attestation ---

    async def initiate_domain_attestation(
        self,
        domain: str,
        method: str = "dns",
        *,
        allow_http: bool = False,
    ) -> ChallengeResponse:
        """Start Layer 1 attestation: run Layer 0 checks, then issue a challenge."""
        # Run Layer 0 first
        layer0 = await check_layer0(
            domain, self._cfg.attestation, allow_http=allow_http
        )
        if not layer0.passed:
            raise ValueError(
                f"Layer 0 checks failed for {domain}: {'; '.join(layer0.errors)}"
            )

        # Generate challenge
        token = generate_token()
        expires = challenge_expiry(self._cfg.attestation)
        instructions = challenge_instructions(domain, token, method)

        # Store challenge
        self._store.create_challenge(domain, token, method, expires)

        log.info("Challenge issued for %s (method=%s)", domain, method)
        return ChallengeResponse(
            domain=domain,
            method=method,
            token=token,
            instructions=instructions,
            expires_at=expires,
            layer0=layer0,
        )

    async def verify_domain_attestation(
        self,
        domain: str,
        *,
        allow_http: bool = False,
    ) -> ChallengeStatusResponse:
        """Verify a pending challenge and issue attestation if verified."""
        challenge = self._store.get_pending_challenge(domain)
        if not challenge:
            return ChallengeStatusResponse(
                domain=domain,
                challenge_verified=False,
                error="No pending challenge found for this domain",
            )

        # Verify the challenge
        verified = await verify_challenge(
            domain,
            challenge["token"],
            challenge["method"],
            self._cfg.attestation,
        )

        if not verified:
            return ChallengeStatusResponse(
                domain=domain,
                challenge_verified=False,
                error=f"Challenge not verified (method: {challenge['method']}). "
                      f"Ensure the {challenge['method'].upper()} record/file is in place.",
            )

        # Mark challenge done
        self._store.mark_challenge_verified(challenge["token"])

        # Re-fetch manifest for current hash
        try:
            manifest, _ = await fetch_manifest(
                domain, self._cfg.attestation, allow_http=allow_http
            )
            manifest_hash = hash_manifest(manifest)
        except Exception as e:
            return ChallengeStatusResponse(
                domain=domain,
                challenge_verified=True,
                error=f"Challenge verified but failed to fetch manifest for signing: {e}",
            )

        # Sign and store attestation
        attestation = self._sign_attestation(
            domain=domain,
            layer=1,
            manifest_hash=manifest_hash,
            verification_method=challenge["method"],
            expiry_days=self._cfg.attestation.layer1_expiry_days,
        )

        log.info("Layer 1 attestation issued for %s", domain)
        return ChallengeStatusResponse(
            domain=domain,
            challenge_verified=True,
            attestation=attestation,
        )

    # --- Layer 2: Capability Attestation ---

    async def attest_capability(
        self,
        domain: str,
        *,
        allow_http: bool = False,
    ) -> tuple[CapabilityTestResult, AttestationRecord | None]:
        """Run Layer 2 capability tests and issue attestation if passed."""
        # Fetch manifest
        try:
            manifest, _ = await fetch_manifest(
                domain, self._cfg.attestation, allow_http=allow_http
            )
        except Exception as e:
            return (
                CapabilityTestResult(
                    endpoint_live=False,
                    passed=False,
                    errors=[f"Failed to fetch manifest: {e}"],
                ),
                None,
            )

        manifest_hash = hash_manifest(manifest)

        # Run capability tests
        test_result = await test_capability(
            manifest, self._cfg.attestation, allow_http=allow_http
        )

        if not test_result.passed:
            return test_result, None

        # Sign and store attestation
        attestation = self._sign_attestation(
            domain=domain,
            layer=2,
            manifest_hash=manifest_hash,
            verification_method="capability_test",
            expiry_days=self._cfg.attestation.layer2_expiry_days,
        )

        log.info("Layer 2 attestation issued for %s", domain)
        return test_result, attestation

    # --- Query ---

    def get_attestations(self, domain: str) -> list[AttestationRecord]:
        """Get all valid attestations for a domain."""
        rows = self._store.get_attestations(domain)
        return [
            AttestationRecord(
                domain=r["domain"],
                layer=r["layer"],
                jws=r["jws"],
                manifest_hash=r["manifest_hash"],
                issued_at=datetime.fromisoformat(r["issued_at"]),
                expires_at=datetime.fromisoformat(r["expires_at"]),
                verification_method=r.get("verification_method"),
            )
            for r in rows
        ]

    # --- Internal ---

    def _sign_attestation(
        self,
        domain: str,
        layer: int,
        manifest_hash: str,
        verification_method: str | None,
        expiry_days: int,
    ) -> AttestationRecord:
        """Create, sign, and store an attestation."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=expiry_days)

        payload = {
            "iss": ISSUER,
            "sub": domain,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "oap_layer": layer,
            "oap_manifest_hash": manifest_hash,
            "oap_verification_method": verification_method,
        }

        jws_token = self._keys.sign(payload)

        self._store.store_attestation(
            domain=domain,
            layer=layer,
            jws=jws_token,
            manifest_hash=manifest_hash,
            verification_method=verification_method,
            issued_at=now,
            expires_at=expires,
        )

        return AttestationRecord(
            domain=domain,
            layer=layer,
            jws=jws_token,
            manifest_hash=manifest_hash,
            issued_at=now,
            expires_at=expires,
            verification_method=verification_method,
        )

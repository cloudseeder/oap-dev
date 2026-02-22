"""Procedural memory engine — experience-augmented discovery and invocation."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from .config import ExperienceConfig
from .discovery import DiscoveryEngine, _extract_json
from .experience_models import (
    CorrectionEntry,
    DiscoveryRecord,
    ExperienceInvokeRequest,
    ExperienceInvokeResponse,
    ExperienceRecord,
    ExperienceRoute,
    IntentRecord,
    InvocationRecord,
    InvocationResult,
    OutcomeRecord,
    ParameterMapping,
)
from .experience_store import ExperienceStore
from .invoker import invoke_manifest
from .models import DiscoverMatch, InvokeSpec
from .ollama_client import OllamaClient

log = logging.getLogger("oap.experience")

FINGERPRINT_SYSTEM = """\
You are an intent classifier. Given a natural language task, produce a hierarchical \
intent fingerprint and domain classification.

Respond with ONLY a JSON object (no markdown, no extra text):
{"fingerprint": "verb.category.specific_action", "domain": "broad.narrow"}

The fingerprint MUST be deterministic: the same task should always produce the same fingerprint. \
Focus on the core action, not surface wording.

Examples:
- "Search text files for regex" → {"fingerprint": "search.text.pattern_match", "domain": "developer.tools"}
- "Find lines matching a pattern" → {"fingerprint": "search.text.pattern_match", "domain": "developer.tools"}
- "Count the words in this text" → {"fingerprint": "count.text.word_count", "domain": "text.processing"}
- "How many lines in this file" → {"fingerprint": "count.text.line_count", "domain": "text.processing"}
- "What is 2+2" → {"fingerprint": "compute.math.calculation", "domain": "math.arithmetic"}
- "Calculate 15% tip on $80" → {"fingerprint": "compute.math.calculation", "domain": "math.arithmetic"}
- "What time is it" → {"fingerprint": "query.system.date_time", "domain": "system.info"}
- "Show today's date" → {"fingerprint": "query.system.date_time", "domain": "system.info"}
- "Filter JSON with jq" → {"fingerprint": "transform.data.json_query", "domain": "developer.tools"}
- "Find a command for disk usage" → {"fingerprint": "search.system.command_lookup", "domain": "system.tools"}
- "Read the manual for grep" → {"fingerprint": "query.system.manual_page", "domain": "system.tools"}
"""

PARAM_EXTRACT_SYSTEM = """\
You are an API parameter mapper. Given a task description and a manifest's invoke \
specification, extract the parameters the task implies.

Respond with ONLY a JSON object (no markdown, no extra text):
{"parameters": {"param_name": {"source": "description of where the value comes from", "transform": null, "value": "extracted_value"}}}

If the task provides input text directly (e.g. for a text processor), use "input" as \
the parameter name with the text as the value.

If no parameters can be extracted, respond: {"parameters": {}}
"""


def _make_experience_id(fingerprint: str, manifest_domain: str) -> str:
    """Generate a deterministic experience ID."""
    now = datetime.now(timezone.utc)
    h = hashlib.sha256(f"{fingerprint}:{manifest_domain}".encode()).hexdigest()[:8]
    return f"exp_{now.strftime('%Y%m%d')}_{h}"


class ExperienceEngine:
    """Experience-augmented discovery: cache + discover + invoke + learn."""

    def __init__(
        self,
        discovery: DiscoveryEngine,
        ollama: OllamaClient,
        store: ExperienceStore,
        config: ExperienceConfig,
    ) -> None:
        self._discovery = discovery
        self._ollama = ollama
        self._store = store
        self._config = config

    async def process(
        self, request: ExperienceInvokeRequest
    ) -> ExperienceInvokeResponse:
        """Run the three-path experience-augmented flow.

        Path 1 (cache_hit): High-confidence exact fingerprint match → use cached pattern.
        Path 2 (partial_match): Similar match → validate with discovery → execute.
        Path 3 (full_discovery): No match → full discovery → execute → cache.
        """
        threshold = request.confidence_threshold

        # Step 1: Fingerprint the intent
        fingerprint, intent_domain = await self.fingerprint_intent(request.task)

        if fingerprint is None:
            # Fingerprinting failed — go straight to path 3
            log.warning("Intent fingerprinting failed, using full discovery")
            return await self._path3_full_discovery(request, "unknown", "unknown")

        # Step 2: Search experience cache
        exact_matches = self._store.find_by_fingerprint(fingerprint)

        # Path 1: Exact match with high confidence and previous success
        for exp in exact_matches:
            if (
                exp.discovery.confidence >= threshold
                and exp.outcome.status == "success"
            ):
                log.info(
                    "Cache hit: %s (confidence=%.2f, use_count=%d)",
                    exp.id,
                    exp.discovery.confidence,
                    exp.use_count,
                )
                return await self._path1_cache_hit(request, exp)

        # Path 2: Similar match (prefix or same domain)
        fp_parts = fingerprint.split(".")
        if len(fp_parts) >= 2:
            prefix = ".".join(fp_parts[:2])
            similar = self._store.find_similar(intent_domain, prefix)
            if similar:
                best = similar[0]
                log.info(
                    "Partial match: %s (fingerprint=%s, confidence=%.2f)",
                    best.id,
                    best.intent.fingerprint,
                    best.discovery.confidence,
                )
                return await self._path2_partial_match(
                    request, fingerprint, intent_domain, best
                )

        # Path 3: No match
        log.info("No experience match for fingerprint=%s", fingerprint)
        return await self._path3_full_discovery(request, fingerprint, intent_domain)

    async def fingerprint_intent(
        self, task: str
    ) -> tuple[str | None, str | None]:
        """Use qwen3 to classify the task into a fingerprint and domain."""
        try:
            raw, _ = await self._ollama.chat(
                task, system=FINGERPRINT_SYSTEM, timeout=120,
                think=False, temperature=0, format="json",
            )
            parsed = _extract_json(raw)
            if parsed and "fingerprint" in parsed and "domain" in parsed:
                return parsed["fingerprint"], parsed["domain"]
        except Exception:
            log.exception("Fingerprinting failed")
        return None, None

    async def _extract_params(
        self, task: str, invoke_spec: InvokeSpec
    ) -> dict[str, ParameterMapping]:
        """Use qwen3 to extract parameters from the task for the invoke spec."""
        prompt = (
            f"Task: {task}\n\n"
            f"Invoke spec:\n"
            f"  Method: {invoke_spec.method}\n"
            f"  URL: {invoke_spec.url}\n"
        )
        try:
            raw, _ = await self._ollama.generate(prompt, system=PARAM_EXTRACT_SYSTEM)
            parsed = _extract_json(raw)
            if parsed and "parameters" in parsed:
                mappings = {}
                for name, info in parsed["parameters"].items():
                    if isinstance(info, dict):
                        mappings[name] = ParameterMapping(
                            source=info.get("source", "task"),
                            transform=info.get("transform"),
                            value_used=str(info.get("value", "")),
                        )
                return mappings
        except Exception:
            log.exception("Parameter extraction failed")
        return {}

    async def _path1_cache_hit(
        self,
        request: ExperienceInvokeRequest,
        experience: ExperienceRecord,
    ) -> ExperienceInvokeResponse:
        """Use cached invocation pattern directly."""
        # Reconstruct invoke spec from experience
        invoke_spec = InvokeSpec(
            method=experience.invocation.method,
            url=experience.invocation.endpoint,
        )

        # Build params from cached parameter mapping
        params: dict[str, Any] | None = None
        stdin_text: str | None = None
        if experience.invocation.parameter_mapping:
            if invoke_spec.method.upper() == "STDIO":
                # For stdio, concatenate param values as stdin
                values = [
                    pm.value_used
                    for pm in experience.invocation.parameter_mapping.values()
                ]
                stdin_text = " ".join(values) if values else None
            else:
                params = {
                    k: pm.value_used
                    for k, pm in experience.invocation.parameter_mapping.items()
                }

        # Execute
        result = await invoke_manifest(
            invoke_spec,
            params,
            stdin_text=stdin_text,
            http_timeout=self._config.invoke_timeout,
            stdio_timeout=self._config.stdio_timeout,
        )

        # Touch the experience record
        self._store.touch(experience.id)

        # Build match from experience data
        match = DiscoverMatch(
            domain=experience.discovery.manifest_matched,
            name=experience.discovery.manifest_matched,
            description=f"Cached: {experience.intent.fingerprint}",
            invoke=invoke_spec,
            score=1.0 - experience.discovery.confidence,
            reason=f"Experience cache hit (used {experience.use_count + 1} times)",
        )

        return ExperienceInvokeResponse(
            task=request.task,
            route=ExperienceRoute(
                path="cache_hit",
                cache_confidence=experience.discovery.confidence,
                experience_id=experience.id,
            ),
            match=match,
            experience=experience,
            invocation_result=result,
        )

    async def _path2_partial_match(
        self,
        request: ExperienceInvokeRequest,
        fingerprint: str,
        intent_domain: str,
        template: ExperienceRecord,
    ) -> ExperienceInvokeResponse:
        """Use cached experience as template, validate with discovery."""
        # Run discovery to validate
        discover_result = await self._discovery.discover(
            request.task, top_k=request.top_k
        )

        if not discover_result.match:
            return ExperienceInvokeResponse(
                task=request.task,
                route=ExperienceRoute(
                    path="partial_match",
                    cache_confidence=template.discovery.confidence,
                    experience_id=template.id,
                ),
                candidates=discover_result.candidates,
            )

        match = discover_result.match

        # Extract params for this invocation
        param_mappings = await self._extract_params(request.task, match.invoke)

        # Execute
        params: dict[str, Any] | None = None
        stdin_text: str | None = None
        if param_mappings:
            if match.invoke.method.upper() == "STDIO":
                values = [pm.value_used for pm in param_mappings.values()]
                stdin_text = " ".join(values) if values else None
            else:
                params = {k: pm.value_used for k, pm in param_mappings.items()}

        result = await invoke_manifest(
            match.invoke,
            params,
            stdin_text=stdin_text,
            http_timeout=self._config.invoke_timeout,
            stdio_timeout=self._config.stdio_timeout,
        )

        # Create or update experience record
        now = datetime.now(timezone.utc)
        exp_id = _make_experience_id(fingerprint, match.domain)
        experience = ExperienceRecord(
            id=exp_id,
            timestamp=now,
            use_count=1,
            last_used=now,
            intent=IntentRecord(
                raw=request.task,
                fingerprint=fingerprint,
                domain=intent_domain,
            ),
            discovery=DiscoveryRecord(
                query_used=request.task,
                manifest_matched=match.domain,
                manifest_version=None,
                confidence=1.0 - match.score if match.score < 1.0 else match.score,
            ),
            invocation=InvocationRecord(
                endpoint=match.invoke.url,
                method=match.invoke.method,
                parameter_mapping=param_mappings,
            ),
            outcome=OutcomeRecord(
                status=result.status,
                http_code=result.http_code,
                response_summary=result.response_body[:200] if result.response_body else "",
                latency_ms=result.latency_ms,
            ),
        )
        self._store.save(experience)

        return ExperienceInvokeResponse(
            task=request.task,
            route=ExperienceRoute(
                path="partial_match",
                cache_confidence=template.discovery.confidence,
                experience_id=exp_id,
            ),
            match=match,
            experience=experience,
            invocation_result=result,
            candidates=discover_result.candidates,
        )

    async def _path3_full_discovery(
        self,
        request: ExperienceInvokeRequest,
        fingerprint: str,
        intent_domain: str,
    ) -> ExperienceInvokeResponse:
        """Full discovery from scratch, then execute and cache."""
        discover_result = await self._discovery.discover(
            request.task, top_k=request.top_k
        )

        if not discover_result.match:
            return ExperienceInvokeResponse(
                task=request.task,
                route=ExperienceRoute(path="full_discovery"),
                candidates=discover_result.candidates,
            )

        match = discover_result.match

        # Extract params
        param_mappings = await self._extract_params(request.task, match.invoke)

        # Execute
        params: dict[str, Any] | None = None
        stdin_text: str | None = None
        if param_mappings:
            if match.invoke.method.upper() == "STDIO":
                values = [pm.value_used for pm in param_mappings.values()]
                stdin_text = " ".join(values) if values else None
            else:
                params = {k: pm.value_used for k, pm in param_mappings.items()}

        result = await invoke_manifest(
            match.invoke,
            params,
            stdin_text=stdin_text,
            http_timeout=self._config.invoke_timeout,
            stdio_timeout=self._config.stdio_timeout,
        )

        # Cache the new experience
        now = datetime.now(timezone.utc)
        exp_id = _make_experience_id(fingerprint, match.domain)
        experience = ExperienceRecord(
            id=exp_id,
            timestamp=now,
            use_count=1,
            last_used=now,
            intent=IntentRecord(
                raw=request.task,
                fingerprint=fingerprint,
                domain=intent_domain,
            ),
            discovery=DiscoveryRecord(
                query_used=request.task,
                manifest_matched=match.domain,
                manifest_version=None,
                confidence=1.0 - match.score if match.score < 1.0 else match.score,
            ),
            invocation=InvocationRecord(
                endpoint=match.invoke.url,
                method=match.invoke.method,
                parameter_mapping=param_mappings,
            ),
            outcome=OutcomeRecord(
                status=result.status,
                http_code=result.http_code,
                response_summary=result.response_body[:200] if result.response_body else "",
                latency_ms=result.latency_ms,
            ),
        )
        self._store.save(experience)

        return ExperienceInvokeResponse(
            task=request.task,
            route=ExperienceRoute(
                path="full_discovery",
                experience_id=exp_id,
            ),
            match=match,
            experience=experience,
            invocation_result=result,
            candidates=discover_result.candidates,
        )

"""Tests for procedural memory: experience store + engine."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oap_discovery.config import ExperienceConfig
from oap_discovery.discovery import DiscoveryEngine
from oap_discovery.experience_engine import ExperienceEngine
from oap_discovery.ollama_client import OllamaMetrics
from oap_discovery.experience_models import (
    CorrectionEntry,
    DiscoveryRecord,
    ExperienceInvokeRequest,
    ExperienceRecord,
    IntentRecord,
    InvocationRecord,
    InvocationResult,
    OutcomeRecord,
    ParameterMapping,
)
from oap_discovery.experience_store import ExperienceStore
from oap_discovery.models import DiscoverMatch, DiscoverResponse, InvokeSpec


def _make_record(
    record_id: str = "exp_20260219_abcd1234",
    fingerprint: str = "search.text.pattern_match",
    domain: str = "developer.tools",
    manifest: str = "grep",
    confidence: float = 0.92,
    status: str = "success",
    use_count: int = 1,
) -> ExperienceRecord:
    """Create a sample experience record for testing."""
    now = datetime.now(timezone.utc)
    return ExperienceRecord(
        id=record_id,
        timestamp=now,
        use_count=use_count,
        last_used=now,
        intent=IntentRecord(
            raw="search text files for a regex pattern",
            fingerprint=fingerprint,
            domain=domain,
        ),
        discovery=DiscoveryRecord(
            query_used="search text files for a regex pattern",
            manifest_matched=manifest,
            manifest_version=None,
            confidence=confidence,
        ),
        invocation=InvocationRecord(
            endpoint="grep",
            method="stdio",
            parameter_mapping={
                "pattern": ParameterMapping(
                    source="intent.pattern",
                    transform=None,
                    value_used="test",
                ),
            },
        ),
        outcome=OutcomeRecord(
            status=status,
            http_code=0,
            response_summary="matched 3 lines",
            latency_ms=15,
        ),
        corrections=[],
    )


# --- ExperienceStore tests ---


class TestExperienceStore:
    @pytest.fixture
    def store(self, tmp_path):
        return ExperienceStore(str(tmp_path / "test_experience.db"))

    @pytest.fixture
    def sample_record(self) -> ExperienceRecord:
        return _make_record()

    def test_save_and_get(self, store, sample_record):
        store.save(sample_record)
        retrieved = store.get(sample_record.id)
        assert retrieved is not None
        assert retrieved.id == sample_record.id
        assert retrieved.intent.fingerprint == "search.text.pattern_match"
        assert retrieved.discovery.manifest_matched == "grep"
        assert retrieved.outcome.status == "success"

    def test_get_nonexistent(self, store):
        assert store.get("nonexistent") is None

    def test_find_by_fingerprint(self, store, sample_record):
        store.save(sample_record)
        results = store.find_by_fingerprint("search.text.pattern_match")
        assert len(results) == 1
        assert results[0].id == sample_record.id

    def test_find_by_fingerprint_no_match(self, store, sample_record):
        store.save(sample_record)
        results = store.find_by_fingerprint("query.zoning.parcel_lookup")
        assert len(results) == 0

    def test_find_similar_prefix_match(self, store):
        store.save(_make_record(record_id="exp_1", fingerprint="search.text.pattern_match"))
        store.save(_make_record(record_id="exp_2", fingerprint="search.text.keyword_search"))
        store.save(_make_record(record_id="exp_3", fingerprint="query.data.lookup"))

        results = store.find_similar("developer.tools", "search.text")
        assert len(results) == 2
        ids = {r.id for r in results}
        assert "exp_1" in ids
        assert "exp_2" in ids

    def test_touch_increments_use_count(self, store, sample_record):
        store.save(sample_record)
        original = store.get(sample_record.id)
        assert original.use_count == 1

        store.touch(sample_record.id)
        updated = store.get(sample_record.id)
        assert updated.use_count == 2
        assert updated.last_used >= original.last_used

    def test_delete(self, store, sample_record):
        store.save(sample_record)
        assert store.delete(sample_record.id) is True
        assert store.get(sample_record.id) is None

    def test_delete_nonexistent(self, store):
        assert store.delete("nonexistent") is False

    def test_list_all_pagination(self, store):
        for i in range(5):
            store.save(_make_record(record_id=f"exp_{i}"))

        result = store.list_all(page=1, limit=2)
        assert len(result["records"]) == 2
        assert result["total"] == 5
        assert result["page"] == 1

        result2 = store.list_all(page=2, limit=2)
        assert len(result2["records"]) == 2

    def test_count(self, store, sample_record):
        assert store.count() == 0
        store.save(sample_record)
        assert store.count() == 1

    def test_stats_empty(self, store):
        stats = store.stats()
        assert stats["total"] == 0
        assert stats["avg_confidence"] == 0.0
        assert stats["success_rate"] == 0.0

    def test_stats(self, store):
        store.save(_make_record(record_id="exp_1", confidence=0.9, status="success"))
        store.save(_make_record(record_id="exp_2", confidence=0.8, status="failure"))
        stats = store.stats()
        assert stats["total"] == 2
        assert stats["avg_confidence"] == pytest.approx(0.85, abs=0.01)
        assert stats["success_rate"] == pytest.approx(0.5, abs=0.01)

    def test_upsert_replaces(self, store, sample_record):
        store.save(sample_record)
        # Save again with different outcome
        updated = _make_record(status="failure")
        store.save(updated)
        retrieved = store.get(sample_record.id)
        assert retrieved.outcome.status == "failure"

    def test_corrections_roundtrip(self, store):
        record = _make_record()
        record.corrections = [
            CorrectionEntry(
                attempted="1234-56-789",
                error="Invalid format",
                fix="remove_hyphens",
            )
        ]
        store.save(record)
        retrieved = store.get(record.id)
        assert len(retrieved.corrections) == 1
        assert retrieved.corrections[0].fix == "remove_hyphens"

    def test_parameter_mapping_roundtrip(self, store):
        record = _make_record()
        record.invocation.parameter_mapping = {
            "query": ParameterMapping(source="intent.text", transform="lowercase", value_used="hello"),
            "limit": ParameterMapping(source="default", transform=None, value_used="10"),
        }
        store.save(record)
        retrieved = store.get(record.id)
        assert "query" in retrieved.invocation.parameter_mapping
        assert retrieved.invocation.parameter_mapping["query"].transform == "lowercase"
        assert retrieved.invocation.parameter_mapping["limit"].value_used == "10"


# --- ExperienceEngine tests ---


class TestExperienceEngine:
    @pytest.fixture
    def experience_store(self, tmp_path):
        return ExperienceStore(str(tmp_path / "exp.db"))

    @pytest.fixture
    def config(self):
        return ExperienceConfig(
            enabled=True,
            confidence_threshold=0.85,
            invoke_timeout=30,
            stdio_timeout=10,
        )

    @pytest.fixture
    def mock_store(self):
        store = MagicMock()
        store.search.return_value = [
            {
                "domain": "grep",
                "name": "grep",
                "description": "Searches text for lines matching a pattern.",
                "manifest": {
                    "oap": "1.0",
                    "name": "grep",
                    "description": "Searches text for lines matching a pattern.",
                    "invoke": {"method": "stdio", "url": "grep"},
                },
                "score": 0.15,
            },
        ]
        return store

    @pytest.fixture
    def mock_ollama(self):
        _m = OllamaMetrics(model="test", prompt_tokens=10, generated_tokens=5, total_ms=100, eval_ms=50)
        ollama = AsyncMock()
        ollama.embed_query.return_value = ([0.1] * 768, _m)
        ollama._stub_metrics = _m  # available to tests for building side_effects
        return ollama

    @pytest.fixture
    def mock_invocation_result(self):
        return InvocationResult(
            status="success",
            http_code=0,
            response_body="match found",
            latency_ms=10,
        )

    @pytest.mark.asyncio
    async def test_path3_full_discovery_creates_record(
        self, experience_store, config, mock_store, mock_ollama, mock_invocation_result
    ):
        """Empty cache → full discovery → new experience record created."""
        # Fingerprint via chat(think=False), then discovery pick + param extraction via generate()
        _m = mock_ollama._stub_metrics
        mock_ollama.chat.return_value = (
            '{"fingerprint": "search.text.pattern_match", "domain": "developer.tools"}', _m,
        )
        mock_ollama.generate.side_effect = [
            ('{"pick": "grep", "reason": "grep is for text search"}', _m),
            ('{"parameters": {"pattern": {"source": "intent.text", "transform": null, "value": "test"}}}', _m),
        ]

        discovery = DiscoveryEngine(mock_store, mock_ollama)
        engine = ExperienceEngine(discovery, mock_ollama, experience_store, config)

        with patch("oap_discovery.experience_engine.invoke_manifest", return_value=mock_invocation_result):
            result = await engine.process(
                ExperienceInvokeRequest(task="search for test in files")
            )

        assert result.route.path == "full_discovery"
        assert result.match is not None
        assert result.match.domain == "grep"
        assert result.invocation_result is not None
        assert result.invocation_result.status == "success"
        assert result.experience is not None

        # Verify record was stored
        assert experience_store.count() == 1

    @pytest.mark.asyncio
    async def test_path1_cache_hit(
        self, experience_store, config, mock_store, mock_ollama, mock_invocation_result
    ):
        """Pre-populated cache → cache hit → use_count incremented, discovery not called."""
        # Pre-populate the cache
        record = _make_record(confidence=0.92)
        experience_store.save(record)

        # Only fingerprint call needed (no discovery, no param extraction)
        _m = mock_ollama._stub_metrics
        mock_ollama.chat.return_value = (
            '{"fingerprint": "search.text.pattern_match", "domain": "developer.tools"}', _m,
        )

        discovery = DiscoveryEngine(mock_store, mock_ollama)
        engine = ExperienceEngine(discovery, mock_ollama, experience_store, config)

        with patch("oap_discovery.experience_engine.invoke_manifest", return_value=mock_invocation_result):
            result = await engine.process(
                ExperienceInvokeRequest(task="search text files for a regex pattern")
            )

        assert result.route.path == "cache_hit"
        assert result.route.cache_confidence == 0.92
        assert result.invocation_result.status == "success"

        # Verify use_count was incremented
        updated = experience_store.get(record.id)
        assert updated.use_count == 2

        # Discovery should NOT have been called (only fingerprint generation)
        mock_store.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_path2_partial_match(
        self, experience_store, config, mock_store, mock_ollama, mock_invocation_result
    ):
        """Similar fingerprint → discovery validates → new record created."""
        # Pre-populate with a related but different fingerprint
        record = _make_record(
            record_id="exp_related",
            fingerprint="search.text.keyword_search",
            confidence=0.80,
        )
        experience_store.save(record)

        # Fingerprint via chat(think=False), then discovery pick + param extraction via generate()
        _m = mock_ollama._stub_metrics
        mock_ollama.chat.return_value = (
            '{"fingerprint": "search.text.regex_match", "domain": "developer.tools"}', _m,
        )
        mock_ollama.generate.side_effect = [
            ('{"pick": "grep", "reason": "grep handles regex"}', _m),
            ('{"parameters": {"pattern": {"source": "intent.text", "transform": null, "value": ".*test.*"}}}', _m),
        ]

        discovery = DiscoveryEngine(mock_store, mock_ollama)
        engine = ExperienceEngine(discovery, mock_ollama, experience_store, config)

        with patch("oap_discovery.experience_engine.invoke_manifest", return_value=mock_invocation_result):
            result = await engine.process(
                ExperienceInvokeRequest(task="search files with regex .*test.*")
            )

        assert result.route.path == "partial_match"
        assert result.match is not None
        assert result.invocation_result.status == "success"

        # Should have created a new record (2 total now)
        assert experience_store.count() == 2

    @pytest.mark.asyncio
    async def test_confidence_threshold_boundary(
        self, experience_store, config, mock_store, mock_ollama, mock_invocation_result
    ):
        """Record with confidence 0.84 should go to path 2, not path 1."""
        # Pre-populate with below-threshold confidence
        record = _make_record(confidence=0.84)
        experience_store.save(record)

        # Fingerprint via chat(think=False), then discovery + params via generate()
        _m = mock_ollama._stub_metrics
        mock_ollama.chat.return_value = (
            '{"fingerprint": "search.text.pattern_match", "domain": "developer.tools"}', _m,
        )
        mock_ollama.generate.side_effect = [
            ('{"pick": "grep", "reason": "best match"}', _m),
            ('{"parameters": {}}', _m),
        ]

        discovery = DiscoveryEngine(mock_store, mock_ollama)
        engine = ExperienceEngine(discovery, mock_ollama, experience_store, config)

        with patch("oap_discovery.experience_engine.invoke_manifest", return_value=mock_invocation_result):
            result = await engine.process(
                ExperienceInvokeRequest(task="search text files for a regex pattern")
            )

        # Should NOT be a cache hit — confidence is below threshold
        assert result.route.path != "cache_hit"

    @pytest.mark.asyncio
    async def test_fingerprint_failure_falls_back(
        self, experience_store, config, mock_store, mock_ollama, mock_invocation_result
    ):
        """If fingerprinting fails, fall back to path 3."""
        _m = mock_ollama._stub_metrics
        mock_ollama.chat.return_value = ("invalid json response", _m)  # fingerprint fails
        mock_ollama.generate.side_effect = [
            ('{"pick": "grep", "reason": "best match"}', _m),  # discovery works
            ('{"parameters": {}}', _m),  # param extraction
        ]

        discovery = DiscoveryEngine(mock_store, mock_ollama)
        engine = ExperienceEngine(discovery, mock_ollama, experience_store, config)

        with patch("oap_discovery.experience_engine.invoke_manifest", return_value=mock_invocation_result):
            result = await engine.process(
                ExperienceInvokeRequest(task="do something")
            )

        assert result.route.path == "full_discovery"

    @pytest.mark.asyncio
    async def test_no_discovery_match_returns_empty(
        self, experience_store, config, mock_ollama
    ):
        """If discovery finds nothing, return empty response."""
        empty_store = MagicMock()
        empty_store.search.return_value = []

        _m = mock_ollama._stub_metrics
        mock_ollama.chat.return_value = (
            '{"fingerprint": "query.unknown.thing", "domain": "unknown"}', _m,
        )

        discovery = DiscoveryEngine(empty_store, mock_ollama)
        engine = ExperienceEngine(discovery, mock_ollama, experience_store, config)

        result = await engine.process(
            ExperienceInvokeRequest(task="do something impossible")
        )

        assert result.route.path == "full_discovery"
        assert result.match is None
        assert result.invocation_result is None

    @pytest.mark.asyncio
    async def test_failed_record_not_used_for_cache_hit(
        self, experience_store, config, mock_store, mock_ollama, mock_invocation_result
    ):
        """Records with status='failure' should not trigger cache hits."""
        record = _make_record(confidence=0.95, status="failure")
        experience_store.save(record)

        # Fingerprint via chat(think=False), then discovery + params via generate()
        _m = mock_ollama._stub_metrics
        mock_ollama.chat.return_value = (
            '{"fingerprint": "search.text.pattern_match", "domain": "developer.tools"}', _m,
        )
        mock_ollama.generate.side_effect = [
            ('{"pick": "grep", "reason": "best match"}', _m),
            ('{"parameters": {}}', _m),
        ]

        discovery = DiscoveryEngine(mock_store, mock_ollama)
        engine = ExperienceEngine(discovery, mock_ollama, experience_store, config)

        with patch("oap_discovery.experience_engine.invoke_manifest", return_value=mock_invocation_result):
            result = await engine.process(
                ExperienceInvokeRequest(task="search text files for a regex pattern")
            )

        # Should NOT be cache_hit because the record has status='failure'
        assert result.route.path != "cache_hit"

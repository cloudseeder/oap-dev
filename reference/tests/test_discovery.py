"""Tests for the discovery engine (mocked Ollama + ChromaDB)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from oap_discovery.discovery import DiscoveryEngine, _extract_json, _strip_think_blocks
from oap_discovery.models import InvokeSpec


class TestStripThinkBlocks:
    def test_removes_think_block(self):
        text = '<think>some reasoning here</think>{"pick": "grep"}'
        assert _strip_think_blocks(text) == '{"pick": "grep"}'

    def test_removes_multiline_think(self):
        text = '<think>\nline 1\nline 2\n</think>\n{"pick": "grep"}'
        result = _strip_think_blocks(text)
        assert "<think>" not in result
        assert '{"pick": "grep"}' in result

    def test_no_think_block(self):
        text = '{"pick": "grep"}'
        assert _strip_think_blocks(text) == text


class TestExtractJson:
    def test_plain_json(self):
        result = _extract_json('{"pick": "grep", "reason": "matches"}')
        assert result == {"pick": "grep", "reason": "matches"}

    def test_json_with_surrounding_text(self):
        result = _extract_json('Here is my answer: {"pick": "grep", "reason": "best"} done')
        assert result["pick"] == "grep"

    def test_json_with_think_block(self):
        text = '<think>thinking...</think>{"pick": "grep", "reason": "text search"}'
        result = _extract_json(text)
        assert result["pick"] == "grep"

    def test_invalid_json(self):
        assert _extract_json("no json here") is None

    def test_null_pick(self):
        result = _extract_json('{"pick": null, "reason": "none match"}')
        assert result["pick"] is None


class TestDiscoveryEngine:
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
            {
                "domain": "jq",
                "name": "jq",
                "description": "Command-line JSON processor.",
                "manifest": {
                    "oap": "1.0",
                    "name": "jq",
                    "description": "Command-line JSON processor.",
                    "invoke": {"method": "stdio", "url": "jq"},
                },
                "score": 0.45,
            },
        ]
        return store

    @pytest.fixture
    def mock_ollama(self):
        ollama = AsyncMock()
        ollama.embed_query.return_value = [0.1] * 768
        ollama.generate.return_value = '{"pick": "grep", "reason": "grep is for text search"}'
        return ollama

    @pytest.mark.asyncio
    async def test_discover_picks_best(self, mock_store, mock_ollama):
        engine = DiscoveryEngine(mock_store, mock_ollama)
        result = await engine.discover("search for text in files")

        assert result.match is not None
        assert result.match.domain == "grep"
        assert result.match.reason == "grep is for text search"
        assert len(result.candidates) == 2

    @pytest.mark.asyncio
    async def test_discover_empty_index(self, mock_ollama):
        store = MagicMock()
        store.search.return_value = []
        engine = DiscoveryEngine(store, mock_ollama)
        result = await engine.discover("anything")

        assert result.match is None
        assert result.candidates == []

    @pytest.mark.asyncio
    async def test_discover_llm_failure_fallback(self, mock_store, mock_ollama):
        mock_ollama.generate.side_effect = Exception("LLM down")
        engine = DiscoveryEngine(mock_store, mock_ollama)
        result = await engine.discover("search text")

        # Should fall back to top vector match
        assert result.match is not None
        assert result.match.domain == "grep"
        assert "vector similarity" in result.match.reason.lower()

    @pytest.mark.asyncio
    async def test_discover_with_think_blocks(self, mock_store, mock_ollama):
        mock_ollama.generate.return_value = (
            '<think>Let me analyze...</think>{"pick": "grep", "reason": "best for regex search"}'
        )
        engine = DiscoveryEngine(mock_store, mock_ollama)
        result = await engine.discover("regex search")

        assert result.match is not None
        assert result.match.domain == "grep"

    @pytest.mark.asyncio
    async def test_discover_llm_says_no_match(self, mock_store, mock_ollama):
        mock_ollama.generate.return_value = '{"pick": null, "reason": "none of these match"}'
        engine = DiscoveryEngine(mock_store, mock_ollama)
        result = await engine.discover("bake a cake")

        assert result.match is None
        assert len(result.candidates) == 2

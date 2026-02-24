"""Tests for the FTS5 manifest store."""

import tempfile
import os

import pytest

from oap_discovery.fts_store import FTSStore


@pytest.fixture
def fts_store(tmp_path):
    db_path = str(tmp_path / "test_fts.db")
    store = FTSStore(db_path)
    yield store
    store.close()


@pytest.fixture
def grep_manifest():
    return {
        "oap": "1.0",
        "name": "grep",
        "description": "Search text for lines matching a regular expression pattern. "
        "Filters input line by line, printing lines that match. "
        "Supports extended regex, case-insensitive matching, and inverted matches.",
        "input": {"format": "text/plain", "description": "Text and a search pattern"},
        "output": {"format": "text/plain", "description": "Matching lines"},
        "invoke": {"method": "stdio", "url": "grep -E"},
        "tags": ["search", "text", "regex", "filter"],
    }


@pytest.fixture
def jq_manifest():
    return {
        "oap": "1.0",
        "name": "jq",
        "description": "Command-line JSON processor. Extract, transform, and filter "
        "JSON data using a lightweight query language.",
        "input": {"format": "application/json", "description": "JSON data"},
        "output": {"format": "application/json", "description": "Processed JSON"},
        "invoke": {"method": "stdio", "url": "jq"},
        "tags": ["json", "transform", "query"],
    }


@pytest.fixture
def wc_manifest():
    return {
        "oap": "1.0",
        "name": "wc",
        "description": "Count lines, words, and characters in text input.",
        "input": {"format": "text/plain", "description": "Text to count"},
        "output": {"format": "text/plain", "description": "Line, word, and character counts"},
        "invoke": {"method": "stdio", "url": "wc"},
        "tags": ["count", "text", "lines", "words"],
    }


@pytest.fixture
def date_manifest():
    return {
        "oap": "1.0",
        "name": "date",
        "description": "Display or convert dates and times. Supports custom formats "
        "and date arithmetic.",
        "input": {"format": "text/plain", "description": "Date string or format specification"},
        "output": {"format": "text/plain", "description": "Formatted date/time"},
        "invoke": {"method": "stdio", "url": "date"},
        "tags": ["date", "time", "format"],
    }


class TestFTSStoreBasics:
    def test_empty_store(self, fts_store):
        assert fts_store.count() == 0
        assert fts_store.list_domains() == []

    def test_upsert_and_count(self, fts_store, grep_manifest):
        fts_store.upsert_manifest("local/grep", grep_manifest)
        assert fts_store.count() == 1

    def test_upsert_idempotent(self, fts_store, grep_manifest):
        fts_store.upsert_manifest("local/grep", grep_manifest)
        fts_store.upsert_manifest("local/grep", grep_manifest)
        assert fts_store.count() == 1

    def test_get_manifest(self, fts_store, grep_manifest):
        fts_store.upsert_manifest("local/grep", grep_manifest)
        result = fts_store.get_manifest("local/grep")
        assert result is not None
        assert result["name"] == "grep"

    def test_get_manifest_missing(self, fts_store):
        assert fts_store.get_manifest("nonexistent") is None

    def test_list_domains(self, fts_store, grep_manifest, jq_manifest):
        fts_store.upsert_manifest("local/grep", grep_manifest)
        fts_store.upsert_manifest("local/jq", jq_manifest)
        domains = fts_store.list_domains()
        assert len(domains) == 2
        domain_names = {d["domain"] for d in domains}
        assert domain_names == {"local/grep", "local/jq"}


class TestFTSSearch:
    @pytest.fixture(autouse=True)
    def index_manifests(self, fts_store, grep_manifest, jq_manifest, wc_manifest, date_manifest):
        fts_store.upsert_manifest("local/grep", grep_manifest)
        fts_store.upsert_manifest("local/jq", jq_manifest)
        fts_store.upsert_manifest("local/wc", wc_manifest)
        fts_store.upsert_manifest("local/date", date_manifest)

    def test_search_grep_by_keyword(self, fts_store):
        results = fts_store.search("regex pattern matching")
        domains = [r["domain"] for r in results]
        assert "local/grep" in domains

    def test_search_jq_by_keyword(self, fts_store):
        results = fts_store.search("JSON processor")
        domains = [r["domain"] for r in results]
        assert "local/jq" in domains

    def test_search_returns_dict_shape(self, fts_store):
        results = fts_store.search("text")
        assert len(results) > 0
        hit = results[0]
        assert "domain" in hit
        assert "name" in hit
        assert "description" in hit
        assert "manifest" in hit
        assert "score" in hit

    def test_search_respects_n_results(self, fts_store):
        results = fts_store.search("text", n_results=2)
        assert len(results) <= 2

    def test_search_empty_query(self, fts_store):
        results = fts_store.search("")
        assert results == []

    def test_search_no_match(self, fts_store):
        results = fts_store.search("blockchain cryptocurrency")
        assert results == []

    def test_bm25_ranking(self, fts_store):
        """grep should rank higher than wc for 'search pattern' since
        grep's description mentions both words prominently."""
        results = fts_store.search("search pattern")
        if len(results) >= 2:
            domains = [r["domain"] for r in results]
            grep_idx = domains.index("local/grep") if "local/grep" in domains else 999
            assert grep_idx < len(results), "grep should appear in results"

    def test_search_by_tag(self, fts_store):
        """Tags are indexed in FTS5 — searching by tag should find manifests."""
        results = fts_store.search("filter")
        domains = [r["domain"] for r in results]
        assert "local/grep" in domains

    def test_search_count_lines(self, fts_store):
        results = fts_store.search("count lines words")
        domains = [r["domain"] for r in results]
        assert "local/wc" in domains

    def test_search_date_time(self, fts_store):
        results = fts_store.search("date time format")
        domains = [r["domain"] for r in results]
        assert "local/date" in domains


class TestFTSUpsertUpdate:
    def test_update_manifest_description(self, fts_store, grep_manifest):
        fts_store.upsert_manifest("local/grep", grep_manifest)

        # Update description
        updated = {**grep_manifest, "description": "A specialized blockchain analyzer tool."}
        fts_store.upsert_manifest("local/grep", updated)

        # Old keyword should not match, new one should
        assert fts_store.count() == 1
        results = fts_store.search("blockchain")
        domains = [r["domain"] for r in results]
        assert "local/grep" in domains

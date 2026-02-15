"""Shared fixtures for OAP discovery tests."""

import pytest


@pytest.fixture
def grep_manifest() -> dict:
    return {
        "oap": "1.0",
        "name": "grep",
        "description": "Searches text for lines matching a pattern.",
        "input": {"format": "text/plain", "description": "Text and a search pattern"},
        "output": {"format": "text/plain", "description": "Matching lines"},
        "invoke": {"method": "stdio", "url": "grep"},
        "tags": ["search", "text"],
    }


@pytest.fixture
def minimal_manifest() -> dict:
    return {
        "oap": "1.0",
        "name": "Minimal",
        "description": "A minimal manifest with only required fields.",
        "invoke": {"method": "GET", "url": "https://example.com/api"},
    }


@pytest.fixture
def mynewscast_manifest() -> dict:
    return {
        "oap": "1.0",
        "name": "myNewscast Meeting Processor",
        "description": "Ingests government meeting videos and produces structured transcripts with speaker identification.",
        "input": {"format": "text/plain", "description": "URL to a meeting video"},
        "output": {"format": "application/json", "description": "Structured transcript"},
        "invoke": {"method": "POST", "url": "https://api.mynewscast.com/v1/process", "auth": "bearer"},
    }

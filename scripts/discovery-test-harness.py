#!/usr/bin/env python3
"""Discovery Test Harness — integration tests for OAP tool bridge discovery and execution.

Tests semantic matching quality, invocation correctness, and execution success
across all local manifests (grep, wc, jq, date, bc, apropos, man). Hits a live
/v1/chat endpoint with oap_debug enabled.

Usage:
    python scripts/discovery-test-harness.py --token <secret>       # run all
    python scripts/discovery-test-harness.py --category grep,wc    # filter
    python scripts/discovery-test-harness.py --test grep-001       # specific test
    python scripts/discovery-test-harness.py --smoke               # first 10 only
    python scripts/discovery-test-harness.py --dry-run             # list without executing
    python scripts/discovery-test-harness.py --fail-fast           # stop on first FAIL
    python scripts/discovery-test-harness.py --verbose             # full debug on failure
    python scripts/discovery-test-harness.py --json results.json   # JSON report
    python scripts/discovery-test-harness.py --url http://host:8300
    python scripts/discovery-test-harness.py --model qwen3t:4b
    python scripts/discovery-test-harness.py --timeout 120
    python scripts/discovery-test-harness.py --include-cache-tests --token <secret>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    id: str                                        # "grep-001"
    category: str                                  # "grep", "wc", etc.
    task: str                                      # Natural language prompt
    expect_tool: str | list[str] | None = None     # Expected tool(s), None = no tool
    expect_in_output: list[str] = field(default_factory=list)
    expect_error: bool = False                     # True = expect "Error:" in result
    allow_alternatives: list[str] = field(default_factory=list)
    allow_no_tool: bool = False


@dataclass
class TestResult:
    test_id: str
    verdict: str          # PASS, SOFT, WARN, FAIL, SKIP
    tool_called: str      # tool name or ""
    duration_s: float
    task: str
    detail: str = ""      # reason for non-PASS
    debug: dict | None = None


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

PASS = "PASS"
SOFT = "SOFT"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

_IS_TTY = sys.stdout.isatty()

def _color(code: str, text: str) -> str:
    if not _IS_TTY:
        return text
    return f"\033[{code}m{text}\033[0m"

def green(t: str) -> str: return _color("32", t)
def yellow(t: str) -> str: return _color("33", t)
def red(t: str) -> str: return _color("31", t)
def bold(t: str) -> str: return _color("1", t)
def dim(t: str) -> str: return _color("2", t)

VERDICT_COLOR = {
    PASS: green,
    SOFT: yellow,
    WARN: yellow,
    FAIL: red,
    SKIP: dim,
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def health_check(base_url: str, timeout: float, token: str | None = None) -> bool:
    """Check service connectivity via /health (requires token)."""
    headers = {}
    if token:
        headers["X-Backend-Token"] = token
    try:
        resp = httpx.get(f"{base_url}/health", headers=headers, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def send_chat(
    base_url: str,
    task: str,
    model: str,
    timeout: float,
) -> dict[str, Any] | None:
    """POST /v1/chat with oap_debug enabled. Returns response dict or None."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": task}],
        "stream": False,
        "oap_debug": True,
        "oap_discover": True,
        "oap_auto_execute": True,
        "oap_max_rounds": 3,
        "oap_top_k": 10,
    }
    try:
        resp = httpx.post(
            f"{base_url}/v1/chat",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _normalize_tool(name: str | list[str] | None) -> list[str]:
    if name is None:
        return []
    if isinstance(name, str):
        return [name]
    return list(name)


def verify_test(tc: TestCase, response: dict[str, Any] | None, duration_s: float) -> TestResult:
    """Apply the verdict logic to a single test response."""

    if response is None:
        return TestResult(tc.id, SKIP, "", duration_s, tc.task, detail="No response (timeout or server error)")

    debug_info = response.get("oap_debug")

    # Collect tool executions across all rounds
    tool_executions: list[dict] = []
    if debug_info and "rounds" in debug_info:
        for rnd in debug_info["rounds"]:
            tool_executions.extend(rnd.get("tool_executions", []))

    tools_called = [te["tool"] for te in tool_executions]
    tool_results = [te.get("result", "") for te in tool_executions]

    # Message content from the final response
    message_content = response.get("message", {}).get("content", "")

    # Combined text for output matching
    combined = "\n".join(tool_results) + "\n" + message_content

    expected = _normalize_tool(tc.expect_tool)
    primary_tool = tools_called[0] if tools_called else ""

    # 1. No tool called
    if not tools_called:
        if tc.allow_no_tool:
            return TestResult(tc.id, WARN, "", duration_s, tc.task,
                              detail="No tool called (allow_no_tool)", debug=debug_info)
        if not expected:
            # Negative test — expected no tool
            return TestResult(tc.id, PASS, "", duration_s, tc.task, debug=debug_info)
        return TestResult(tc.id, FAIL, "", duration_s, tc.task,
                          detail=f"Expected {expected}, no tool called", debug=debug_info)

    # 2. Tool was called
    # Check if any called tool matches expected
    matched_expected = any(t in expected for t in tools_called) if expected else False

    # Check alternatives
    matched_alt = any(t in tc.allow_alternatives for t in tools_called)

    # 3. Error check
    has_error = any(r.startswith("Error") for r in tool_results)
    if has_error and not tc.expect_error:
        # Unexpected error — but if the tool was right, still count as FAIL with detail
        return TestResult(tc.id, FAIL, primary_tool, duration_s, tc.task,
                          detail=f"Unexpected error in tool result", debug=debug_info)

    # 4. Tool match check
    if not expected:
        # Negative test expected no tool but one was called
        return TestResult(tc.id, FAIL, primary_tool, duration_s, tc.task,
                          detail=f"Expected no tool, got {primary_tool}", debug=debug_info)

    if not matched_expected and not matched_alt:
        return TestResult(tc.id, FAIL, primary_tool, duration_s, tc.task,
                          detail=f"Expected {expected}, got {primary_tool}", debug=debug_info)

    # 5. Output check
    for substr in tc.expect_in_output:
        if substr not in combined:
            verdict = SOFT if matched_alt and not matched_expected else FAIL
            return TestResult(tc.id, verdict, primary_tool, duration_s, tc.task,
                              detail=f'Expected output "{substr}" not found', debug=debug_info)

    # 6. Final verdict
    if matched_expected:
        return TestResult(tc.id, PASS, primary_tool, duration_s, tc.task, debug=debug_info)
    if matched_alt:
        return TestResult(tc.id, SOFT, primary_tool, duration_s, tc.task,
                          detail=f"Alternative tool {primary_tool} used", debug=debug_info)

    return TestResult(tc.id, PASS, primary_tool, duration_s, tc.task, debug=debug_info)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

def build_test_cases() -> list[TestCase]:
    """Return all ~200 test cases."""
    tests: list[TestCase] = []

    # ===== GREP (35 tests) =====

    # Semantic matching — varied phrasings
    tests.append(TestCase("grep-001", "grep",
        'find lines containing "error" in:\nfoo\nerror happened\nbar\nerror again',
        expect_tool="oap_grep", expect_in_output=["error happened"]))
    tests.append(TestCase("grep-002", "grep",
        'search for the word "hello" in this text:\nhello world\ngoodbye world\nhello again',
        expect_tool="oap_grep", expect_in_output=["hello"]))
    tests.append(TestCase("grep-003", "grep",
        'filter lines that contain "warning" from:\ninfo: ok\nwarning: disk full\ninfo: done\nwarning: memory low',
        expect_tool="oap_grep", expect_in_output=["warning"]))
    tests.append(TestCase("grep-004", "grep",
        'which lines match the pattern "2024" in:\nlog 2023-01-01\nlog 2024-06-15\nlog 2024-12-31',
        expect_tool="oap_grep", expect_in_output=["2024"]))
    tests.append(TestCase("grep-005", "grep",
        'look for "TODO" in:\n# TODO fix this\ndef main():\n  # TODO refactor\n  pass',
        expect_tool="oap_grep", expect_in_output=["TODO"]))
    tests.append(TestCase("grep-006", "grep",
        'extract all lines with "fail" from:\ntest1: pass\ntest2: fail\ntest3: pass\ntest4: fail',
        expect_tool="oap_grep", expect_in_output=["fail"]))
    tests.append(TestCase("grep-007", "grep",
        'show me lines matching "^[0-9]" in:\nabc\n123\ndef\n456',
        expect_tool="oap_grep", expect_in_output=["123"],
        allow_no_tool=True))
    tests.append(TestCase("grep-008", "grep",
        'I need to find "connection refused" in:\nconnected ok\nconnection refused by host\ntimeout\nconnection refused again',
        expect_tool="oap_grep", expect_in_output=["connection refused"]))
    tests.append(TestCase("grep-009", "grep",
        'pull out lines with email addresses from:\nJohn Smith\njohn@example.com\nJane Doe\njane@test.org',
        expect_tool="oap_grep", expect_in_output=["@"],
        allow_no_tool=True))
    tests.append(TestCase("grep-010", "grep",
        'grep for "apple" in:\napple pie\nbanana split\napple sauce\ncherry tart',
        expect_tool="oap_grep", expect_in_output=["apple"]))

    # Invocation correctness — flags
    tests.append(TestCase("grep-011", "grep",
        'case-insensitive search for "ERROR" in:\nerror found\nERROR found\nError Found\nno issue',
        expect_tool="oap_grep", expect_in_output=["error", "ERROR"],
        allow_no_tool=True))
    tests.append(TestCase("grep-012", "grep",
        'count how many lines contain "x" in:\nax\nbx\ncy\ndx',
        expect_tool="oap_grep", expect_in_output=["3"],
        allow_alternatives=["oap_wc"]))
    tests.append(TestCase("grep-013", "grep",
        'show lines NOT containing "ok" from:\nstatus: ok\nstatus: fail\nstatus: ok\nstatus: error',
        expect_tool="oap_grep", expect_in_output=["fail"],
        allow_no_tool=True))
    tests.append(TestCase("grep-014", "grep",
        'find lines with numbers using regex pattern "[0-9]+" in:\nabc\n42\ndef\n7',
        expect_tool="oap_grep", expect_in_output=["42"],
        allow_no_tool=True))
    tests.append(TestCase("grep-015", "grep",
        'search for lines starting with "#" in:\n# comment\ncode\n# another comment\nmore code',
        expect_tool="oap_grep", expect_in_output=["# comment"],
        allow_no_tool=True))
    tests.append(TestCase("grep-016", "grep",
        'find "data" in:\nno data here\ndata found\nnothing\nmore data',
        expect_tool="oap_grep", expect_in_output=["data found"]))
    tests.append(TestCase("grep-017", "grep",
        'use grep to find lines with "port" in:\nhost: localhost\nport: 8080\nuser: admin\nport: 3000',
        expect_tool="oap_grep", expect_in_output=["port"]))

    # Execution validation — verify output correctness
    tests.append(TestCase("grep-018", "grep",
        'find "cat" in:\nthe cat sat\non the mat\nthe cat slept',
        expect_tool="oap_grep", expect_in_output=["cat sat", "cat slept"]))
    tests.append(TestCase("grep-019", "grep",
        'search for "200" in:\n200 OK\n404 Not Found\n200 OK\n500 Error',
        expect_tool="oap_grep", expect_in_output=["200 OK"]))
    tests.append(TestCase("grep-020", "grep",
        'find "python" in:\nuse python3\njava is ok\npython rocks\ngo is fast',
        expect_tool="oap_grep", expect_in_output=["python"]))
    tests.append(TestCase("grep-021", "grep",
        'search for "DEBUG" in:\nINFO start\nDEBUG value=42\nWARN slow\nDEBUG done',
        expect_tool="oap_grep", expect_in_output=["DEBUG"]))
    tests.append(TestCase("grep-022", "grep",
        'find lines with "192.168" in:\n10.0.0.1\n192.168.1.1\n172.16.0.1\n192.168.0.1',
        expect_tool="oap_grep", expect_in_output=["192.168"]))
    tests.append(TestCase("grep-023", "grep",
        'filter for lines containing "test" from:\nunit test\nintegration test\ndeploy\nsmoke test',
        expect_tool="oap_grep", expect_in_output=["test"]))

    # No-match tests (expect_error=True since grep returns exit 1)
    tests.append(TestCase("grep-024", "grep",
        'search for "zebra" in:\napple\nbanana\ncherry',
        expect_tool="oap_grep", expect_error=True))
    tests.append(TestCase("grep-025", "grep",
        'find "xyz123" in:\nabc\ndef\nghi',
        expect_tool="oap_grep", expect_error=True))

    # More varied phrasings
    tests.append(TestCase("grep-026", "grep",
        'show only lines that have "success" in:\nattempt 1: success\nattempt 2: failure\nattempt 3: success',
        expect_tool="oap_grep", expect_in_output=["success"]))
    tests.append(TestCase("grep-027", "grep",
        'pick out the lines matching "GET" from:\nGET /index.html\nPOST /api/data\nGET /about\nDELETE /item',
        expect_tool="oap_grep", expect_in_output=["GET"]))
    tests.append(TestCase("grep-028", "grep",
        'which of these lines have "linux" in them?\nI use linux\nmac is nice\nlinux is free\nwindows too',
        expect_tool="oap_grep", expect_in_output=["linux"]))
    tests.append(TestCase("grep-029", "grep",
        'return lines from this text that contain "urgent":\nlow priority\nurgent: fix now\nmedium priority\nurgent: deploy',
        expect_tool="oap_grep", expect_in_output=["urgent"]))
    tests.append(TestCase("grep-030", "grep",
        'match "v[0-9]" in:\nv1.0\nrelease\nv2.3\nbeta',
        expect_tool="oap_grep", expect_in_output=["v1", "v2"],
        allow_no_tool=True))

    # Edge cases
    tests.append(TestCase("grep-031", "grep",
        'find empty-looking lines — search for "^$" in:\nfoo\n\nbar\n\nbaz',
        expect_tool="oap_grep",
        allow_no_tool=True))
    tests.append(TestCase("grep-032", "grep",
        'search this server log for "timeout":\n[10:00] connected\n[10:01] timeout\n[10:02] retry\n[10:03] timeout',
        expect_tool="oap_grep", expect_in_output=["timeout"]))
    tests.append(TestCase("grep-033", "grep",
        'find "404" in these HTTP status codes:\n200\n301\n404\n500\n404',
        expect_tool="oap_grep", expect_in_output=["404"]))
    tests.append(TestCase("grep-034", "grep",
        'look for "price" in:\nname: widget\nprice: 9.99\ncolor: blue\nprice: 12.50',
        expect_tool="oap_grep", expect_in_output=["price"]))
    tests.append(TestCase("grep-035", "grep",
        'search for tab-separated fields containing "admin" in:\nuser\tadmin\nuser\tguest\nuser\tadmin',
        expect_tool="oap_grep", expect_in_output=["admin"]))

    # ===== WC (25 tests) =====

    # Semantic matching
    tests.append(TestCase("wc-001", "wc",
        'count the lines in:\none\ntwo\nthree\nfour\nfive',
        expect_tool="oap_wc", expect_in_output=["5"]))
    tests.append(TestCase("wc-002", "wc",
        'how many lines are in this text?\nalpha\nbeta\ngamma',
        expect_tool="oap_wc", expect_in_output=["3"]))
    tests.append(TestCase("wc-003", "wc",
        'count words in: the quick brown fox jumps over the lazy dog',
        expect_tool="oap_wc", expect_in_output=["9"]))
    tests.append(TestCase("wc-004", "wc",
        'how many words are there in: hello world foo bar baz',
        expect_tool="oap_wc", expect_in_output=["5"]))
    tests.append(TestCase("wc-005", "wc",
        'tell me the line count of:\nline1\nline2\nline3\nline4\nline5\nline6\nline7',
        expect_tool="oap_wc", expect_in_output=["7"]))
    tests.append(TestCase("wc-006", "wc",
        'what is the word count of: one two three four',
        expect_tool="oap_wc", expect_in_output=["4"]))
    tests.append(TestCase("wc-007", "wc",
        'measure the size of this text in lines:\na\nb\nc\nd\ne\nf\ng\nh\ni\nj',
        expect_tool="oap_wc", expect_in_output=["10"]))
    tests.append(TestCase("wc-008", "wc",
        'how long is this list?\nitem1\nitem2\nitem3',
        expect_tool="oap_wc", expect_in_output=["3"],
        allow_no_tool=True))

    # Invocation correctness
    tests.append(TestCase("wc-009", "wc",
        'count just the number of lines in:\nfoo\nbar\nbaz',
        expect_tool="oap_wc", expect_in_output=["3"]))
    tests.append(TestCase("wc-010", "wc",
        'give me line, word, and character counts for: hello world',
        expect_tool="oap_wc"))
    tests.append(TestCase("wc-011", "wc",
        'count the number of words in:\nthe quick\nbrown fox\njumps over',
        expect_tool="oap_wc", expect_in_output=["6"]))
    tests.append(TestCase("wc-012", "wc",
        'how many lines in:\nserver1\nserver2\nserver3\nserver4\nserver5',
        expect_tool="oap_wc", expect_in_output=["5"]))

    # Execution validation
    tests.append(TestCase("wc-013", "wc",
        'count lines in:\na',
        expect_tool="oap_wc", expect_in_output=["1"]))
    tests.append(TestCase("wc-014", "wc",
        'word count of: one',
        expect_tool="oap_wc", expect_in_output=["1"]))
    tests.append(TestCase("wc-015", "wc",
        'count the words in this sentence: I have exactly six words here',
        expect_tool="oap_wc", expect_in_output=["6"],
        allow_no_tool=True))
    tests.append(TestCase("wc-016", "wc",
        'how many lines?\nrow1\nrow2\nrow3\nrow4\nrow5\nrow6\nrow7\nrow8',
        expect_tool="oap_wc", expect_in_output=["8"]))
    tests.append(TestCase("wc-017", "wc",
        'count words in: a b c d e f g h i j',
        expect_tool="oap_wc", expect_in_output=["10"]))
    tests.append(TestCase("wc-018", "wc",
        'number of lines in:\nfirst\nsecond',
        expect_tool="oap_wc", expect_in_output=["2"]))
    tests.append(TestCase("wc-019", "wc",
        'how many lines are there in:\napple\nbanana\ncherry\ndate',
        expect_tool="oap_wc", expect_in_output=["4"]))
    tests.append(TestCase("wc-020", "wc",
        'count lines:\none\ntwo\nthree',
        expect_tool="oap_wc", expect_in_output=["3"]))
    tests.append(TestCase("wc-021", "wc",
        'tell me the word count: the cat sat on the mat',
        expect_tool="oap_wc", expect_in_output=["6"]))
    tests.append(TestCase("wc-022", "wc",
        'how many lines in this data?\nx\ny\nz',
        expect_tool="oap_wc", expect_in_output=["3"]))
    tests.append(TestCase("wc-023", "wc",
        'count entries in this list:\ntask1\ntask2\ntask3\ntask4\ntask5\ntask6',
        expect_tool="oap_wc", expect_in_output=["6"],
        allow_alternatives=["oap_grep"]))
    tests.append(TestCase("wc-024", "wc",
        'number of words in: the rain in spain falls mainly on the plain',
        expect_tool="oap_wc", expect_in_output=["9"]))
    tests.append(TestCase("wc-025", "wc",
        'give me the line count for:\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12',
        expect_tool="oap_wc", expect_in_output=["12"]))

    # ===== JQ (35 tests) =====

    # Semantic matching
    tests.append(TestCase("jq-001", "jq",
        'extract the "name" field from: {"name": "Alice", "age": 30}',
        expect_tool="oap_jq", expect_in_output=["Alice"]))
    tests.append(TestCase("jq-002", "jq",
        'get the value of "status" from this JSON: {"status": "active", "id": 42}',
        expect_tool="oap_jq", expect_in_output=["active"]))
    tests.append(TestCase("jq-003", "jq",
        'parse this JSON and return the "city" field: {"city": "Tokyo", "country": "Japan"}',
        expect_tool="oap_jq", expect_in_output=["Tokyo"]))
    tests.append(TestCase("jq-004", "jq",
        'what is the "version" in: {"version": "2.1.0", "stable": true}',
        expect_tool="oap_jq", expect_in_output=["2.1.0"]))
    tests.append(TestCase("jq-005", "jq",
        'extract the title from: {"title": "Hello World", "body": "content here"}',
        expect_tool="oap_jq", expect_in_output=["Hello World"]))
    tests.append(TestCase("jq-006", "jq",
        'read the "host" value from: {"host": "example.com", "port": 443}',
        expect_tool="oap_jq", expect_in_output=["example.com"]))
    tests.append(TestCase("jq-007", "jq",
        'pull out "email" from this JSON: {"name": "Bob", "email": "bob@test.com"}',
        expect_tool="oap_jq", expect_in_output=["bob@test.com"]))
    tests.append(TestCase("jq-008", "jq",
        'I have JSON {"color": "red", "size": "large"} — what is the color?',
        expect_tool="oap_jq", expect_in_output=["red"]))

    # Array operations
    tests.append(TestCase("jq-009", "jq",
        'get the first element from: [10, 20, 30, 40]',
        expect_tool="oap_jq", expect_in_output=["10"]))
    tests.append(TestCase("jq-010", "jq",
        'how many items in this JSON array: [1, 2, 3, 4, 5]',
        expect_tool="oap_jq", expect_in_output=["5"]))
    tests.append(TestCase("jq-011", "jq",
        'list all names from: [{"name": "Alice"}, {"name": "Bob"}, {"name": "Carol"}]',
        expect_tool="oap_jq", expect_in_output=["Alice", "Bob", "Carol"]))
    tests.append(TestCase("jq-012", "jq",
        'get the last element from: ["a", "b", "c", "d"]',
        expect_tool="oap_jq", expect_in_output=["d"]))
    tests.append(TestCase("jq-013", "jq",
        'extract all "id" values from: [{"id": 1}, {"id": 2}, {"id": 3}]',
        expect_tool="oap_jq", expect_in_output=["1", "2", "3"]))

    # Filter and transform
    tests.append(TestCase("jq-014", "jq",
        'get the keys of: {"name": "test", "version": "1.0", "license": "MIT"}',
        expect_tool="oap_jq", expect_in_output=["name", "version", "license"]))
    tests.append(TestCase("jq-015", "jq",
        'count the keys in: {"a": 1, "b": 2, "c": 3, "d": 4}',
        expect_tool="oap_jq", expect_in_output=["4"]))
    tests.append(TestCase("jq-016", "jq",
        'extract nested field "address.city" from: {"name": "Test", "address": {"city": "Paris", "zip": "75001"}}',
        expect_tool="oap_jq", expect_in_output=["Paris"]))
    tests.append(TestCase("jq-017", "jq",
        'get "config.debug" from: {"config": {"debug": true, "verbose": false}}',
        expect_tool="oap_jq", expect_in_output=["true"]))
    tests.append(TestCase("jq-018", "jq",
        'filter items where status is "active" from: [{"name":"A","status":"active"},{"name":"B","status":"inactive"},{"name":"C","status":"active"}]',
        expect_tool="oap_jq", expect_in_output=["A"],
        allow_no_tool=True))

    # Pipes and complex expressions
    tests.append(TestCase("jq-019", "jq",
        'get names sorted alphabetically from: [{"name":"Charlie"},{"name":"Alice"},{"name":"Bob"}]',
        expect_tool="oap_jq", expect_in_output=["Alice"],
        allow_no_tool=True))
    tests.append(TestCase("jq-020", "jq",
        'extract all "type" values from: [{"type":"book"},{"type":"dvd"},{"type":"book"}]',
        expect_tool="oap_jq", expect_in_output=["book", "dvd"]))
    tests.append(TestCase("jq-021", "jq",
        'get the length of this array: ["x","y","z"]',
        expect_tool="oap_jq", expect_in_output=["3"]))
    tests.append(TestCase("jq-022", "jq",
        'transform {"first":"John","last":"Doe"} to get the full name by joining first and last',
        expect_tool="oap_jq", expect_in_output=["John"],
        allow_no_tool=True))

    # More field extractions
    tests.append(TestCase("jq-023", "jq",
        'what is the "price" in: {"item": "book", "price": 19.99}',
        expect_tool="oap_jq", expect_in_output=["19.99"]))
    tests.append(TestCase("jq-024", "jq",
        'get "database.host" from: {"database": {"host": "db.local", "port": 5432}}',
        expect_tool="oap_jq", expect_in_output=["db.local"]))
    tests.append(TestCase("jq-025", "jq",
        'extract the "message" from: {"code": 200, "message": "OK"}',
        expect_tool="oap_jq", expect_in_output=["OK"]))
    tests.append(TestCase("jq-026", "jq",
        'parse {"users": [{"name": "A"}, {"name": "B"}]} and get all user names',
        expect_tool="oap_jq", expect_in_output=["A", "B"]))
    tests.append(TestCase("jq-027", "jq",
        'from {"a":1,"b":2,"c":3} get the value of key "b"',
        expect_tool="oap_jq", expect_in_output=["2"]))
    tests.append(TestCase("jq-028", "jq",
        'extract "settings.theme" from: {"settings":{"theme":"dark","lang":"en"}}',
        expect_tool="oap_jq", expect_in_output=["dark"]))
    tests.append(TestCase("jq-029", "jq",
        'get all values from: {"x": 10, "y": 20, "z": 30}',
        expect_tool="oap_jq", expect_in_output=["10", "20", "30"],
        allow_no_tool=True))
    tests.append(TestCase("jq-030", "jq",
        'how many objects in: [{"a":1},{"a":2},{"a":3},{"a":4},{"a":5},{"a":6},{"a":7}]',
        expect_tool="oap_jq", expect_in_output=["7"]))

    # Edge cases
    tests.append(TestCase("jq-031", "jq",
        'pretty-print this JSON: {"compact":true,"data":[1,2,3]}',
        expect_tool="oap_jq",
        allow_no_tool=True))
    tests.append(TestCase("jq-032", "jq",
        'check if "enabled" is true in: {"enabled": false, "name": "test"}',
        expect_tool="oap_jq", expect_in_output=["false"]))
    tests.append(TestCase("jq-033", "jq",
        'get second element from: ["first", "second", "third"]',
        expect_tool="oap_jq", expect_in_output=["second"]))
    tests.append(TestCase("jq-034", "jq",
        'extract "error.code" from: {"error": {"code": 404, "msg": "not found"}}',
        expect_tool="oap_jq", expect_in_output=["404"]))
    tests.append(TestCase("jq-035", "jq",
        'get the "count" from: {"count": 42, "page": 1}',
        expect_tool="oap_jq", expect_in_output=["42"]))

    # ===== DATE (25 tests) =====

    # Semantic matching
    tests.append(TestCase("date-001", "date",
        'what is the current date?',
        expect_tool="oap_date"))
    tests.append(TestCase("date-002", "date",
        'what time is it right now?',
        expect_tool="oap_date"))
    tests.append(TestCase("date-003", "date",
        'tell me today\'s date',
        expect_tool="oap_date"))
    tests.append(TestCase("date-004", "date",
        'what day of the week is it?',
        expect_tool="oap_date"))
    tests.append(TestCase("date-005", "date",
        'show me the current date and time',
        expect_tool="oap_date"))
    tests.append(TestCase("date-006", "date",
        'what is the current time?',
        expect_tool="oap_date"))
    tests.append(TestCase("date-007", "date",
        'display the date',
        expect_tool="oap_date"))
    tests.append(TestCase("date-008", "date",
        'current timestamp please',
        expect_tool="oap_date"))

    # Format strings
    tests.append(TestCase("date-009", "date",
        'show the current date in YYYY-MM-DD format',
        expect_tool="oap_date"))
    tests.append(TestCase("date-010", "date",
        'what is the current unix timestamp?',
        expect_tool="oap_date"))
    tests.append(TestCase("date-011", "date",
        'show the current year',
        expect_tool="oap_date", expect_in_output=["202"]))
    tests.append(TestCase("date-012", "date",
        'what month is it?',
        expect_tool="oap_date"))
    tests.append(TestCase("date-013", "date",
        'display the current hour and minute',
        expect_tool="oap_date"))
    tests.append(TestCase("date-014", "date",
        'show date in ISO 8601 format',
        expect_tool="oap_date"))
    tests.append(TestCase("date-015", "date",
        'what is the current epoch time in seconds?',
        expect_tool="oap_date"))

    # Varied phrasings
    tests.append(TestCase("date-016", "date",
        'give me the date',
        expect_tool="oap_date"))
    tests.append(TestCase("date-017", "date",
        'print the current date',
        expect_tool="oap_date"))
    tests.append(TestCase("date-018", "date",
        'I need to know what day it is',
        expect_tool="oap_date"))
    tests.append(TestCase("date-019", "date",
        'what is today?',
        expect_tool="oap_date",
        allow_no_tool=True))
    tests.append(TestCase("date-020", "date",
        'show current UTC time',
        expect_tool="oap_date"))
    tests.append(TestCase("date-021", "date",
        'date and time right now',
        expect_tool="oap_date"))
    tests.append(TestCase("date-022", "date",
        'get the current date in a readable format',
        expect_tool="oap_date"))
    tests.append(TestCase("date-023", "date",
        'what day of the month is it?',
        expect_tool="oap_date"))
    tests.append(TestCase("date-024", "date",
        'show the full date with day name',
        expect_tool="oap_date"))
    tests.append(TestCase("date-025", "date",
        'whats the time',
        expect_tool="oap_date"))

    # ===== BC (25 tests) =====

    # Semantic matching
    tests.append(TestCase("bc-001", "bc",
        'calculate 42 + 17',
        expect_tool="oap_bc", expect_in_output=["59"]))
    tests.append(TestCase("bc-002", "bc",
        'what is 100 - 37?',
        expect_tool="oap_bc", expect_in_output=["63"]))
    tests.append(TestCase("bc-003", "bc",
        'multiply 12 by 8',
        expect_tool="oap_bc", expect_in_output=["96"]))
    tests.append(TestCase("bc-004", "bc",
        'divide 144 by 12',
        expect_tool="oap_bc", expect_in_output=["12"]))
    tests.append(TestCase("bc-005", "bc",
        'compute 2 to the power of 10',
        expect_tool="oap_bc", expect_in_output=["1024"]))
    tests.append(TestCase("bc-006", "bc",
        'what is 7 * 6?',
        expect_tool="oap_bc", expect_in_output=["42"]))
    tests.append(TestCase("bc-007", "bc",
        'evaluate 999 + 1',
        expect_tool="oap_bc", expect_in_output=["1000"]))
    tests.append(TestCase("bc-008", "bc",
        'what is 256 / 16?',
        expect_tool="oap_bc", expect_in_output=["16"]))

    # Precision and functions
    tests.append(TestCase("bc-009", "bc",
        'calculate 1 / 3 with 4 decimal places',
        expect_tool="oap_bc", expect_in_output=["3333"],
        allow_no_tool=True))
    tests.append(TestCase("bc-010", "bc",
        'what is the square root of 144?',
        expect_tool="oap_bc", expect_in_output=["12"]))
    tests.append(TestCase("bc-011", "bc",
        'compute 15 % 4 (modulo)',
        expect_tool="oap_bc", expect_in_output=["3"]))
    tests.append(TestCase("bc-012", "bc",
        'what is 3^4?',
        expect_tool="oap_bc", expect_in_output=["81"]))
    tests.append(TestCase("bc-013", "bc",
        'evaluate (10 + 5) * 3',
        expect_tool="oap_bc", expect_in_output=["45"]))

    # Unit conversions and practical math
    tests.append(TestCase("bc-014", "bc",
        'convert 100 fahrenheit to celsius: compute (100 - 32) * 5 / 9',
        expect_tool="oap_bc", expect_in_output=["37"],
        allow_no_tool=True))
    tests.append(TestCase("bc-015", "bc",
        'how many seconds in a day? calculate 24 * 60 * 60',
        expect_tool="oap_bc", expect_in_output=["86400"]))
    tests.append(TestCase("bc-016", "bc",
        'compute 1000 * 1.08 for 8% markup',
        expect_tool="oap_bc", expect_in_output=["1080"]))
    tests.append(TestCase("bc-017", "bc",
        'what is 50 * 50?',
        expect_tool="oap_bc", expect_in_output=["2500"]))
    tests.append(TestCase("bc-018", "bc",
        'calculate 10! which is 10*9*8*7*6*5*4*3*2*1',
        expect_tool="oap_bc", expect_in_output=["3628800"],
        allow_no_tool=True))

    # More arithmetic
    tests.append(TestCase("bc-019", "bc",
        'add 123 and 456',
        expect_tool="oap_bc", expect_in_output=["579"]))
    tests.append(TestCase("bc-020", "bc",
        'subtract 50 from 200',
        expect_tool="oap_bc", expect_in_output=["150"]))
    tests.append(TestCase("bc-021", "bc",
        'what is 99 * 99?',
        expect_tool="oap_bc", expect_in_output=["9801"]))
    tests.append(TestCase("bc-022", "bc",
        'compute 2^16',
        expect_tool="oap_bc", expect_in_output=["65536"]))
    tests.append(TestCase("bc-023", "bc",
        'divide 1000 by 8',
        expect_tool="oap_bc", expect_in_output=["125"]))
    tests.append(TestCase("bc-024", "bc",
        'what is 111 + 222 + 333?',
        expect_tool="oap_bc", expect_in_output=["666"]))
    tests.append(TestCase("bc-025", "bc",
        'calculate 5 * 5 * 5',
        expect_tool="oap_bc", expect_in_output=["125"]))

    # ===== APROPOS (20 tests) =====

    # Semantic matching — keyword discovery
    tests.append(TestCase("apropos-001", "apropos",
        'find commands related to "compression"',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-002", "apropos",
        'what commands are available for working with archives?',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"],
        allow_no_tool=True))
    tests.append(TestCase("apropos-003", "apropos",
        'search for commands related to "network"',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-004", "apropos",
        'discover Unix commands for text processing',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"],
        allow_no_tool=True))
    tests.append(TestCase("apropos-005", "apropos",
        'what tools exist for file compression on this system?',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"],
        allow_no_tool=True))
    tests.append(TestCase("apropos-006", "apropos",
        'find commands for sorting data',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-007", "apropos",
        'look up commands related to "disk"',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-008", "apropos",
        'search for commands about "password"',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-009", "apropos",
        'what commands handle "encryption" on this system?',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"],
        allow_no_tool=True))
    tests.append(TestCase("apropos-010", "apropos",
        'find tools for working with CSV files',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man", "oap_jq"],
        allow_no_tool=True))

    # Specific keyword searches
    tests.append(TestCase("apropos-011", "apropos",
        'search manual pages for "checksum" related commands',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-012", "apropos",
        'find commands matching keyword "copy"',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-013", "apropos",
        'what commands are available for "printing"?',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"],
        allow_no_tool=True))
    tests.append(TestCase("apropos-014", "apropos",
        'list Unix commands for "diff"',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-015", "apropos",
        'search for commands about "process"',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-016", "apropos",
        'discover commands for "cron" or scheduling',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"],
        allow_no_tool=True))
    tests.append(TestCase("apropos-017", "apropos",
        'find commands related to "base64"',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-018", "apropos",
        'what tools deal with "permission" on this machine?',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"],
        allow_no_tool=True))
    tests.append(TestCase("apropos-019", "apropos",
        'search for commands about "hash"',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man"]))
    tests.append(TestCase("apropos-020", "apropos",
        'find tools for "hexadecimal" conversion',
        expect_tool="oap_apropos",
        allow_alternatives=["oap_man", "oap_bc"],
        allow_no_tool=True))

    # ===== MAN (15 tests) =====

    # Semantic matching
    tests.append(TestCase("man-001", "man",
        'show me the manual page for the grep command',
        expect_tool="oap_man", expect_in_output=["grep"],
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-002", "man",
        'read the documentation for the ls command',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-003", "man",
        'what are the options for the tar command? show its man page',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-004", "man",
        'display the manual for sed',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-005", "man",
        'I need to read the man page for awk',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))

    # Specific command lookups
    tests.append(TestCase("man-006", "man",
        'how do I use the find command? show me its manual',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-007", "man",
        'show the documentation for curl',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-008", "man",
        'what does the chmod command do? show its man page',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-009", "man",
        'read the manual for the sort command',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-010", "man",
        'show me the man page for cut',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))

    # Varied phrasings
    tests.append(TestCase("man-011", "man",
        'look up the manual for diff',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-012", "man",
        'get the man page for head',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-013", "man",
        'what flags does rsync accept? show its documentation',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-014", "man",
        'pull up the man page for xargs',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))
    tests.append(TestCase("man-015", "man",
        'display the manual page for tee',
        expect_tool="oap_man",
        allow_alternatives=["oap_apropos"]))

    # ===== CROSS-TOOL (10 tests) =====

    tests.append(TestCase("cross-001", "cross",
        'count how many lines contain "error" in:\ninfo ok\nerror bad\ninfo ok\nerror worse\ninfo fine',
        expect_tool=["oap_grep", "oap_wc"],
        allow_alternatives=["oap_grep", "oap_wc"]))
    tests.append(TestCase("cross-002", "cross",
        'search for "sort" related commands and show the manual for the best match',
        expect_tool=["oap_apropos", "oap_man"],
        allow_alternatives=["oap_apropos", "oap_man"]))
    tests.append(TestCase("cross-003", "cross",
        'what is 2+2 and what day is it?',
        expect_tool=["oap_bc", "oap_date"],
        allow_alternatives=["oap_bc", "oap_date"],
        allow_no_tool=True))
    tests.append(TestCase("cross-004", "cross",
        'find lines with numbers in:\nabc\n123\ndef\n456\nand count them',
        expect_tool=["oap_grep", "oap_wc"],
        allow_alternatives=["oap_grep", "oap_wc"]))
    tests.append(TestCase("cross-005", "cross",
        'get the "count" from {"count": 5} and multiply it by 10',
        expect_tool=["oap_jq", "oap_bc"],
        allow_alternatives=["oap_jq", "oap_bc"],
        allow_no_tool=True))
    tests.append(TestCase("cross-006", "cross",
        'look up what "wc" does — show its manual',
        expect_tool=["oap_man", "oap_apropos"],
        allow_alternatives=["oap_man", "oap_apropos"]))
    tests.append(TestCase("cross-007", "cross",
        'how many words in this JSON field? get "text" from {"text": "the quick brown fox"} then count the words',
        expect_tool=["oap_jq", "oap_wc"],
        allow_alternatives=["oap_jq", "oap_wc"],
        allow_no_tool=True))
    tests.append(TestCase("cross-008", "cross",
        'search the text for "foo" and tell me how many matches:\nfoo bar\nbaz foo\nqux',
        expect_tool=["oap_grep", "oap_wc"],
        allow_alternatives=["oap_grep", "oap_wc"]))
    tests.append(TestCase("cross-009", "cross",
        'find commands related to "calendar" and show the date',
        expect_tool=["oap_apropos", "oap_date"],
        allow_alternatives=["oap_apropos", "oap_date"]))
    tests.append(TestCase("cross-010", "cross",
        'parse {"items": 3} to get the count, then compute 3 * 7',
        expect_tool=["oap_jq", "oap_bc"],
        allow_alternatives=["oap_jq", "oap_bc"],
        allow_no_tool=True))

    # ===== NEGATIVE (10 tests) =====

    tests.append(TestCase("neg-001", "negative",
        'send an email to alice@example.com',
        expect_tool=None,
        allow_no_tool=True))
    tests.append(TestCase("neg-002", "negative",
        'compile this C program: #include <stdio.h>\nint main() { return 0; }',
        expect_tool=None,
        allow_no_tool=True))
    tests.append(TestCase("neg-003", "negative",
        'play a song called "Bohemian Rhapsody"',
        expect_tool=None,
        allow_no_tool=True))
    tests.append(TestCase("neg-004", "negative",
        'download the file at https://example.com/data.zip',
        expect_tool=None,
        allow_no_tool=True))
    tests.append(TestCase("neg-005", "negative",
        'open a web browser and go to google.com',
        expect_tool=None,
        allow_no_tool=True))
    tests.append(TestCase("neg-006", "negative",
        'take a screenshot of my desktop',
        expect_tool=None,
        allow_no_tool=True))
    tests.append(TestCase("neg-007", "negative",
        'create a new directory called "project"',
        expect_tool=None,
        allow_no_tool=True))
    tests.append(TestCase("neg-008", "negative",
        'list all running docker containers',
        expect_tool=None,
        allow_no_tool=True))
    tests.append(TestCase("neg-009", "negative",
        'restart the nginx service',
        expect_tool=None,
        allow_no_tool=True))
    tests.append(TestCase("neg-010", "negative",
        'translate "hello" to French',
        expect_tool=None,
        allow_no_tool=True))

    return tests


# ---------------------------------------------------------------------------
# Cache tests (behind --include-cache-tests)
# ---------------------------------------------------------------------------

def build_cache_tests() -> list[TestCase]:
    """Cache test cases that require --token and mutate state."""
    return [
        TestCase("cache-001", "cache",
            'calculate 7 * 8',
            expect_tool="oap_bc", expect_in_output=["56"]),
        TestCase("cache-002", "cache",
            'calculate 7 * 8',
            expect_tool="oap_bc", expect_in_output=["56"]),
    ]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def run_tests(
    tests: list[TestCase],
    base_url: str,
    model: str,
    timeout: float,
    fail_fast: bool,
    verbose: bool,
    dry_run: bool,
) -> list[TestResult]:
    results: list[TestResult] = []
    total = len(tests)
    start_all = time.monotonic()

    for i, tc in enumerate(tests, 1):
        if dry_run:
            print(f"[{i:3d}/{total}] {tc.id:<14s}  {tc.category:<10s}  {tc.task[:60]}")
            continue

        elapsed_so_far = time.monotonic() - start_all
        if i > 1 and results:
            avg = elapsed_so_far / (i - 1)
            eta = avg * (total - i + 1)
            eta_str = f"  ETA {format_duration(eta)}"
        else:
            eta_str = ""

        t0 = time.monotonic()
        response = send_chat(base_url, tc.task, model, timeout)
        duration = time.monotonic() - t0

        result = verify_test(tc, response, duration)
        results.append(result)

        color_fn = VERDICT_COLOR.get(result.verdict, str)
        tool_display = result.tool_called or "-"
        task_preview = tc.task.replace("\n", " ")[:50]

        line = f"[{i:3d}/{total}] {tc.id:<14s}{color_fn(result.verdict):<6s}{tool_display:<16s}{duration:5.1f}s  {dim(task_preview)}"
        if result.detail:
            line += f"  {dim('[' + result.detail + ']')}"
        print(line + eta_str)

        if verbose and result.verdict == FAIL and result.debug:
            print(dim("    Debug: " + json.dumps(result.debug, indent=2)[:500]))

        if fail_fast and result.verdict == FAIL:
            print(red("\n  Stopping: --fail-fast triggered"))
            break

    return results


def run_cache_tests(
    base_url: str,
    model: str,
    timeout: float,
    token: str,
    verbose: bool,
) -> list[TestResult]:
    """Run cache-specific tests: clear → miss → hit → verify."""
    results: list[TestResult] = []
    headers = {"X-Backend-Token": token}
    cache_tests = build_cache_tests()

    print(bold("\n  Cache Tests"))
    print("  " + "=" * 50)

    # Step 1: Find and clear any existing cache entries for our test task
    task = cache_tests[0].task
    print(dim("  Clearing existing cache entries..."))
    try:
        resp = httpx.get(
            f"{base_url}/v1/experience/records",
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code == 200:
            records = resp.json().get("records", [])
            for rec in records:
                if rec.get("intent", {}).get("raw", "") == task:
                    rid = rec["id"]
                    httpx.delete(
                        f"{base_url}/v1/experience/records/{rid}",
                        headers=headers,
                        timeout=timeout,
                    )
                    print(dim(f"  Deleted: {rid}"))
    except Exception as e:
        print(red(f"  Failed to clear cache: {e}"))
        return results

    # Step 2: First request — should be cache miss
    tc1 = cache_tests[0]
    print(f"\n  [1/2] {tc1.id}  Expecting cache miss...")
    t0 = time.monotonic()
    resp1 = send_chat(base_url, tc1.task, model, timeout)
    d1 = time.monotonic() - t0

    if resp1:
        cache_status = resp1.get("oap_experience_cache", "")
        r1 = verify_test(tc1, resp1, d1)
        if cache_status == "miss":
            print(green(f"    PASS  cache=miss  {d1:.1f}s"))
        else:
            r1 = TestResult(tc1.id, FAIL, r1.tool_called, d1, tc1.task,
                            detail=f"Expected cache miss, got '{cache_status}'")
            print(red(f"    FAIL  cache={cache_status}  {d1:.1f}s"))
        results.append(r1)
    else:
        results.append(TestResult(tc1.id, SKIP, "", d1, tc1.task, detail="No response"))
        print(red(f"    SKIP  no response"))
        return results

    # Step 3: Second request — should be cache hit
    tc2 = cache_tests[1]
    print(f"  [2/2] {tc2.id}  Expecting cache hit...")
    t0 = time.monotonic()
    resp2 = send_chat(base_url, tc2.task, model, timeout)
    d2 = time.monotonic() - t0

    if resp2:
        cache_status = resp2.get("oap_experience_cache", "")
        r2 = verify_test(tc2, resp2, d2)
        if cache_status == "hit":
            print(green(f"    PASS  cache=hit  {d2:.1f}s"))
        else:
            r2 = TestResult(tc2.id, FAIL, r2.tool_called, d2, tc2.task,
                            detail=f"Expected cache hit, got '{cache_status}'")
            print(red(f"    FAIL  cache={cache_status}  {d2:.1f}s"))
        results.append(r2)
    else:
        results.append(TestResult(tc2.id, SKIP, "", d2, tc2.task, detail="No response"))
        print(red(f"    SKIP  no response"))

    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results: list[TestResult], total_duration: float) -> None:
    if not results:
        return

    counts = {PASS: 0, SOFT: 0, WARN: 0, FAIL: 0, SKIP: 0}
    for r in results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1

    total = len(results)
    pass_soft = counts[PASS] + counts[SOFT]
    pct = (pass_soft / total * 100) if total else 0

    # Category breakdown
    categories: dict[str, dict[str, int]] = {}
    for r in results:
        # Derive category from test ID prefix
        cat = r.test_id.rsplit("-", 1)[0]
        if cat not in categories:
            categories[cat] = {PASS: 0, SOFT: 0, WARN: 0, FAIL: 0, SKIP: 0}
        categories[cat][r.verdict] = categories[cat].get(r.verdict, 0) + 1

    # Failures
    failures = [r for r in results if r.verdict == FAIL]

    print("\n" + bold("=" * 54))
    print(bold("  Discovery Test Harness — Results"))
    print(bold("=" * 54))

    color = green if pct >= 80 else yellow if pct >= 60 else red
    print(f"  Total: {total}  "
          f"Pass: {color(str(counts[PASS]))} ({counts[PASS]/total*100:.0f}%)  "
          f"Soft: {yellow(str(counts[SOFT]))}  "
          f"Warn: {yellow(str(counts[WARN]))}  "
          f"Fail: {red(str(counts[FAIL]))}  "
          f"Skip: {dim(str(counts[SKIP]))}")
    print(f"  Pass+Soft: {color(f'{pass_soft}/{total}')} ({pct:.0f}%)")
    print(f"  Duration: {format_duration(total_duration)}")

    if categories:
        print(f"\n  By category:")
        cats_sorted = sorted(categories.items())
        # Print in two columns
        items = []
        for cat, v in cats_sorted:
            cat_total = sum(v.values())
            cat_pass = v[PASS] + v[SOFT]
            cat_pct = (cat_pass / cat_total * 100) if cat_total else 0
            c = green if cat_pct >= 80 else yellow if cat_pct >= 60 else red
            items.append(f"    {cat:<11s}{c(f'{cat_pass}/{cat_total}')} ({cat_pct:.0f}%)")
        for i in range(0, len(items), 2):
            pair = items[i:i+2]
            print("  ".join(pair))

    if failures:
        print(f"\n  Failures:")
        for r in failures:
            detail = r.detail or "unknown reason"
            print(f"    {red(r.test_id)}: {detail}")

    print(bold("=" * 54))


def write_json_report(results: list[TestResult], path: str, total_duration: float) -> None:
    report = {
        "total": len(results),
        "duration_s": round(total_duration, 1),
        "verdicts": {},
        "results": [],
    }
    for r in results:
        report["verdicts"][r.verdict] = report["verdicts"].get(r.verdict, 0) + 1
        report["results"].append({
            "test_id": r.test_id,
            "verdict": r.verdict,
            "tool_called": r.tool_called,
            "duration_s": round(r.duration_s, 2),
            "task": r.task,
            "detail": r.detail,
        })

    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  JSON report written to {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OAP Discovery Test Harness — integration tests for tool bridge",
    )
    parser.add_argument("--url", default="http://localhost:8300",
                        help="Discovery API base URL (default: http://localhost:8300)")
    parser.add_argument("--model", default="qwen3t:4b",
                        help="Ollama model (default: qwen3t:4b)")
    parser.add_argument("--timeout", type=float, default=120,
                        help="Per-request timeout in seconds (default: 120)")
    parser.add_argument("--category",
                        help="Comma-separated categories to run (e.g. grep,wc)")
    parser.add_argument("--test",
                        help="Run a specific test by ID (e.g. grep-001)")
    parser.add_argument("--smoke", action="store_true",
                        help="Run only the first 10 tests")
    parser.add_argument("--dry-run", action="store_true",
                        help="List tests without executing")
    parser.add_argument("--fail-fast", action="store_true",
                        help="Stop on first FAIL verdict")
    parser.add_argument("--verbose", action="store_true",
                        help="Show full debug output on failures")
    parser.add_argument("--json",
                        help="Write JSON report to this path")
    parser.add_argument("--include-cache-tests", action="store_true",
                        help="Run cache miss/hit tests (requires --token)")
    parser.add_argument("--token",
                        help="Backend auth token (required for /health check and cache tests)")

    args = parser.parse_args()

    all_tests = build_test_cases()

    # Filter
    if args.test:
        all_tests = [t for t in all_tests if t.id == args.test]
        if not all_tests:
            print(f"No test found with ID: {args.test}", file=sys.stderr)
            sys.exit(1)
    elif args.category:
        cats = {c.strip() for c in args.category.split(",")}
        all_tests = [t for t in all_tests if t.category in cats]
        if not all_tests:
            print(f"No tests found for categories: {args.category}", file=sys.stderr)
            sys.exit(1)

    if args.smoke:
        all_tests = all_tests[:10]

    print(bold(f"  OAP Discovery Test Harness"))
    print(f"  URL: {args.url}  Model: {args.model}  Tests: {len(all_tests)}")

    if not args.dry_run:
        print(f"  Checking service health...", end=" ")
        if health_check(args.url, args.timeout, args.token):
            print(green("OK"))
        else:
            print(red("FAILED"))
            hint = " (--token required for /health auth)" if not args.token else ""
            print(f"  Cannot reach {args.url}/health{hint}", file=sys.stderr)
            sys.exit(1)

    print()

    start = time.monotonic()
    results = run_tests(
        all_tests,
        args.url,
        args.model,
        args.timeout,
        args.fail_fast,
        args.verbose,
        args.dry_run,
    )

    # Cache tests
    cache_results: list[TestResult] = []
    if args.include_cache_tests:
        if not args.token:
            print(red("\n  --include-cache-tests requires --token"), file=sys.stderr)
        else:
            cache_results = run_cache_tests(
                args.url, args.model, args.timeout, args.token, args.verbose,
            )
            results.extend(cache_results)

    total_duration = time.monotonic() - start

    if not args.dry_run:
        print_report(results, total_duration)

        if args.json:
            write_json_report(results, args.json, total_duration)

        # Exit code: 1 if >20% failures
        total = len(results)
        if total:
            fail_pct = sum(1 for r in results if r.verdict == FAIL) / total
            if fail_pct > 0.20:
                sys.exit(1)


if __name__ == "__main__":
    main()

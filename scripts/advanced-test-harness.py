#!/usr/bin/env python3
"""Advanced Test Harness — file-based, parsing, pipeline, and impossible-task tests.

Complements the Discovery Test Harness (200 inline-text tests) with tests that
exercise file path detection, complex data extraction, multi-step pipelines,
and graceful failure on impossible tasks. Uses deterministic fixture files in
/tmp/oap-test/ for exact output assertions.

Usage:
    python scripts/advanced-test-harness.py                    # run all
    python scripts/advanced-test-harness.py --category file    # filter
    python scripts/advanced-test-harness.py --test file-001    # specific test
    python scripts/advanced-test-harness.py --smoke            # first 10 only
    python scripts/advanced-test-harness.py --dry-run          # list without executing
    python scripts/advanced-test-harness.py --fail-fast        # stop on first FAIL
    python scripts/advanced-test-harness.py --verbose          # full debug on failure
    python scripts/advanced-test-harness.py --json results.json
    python scripts/advanced-test-harness.py --log advanced.jsonl
    python scripts/advanced-test-harness.py --url http://host:8300
    python scripts/advanced-test-harness.py --model qwen3:8b
    python scripts/advanced-test-harness.py --timeout 120
    python scripts/advanced-test-harness.py --keep-fixtures    # don't clean up after
    python scripts/advanced-test-harness.py --no-setup         # skip fixture creation
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXTURE_DIR = "/tmp/oap-test"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    id: str                                        # "file-001"
    category: str                                  # "file", "parse", etc.
    task: str                                      # Natural language prompt
    expect_tool: str | list[str] | None = None     # Expected tool(s), None = no tool
    expect_in_output: list[str] = field(default_factory=list)
    expect_error: bool = False
    allow_alternatives: list[str] = field(default_factory=list)
    allow_no_tool: bool = False


@dataclass
class TestResult:
    test_id: str
    verdict: str          # PASS, SOFT, WARN, FAIL, SKIP
    tool_called: str      # tool name or ""
    duration_s: float
    task: str
    detail: str = ""
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
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES: dict[str, str] = {
    "access.log": (
        '192.168.1.10 - - [01/Jan/2025:10:00:01] "GET /index.html HTTP/1.1" 200 1024\n'
        '10.0.0.5 - - [01/Jan/2025:10:00:02] "POST /api/login HTTP/1.1" 302 0\n'
        '192.168.1.10 - - [01/Jan/2025:10:00:03] "GET /style.css HTTP/1.1" 200 512\n'
        '172.16.0.1 - - [01/Jan/2025:10:00:04] "GET /about HTTP/1.1" 200 2048\n'
        '10.0.0.5 - - [01/Jan/2025:10:00:05] "GET /dashboard HTTP/1.1" 200 4096\n'
        '192.168.1.20 - - [01/Jan/2025:10:00:06] "DELETE /api/session HTTP/1.1" 204 0\n'
        '172.16.0.1 - - [01/Jan/2025:10:00:07] "POST /api/data HTTP/1.1" 201 128\n'
        '192.168.1.10 - - [01/Jan/2025:10:00:08] "GET /favicon.ico HTTP/1.1" 404 0\n'
        '10.0.0.5 - - [01/Jan/2025:10:00:09] "PUT /api/profile HTTP/1.1" 200 256\n'
        '192.168.1.20 - - [01/Jan/2025:10:00:10] "GET /index.html HTTP/1.1" 200 1024\n'
        '172.16.0.1 - - [01/Jan/2025:10:00:11] "GET /contact HTTP/1.1" 200 1536\n'
        '192.168.1.10 - - [01/Jan/2025:10:00:12] "POST /api/upload HTTP/1.1" 500 0\n'
    ),
    "app.log": (
        "[2025-01-01 10:00:01] INFO  Application started\n"
        "[2025-01-01 10:00:02] INFO  Connected to database\n"
        "[2025-01-01 10:00:03] WARN  Slow query detected (2.3s)\n"
        "[2025-01-01 10:00:04] INFO  User alice logged in\n"
        "[2025-01-01 10:00:05] ERROR Failed to send email: timeout\n"
        "[2025-01-01 10:00:06] INFO  Processing batch job\n"
        "[2025-01-01 10:00:07] WARN  Disk usage at 85%\n"
        "[2025-01-01 10:00:08] ERROR Database connection lost\n"
        "[2025-01-01 10:00:09] INFO  Reconnecting to database\n"
        "[2025-01-01 10:00:10] INFO  Connection restored\n"
        "[2025-01-01 10:00:11] WARN  Memory usage at 90%\n"
        "[2025-01-01 10:00:12] ERROR API rate limit exceeded\n"
        "[2025-01-01 10:00:13] INFO  Cache cleared\n"
        "[2025-01-01 10:00:14] WARN  SSL certificate expiring soon\n"
        "[2025-01-01 10:00:15] ERROR Null pointer exception in module X\n"
    ),
    "contacts.txt": (
        "Alice Johnson, alice@example.com, 555-0101\n"
        "Bob Smith, bob@company.org, 555-0102\n"
        "Carol Davis, 555-0103\n"
        "Dave Wilson, dave@example.com, 555-0104\n"
        "Eve Brown, eve@company.org, 555-0105\n"
        "Frank Miller, 555-0106\n"
        "Grace Lee, grace@example.com, 555-0107\n"
        "Hank Taylor, hank@company.org, 555-0108\n"
        "Iris Chen, iris@example.com, 555-0109\n"
        "Jack White, 555-0110\n"
        "Karen Black, karen@example.com, 555-0111\n"
        "Leo Green, leo@company.org, 555-0112\n"
    ),
    "data.json": json.dumps([
        {"name": "Alice", "age": 30, "city": "New York", "score": 85},
        {"name": "Bob", "age": 25, "city": "London", "score": 92},
        {"name": "Carol", "age": 35, "city": "Tokyo", "score": 78},
        {"name": "Dave", "age": 28, "city": "Paris", "score": 88},
        {"name": "Eve", "age": 32, "city": "New York", "score": 91},
        {"name": "Frank", "age": 45, "city": "London", "score": 73},
        {"name": "Grace", "age": 29, "city": "Tokyo", "score": 95},
        {"name": "Hank", "age": 38, "city": "Paris", "score": 82},
    ], indent=2) + "\n",
    "sales.csv": (
        "date,product,quantity,price\n"
        "2025-01-01,Widget,10,9.99\n"
        "2025-01-02,Gadget,5,19.99\n"
        "2025-01-03,Widget,8,9.99\n"
        "2025-01-04,Doohickey,3,29.99\n"
        "2025-01-05,Gadget,12,19.99\n"
        "2025-01-06,Widget,6,9.99\n"
        "2025-01-07,Thingamajig,2,49.99\n"
        "2025-01-08,Doohickey,7,29.99\n"
        "2025-01-09,Gadget,4,19.99\n"
        "2025-01-10,Widget,15,9.99\n"
    ),
    "numbers.txt": (
        "42\n"
        "3.14\n"
        "-7\n"
        "100\n"
        "0\n"
        "2.718\n"
        "-15\n"
        "99\n"
        "0.5\n"
        "1000\n"
        "-3.14\n"
        "7\n"
    ),
    "code.py": (
        "#!/usr/bin/env python3\n"
        '"""Sample module for testing."""\n'
        "\n"
        "import os\n"
        "import sys\n"
        "\n"
        "# TODO: add logging support\n"
        "# FIXME: handle unicode properly\n"
        "\n"
        "def process_data(items):\n"
        '    """Process a list of items."""\n'
        "    result = []\n"
        "    for item in items:\n"
        "        result.append(item.strip().lower())\n"
        "    return result\n"
        "\n"
        "# TODO: implement caching\n"
        "# FIXME: error handling missing\n"
        "\n"
        "def format_output(data, separator=','):\n"
        '    """Format data as delimited string."""\n'
        "    return separator.join(str(d) for d in data)\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    items = sys.argv[1:]\n"
        "    print(format_output(process_data(items)))\n"
    ),
    "config.ini": (
        "[database]\n"
        "host=localhost\n"
        "port=5432\n"
        "name=myapp\n"
        "user=admin\n"
        "password=secret123\n"
        "\n"
        "[server]\n"
        "host=0.0.0.0\n"
        "port=8080\n"
        "debug=true\n"
        "workers=4\n"
        "\n"
        "[logging]\n"
        "level=INFO\n"
        "file=/var/log/app.log\n"
        "rotate=daily\n"
    ),
}


def setup_fixtures() -> None:
    """Create fixture files in /tmp/oap-test/."""
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    for name, content in FIXTURES.items():
        path = os.path.join(FIXTURE_DIR, name)
        with open(path, "w") as f:
            f.write(content)
    print(f"  Fixtures created in {FIXTURE_DIR}/ ({len(FIXTURES)} files)")


def teardown_fixtures() -> None:
    """Remove fixture directory."""
    if os.path.exists(FIXTURE_DIR):
        shutil.rmtree(FIXTURE_DIR)
        print(f"  Fixtures removed: {FIXTURE_DIR}/")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def health_check(base_url: str, timeout: float, token: str | None = None) -> bool:
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
    no_cache: bool = False,
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
        "oap_no_cache": no_cache,
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
    """Apply output-first verdict logic to a single test response.

    Core principle: if the task produces correct output, the tool identity
    is secondary. A correct result via an unexpected tool is SOFT, not FAIL.
    """

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
    if expected:
        expected.append("oap_exec")
    primary_tool = tools_called[0] if tools_called else ""

    # Pre-compute output correctness and tool identity
    output_correct = True
    missing_output = ""
    if tc.expect_in_output:
        for substr in tc.expect_in_output:
            if substr not in combined:
                output_correct = False
                missing_output = substr
                break

    has_error = any(r.startswith("Error") for r in tool_results)
    matched_expected = any(t in expected for t in tools_called) if expected else False
    matched_alt = any(t in tc.allow_alternatives for t in tools_called)

    # --- Verdict logic (output-first) ---

    # 1. No tool called
    if not tools_called:
        if not expected:
            # Negative test — expected no tool
            return TestResult(tc.id, PASS, "", duration_s, tc.task, debug=debug_info)
        if output_correct and tc.expect_in_output:
            return TestResult(tc.id, SOFT, "", duration_s, tc.task,
                              detail="Correct output without tool call", debug=debug_info)
        if message_content.strip():
            return TestResult(tc.id, WARN, "", duration_s, tc.task,
                              detail=f"LLM answered directly (expected {expected})", debug=debug_info)
        return TestResult(tc.id, FAIL, "", duration_s, tc.task,
                          detail=f"Expected {expected}, no tool called", debug=debug_info)

    # 2. Expected error tests
    if tc.expect_error:
        if has_error:
            if matched_expected:
                return TestResult(tc.id, PASS, primary_tool, duration_s, tc.task, debug=debug_info)
            return TestResult(tc.id, SOFT, primary_tool, duration_s, tc.task,
                              detail=f"Expected error via {primary_tool} (expected {expected})", debug=debug_info)
        return TestResult(tc.id, FAIL, primary_tool, duration_s, tc.task,
                          detail="Expected error but got success", debug=debug_info)

    # 3. Unexpected error — fail only if output didn't recover
    if has_error and not output_correct:
        return TestResult(tc.id, FAIL, primary_tool, duration_s, tc.task,
                          detail="Unexpected error in tool result", debug=debug_info)

    # 4. Negative test — expected no tool but one was called
    if not expected:
        return TestResult(tc.id, FAIL, primary_tool, duration_s, tc.task,
                          detail=f"Expected no tool, got {primary_tool}", debug=debug_info)

    # 5. Output correct — tool identity is secondary
    if output_correct and tc.expect_in_output:
        if matched_expected:
            return TestResult(tc.id, PASS, primary_tool, duration_s, tc.task, debug=debug_info)
        if matched_alt:
            return TestResult(tc.id, SOFT, primary_tool, duration_s, tc.task,
                              detail=f"Correct output via alternative {primary_tool}", debug=debug_info)
        return TestResult(tc.id, SOFT, primary_tool, duration_s, tc.task,
                          detail=f"Correct output via {primary_tool} (expected {expected})", debug=debug_info)

    # 6. No output to verify — fall back to tool identity
    if not tc.expect_in_output:
        if matched_expected:
            return TestResult(tc.id, PASS, primary_tool, duration_s, tc.task, debug=debug_info)
        if matched_alt:
            return TestResult(tc.id, SOFT, primary_tool, duration_s, tc.task,
                              detail=f"Alternative tool {primary_tool} used", debug=debug_info)
        return TestResult(tc.id, WARN, primary_tool, duration_s, tc.task,
                          detail=f"Got {primary_tool}, expected {expected} (no output check)", debug=debug_info)

    # 7. Output incorrect
    if matched_expected or matched_alt:
        return TestResult(tc.id, FAIL, primary_tool, duration_s, tc.task,
                          detail=f'Expected output "{missing_output}" not found', debug=debug_info)
    return TestResult(tc.id, FAIL, primary_tool, duration_s, tc.task,
                      detail=f'Wrong tool {primary_tool}, expected output "{missing_output}" not found', debug=debug_info)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

def _fp(name: str) -> str:
    """Return full fixture path."""
    return f"{FIXTURE_DIR}/{name}"


def build_test_cases() -> list[TestCase]:
    """Return all ~60 test cases across file, parse, pipeline, impossible."""
    tests: list[TestCase] = []

    # ===== FILE (15 tests) =====
    # File path detection → oap_exec with file args, basic single-tool operations

    tests.append(TestCase("file-001", "file",
        f"count the number of lines in {_fp('access.log')}",
        expect_tool="oap_exec", expect_in_output=["12"]))
    tests.append(TestCase("file-002", "file",
        f"show the contents of {_fp('numbers.txt')}",
        expect_tool="oap_exec"))
    tests.append(TestCase("file-003", "file",
        f"find all lines containing ERROR in {_fp('app.log')}",
        expect_tool="oap_exec", expect_in_output=["Failed to send email", "Database connection lost"]))
    tests.append(TestCase("file-004", "file",
        f"count the number of words in {_fp('contacts.txt')}",
        expect_tool="oap_exec"))
    tests.append(TestCase("file-005", "file",
        f"extract all email addresses from {_fp('contacts.txt')}",
        expect_tool="oap_exec", expect_in_output=["alice@example.com", "bob@company.org"]))
    tests.append(TestCase("file-006", "file",
        f"show the first 3 lines of {_fp('app.log')}",
        expect_tool="oap_exec", expect_in_output=["Application started", "Connected to database"]))
    tests.append(TestCase("file-007", "file",
        f"show the last 3 lines of {_fp('app.log')}",
        expect_tool="oap_exec", expect_in_output=["Cache cleared", "Null pointer exception"]))
    tests.append(TestCase("file-008", "file",
        f"search for lines containing 'Widget' in {_fp('sales.csv')}",
        expect_tool="oap_exec", expect_in_output=["Widget"]))
    tests.append(TestCase("file-009", "file",
        f"count how many lines in {_fp('code.py')} contain TODO",
        expect_tool="oap_exec", expect_in_output=["2"]))
    tests.append(TestCase("file-010", "file",
        f"find all lines with FIXME in {_fp('code.py')}",
        expect_tool="oap_exec", expect_in_output=["FIXME"]))
    tests.append(TestCase("file-011", "file",
        f"show lines containing 'host' in {_fp('config.ini')}",
        expect_tool="oap_exec", expect_in_output=["localhost", "0.0.0.0"]))
    tests.append(TestCase("file-012", "file",
        f"count the number of lines in {_fp('data.json')}",
        expect_tool="oap_exec"))
    tests.append(TestCase("file-013", "file",
        f"search for 'password' in {_fp('config.ini')}",
        expect_tool="oap_exec", expect_in_output=["secret123"]))
    tests.append(TestCase("file-014", "file",
        f"display all lines containing '500' in {_fp('access.log')}",
        expect_tool="oap_exec", expect_in_output=["500"]))
    tests.append(TestCase("file-015", "file",
        f"find lines with negative numbers in {_fp('numbers.txt')}",
        expect_tool="oap_exec", expect_in_output=["-7", "-15"]))

    # ===== PARSE (15 tests) =====
    # Complex data extraction: regex, jq filters, awk on fixture files

    tests.append(TestCase("parse-001", "parse",
        f"extract all unique IP addresses from {_fp('access.log')}",
        expect_tool="oap_exec", expect_in_output=["192.168.1.10", "10.0.0.5", "172.16.0.1", "192.168.1.20"]))
    tests.append(TestCase("parse-002", "parse",
        f"use jq to find the person with the highest score in {_fp('data.json')}",
        expect_tool="oap_exec", expect_in_output=["Grace"]))
    tests.append(TestCase("parse-003", "parse",
        f"extract all email addresses from {_fp('contacts.txt')} and list only the domain parts",
        expect_tool="oap_exec", expect_in_output=["example.com", "company.org"]))
    tests.append(TestCase("parse-004", "parse",
        f"use jq to list the names of everyone in New York from {_fp('data.json')}",
        expect_tool="oap_exec", expect_in_output=["Alice", "Eve"]))
    tests.append(TestCase("parse-005", "parse",
        f"extract all HTTP status codes from {_fp('access.log')}",
        expect_tool="oap_exec", expect_in_output=["200", "302", "404", "500"]))
    tests.append(TestCase("parse-006", "parse",
        f"use jq to calculate the average age from {_fp('data.json')}",
        expect_tool="oap_exec", expect_in_output=["32"],
        allow_no_tool=True))
    tests.append(TestCase("parse-007", "parse",
        f"extract the product names from {_fp('sales.csv')}, show only unique ones",
        expect_tool="oap_exec", expect_in_output=["Widget", "Gadget", "Doohickey", "Thingamajig"]))
    tests.append(TestCase("parse-008", "parse",
        f"use jq to sort the people by age in {_fp('data.json')} and show the youngest",
        expect_tool="oap_exec", expect_in_output=["Bob"]))
    tests.append(TestCase("parse-009", "parse",
        f"extract all function definitions from {_fp('code.py')}",
        expect_tool="oap_exec", expect_in_output=["process_data", "format_output"]))
    tests.append(TestCase("parse-010", "parse",
        f"extract the timestamps from {_fp('app.log')} — just the time portion (HH:MM:SS)",
        expect_tool="oap_exec", expect_in_output=["10:00:01"]))
    tests.append(TestCase("parse-011", "parse",
        f"use jq to list all unique cities from {_fp('data.json')}",
        expect_tool="oap_exec", expect_in_output=["New York", "London", "Tokyo", "Paris"]))
    tests.append(TestCase("parse-012", "parse",
        f"extract the section headers from {_fp('config.ini')}",
        expect_tool="oap_exec", expect_in_output=["database", "server", "logging"]))
    tests.append(TestCase("parse-013", "parse",
        f"use jq to get names of people with score above 90 from {_fp('data.json')}",
        expect_tool="oap_exec", expect_in_output=["Bob", "Eve", "Grace"]))
    tests.append(TestCase("parse-014", "parse",
        f"extract all HTTP methods (GET, POST, etc.) used in {_fp('access.log')}",
        expect_tool="oap_exec", expect_in_output=["GET", "POST"]))
    tests.append(TestCase("parse-015", "parse",
        f"use jq to count how many people are from London in {_fp('data.json')}",
        expect_tool="oap_exec", expect_in_output=["2"]))

    # ===== PIPELINE (15 tests) =====
    # Multi-step tasks requiring chained tool calls or combined operations

    tests.append(TestCase("pipe-001", "pipeline",
        f"find all ERROR lines in {_fp('app.log')} and count them",
        expect_tool="oap_exec", expect_in_output=["4"]))
    tests.append(TestCase("pipe-002", "pipeline",
        f"list all unique email domains from {_fp('contacts.txt')}",
        expect_tool="oap_exec", expect_in_output=["example.com", "company.org"]))
    tests.append(TestCase("pipe-003", "pipeline",
        f"count how many GET requests are in {_fp('access.log')}",
        expect_tool="oap_exec", expect_in_output=["7"]))
    tests.append(TestCase("pipe-004", "pipeline",
        f"find all WARN messages in {_fp('app.log')} and show just the message text after WARN",
        expect_tool="oap_exec", expect_in_output=["Slow query", "Disk usage"]))
    tests.append(TestCase("pipe-005", "pipeline",
        f"count how many unique IP addresses appear in {_fp('access.log')}",
        expect_tool="oap_exec", expect_in_output=["4"]))
    tests.append(TestCase("pipe-006", "pipeline",
        f"sum all the quantities in {_fp('sales.csv')}",
        expect_tool="oap_exec", expect_in_output=["72"],
        allow_no_tool=True))
    tests.append(TestCase("pipe-007", "pipeline",
        f"find all lines containing 'import' in {_fp('code.py')} and count them",
        expect_tool="oap_exec", expect_in_output=["2"]))
    tests.append(TestCase("pipe-008", "pipeline",
        f"extract the port values from {_fp('config.ini')}",
        expect_tool="oap_exec", expect_in_output=["5432", "8080"]))
    tests.append(TestCase("pipe-009", "pipeline",
        f"count how many lines contain a number greater than 50 in {_fp('numbers.txt')}",
        expect_tool="oap_exec", expect_in_output=["3"],
        allow_no_tool=True))
    tests.append(TestCase("pipe-010", "pipeline",
        f"find all POST requests in {_fp('access.log')} and extract their URLs",
        expect_tool="oap_exec", expect_in_output=["/api/login", "/api/data"]))
    tests.append(TestCase("pipe-011", "pipeline",
        f"count the number of contacts who have email addresses in {_fp('contacts.txt')}",
        expect_tool="oap_exec", expect_in_output=["9"]))
    tests.append(TestCase("pipe-012", "pipeline",
        f"find all 200 status responses in {_fp('access.log')} and count them",
        expect_tool="oap_exec", expect_in_output=["7"]))
    tests.append(TestCase("pipe-013", "pipeline",
        f"extract all comments (lines starting with #) from {_fp('code.py')} and count them",
        expect_tool="oap_exec", expect_in_output=["5"],
        allow_no_tool=True))
    tests.append(TestCase("pipe-014", "pipeline",
        f"find how many Widget sales are in {_fp('sales.csv')}",
        expect_tool="oap_exec", expect_in_output=["4"]))
    tests.append(TestCase("pipe-015", "pipeline",
        f"find all lines with 'def ' in {_fp('code.py')} and show the function names",
        expect_tool="oap_exec", expect_in_output=["process_data", "format_output"]))

    # ===== IMPOSSIBLE (15 tests) =====
    # Tasks the system can't solve — should gracefully decline (no tool call)

    tests.append(TestCase("imp-001", "impossible",
        "I need to book a hotel in Maui for next weekend",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-002", "impossible",
        "Find me a source for Portland local news",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-003", "impossible",
        "What's the current stock price of AAPL?",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-004", "impossible",
        "Order me a large pepperoni pizza from Domino's",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-005", "impossible",
        "Schedule a Zoom meeting with my team for tomorrow at 2pm",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-006", "impossible",
        "What's the weather forecast for Seattle this week?",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-007", "impossible",
        "Send a text message to +1-555-0123 saying I'll be late",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-008", "impossible",
        "Play the song 'Bohemian Rhapsody' on Spotify",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-009", "impossible",
        "What movies are showing at the AMC theater near me?",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-010", "impossible",
        "Transfer $500 from my checking to my savings account",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-011", "impossible",
        "Set an alarm for 6:30 AM tomorrow morning",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-012", "impossible",
        "What's the latest score in the NBA finals?",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-013", "impossible",
        "Book me a flight from SFO to JFK for next Friday",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-014", "impossible",
        "Turn on the living room lights",
        expect_tool=None, allow_no_tool=True))
    tests.append(TestCase("imp-015", "impossible",
        "Add milk and eggs to my grocery shopping list",
        expect_tool=None, allow_no_tool=True))

    return tests


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
    log_file: Any | None = None,
    no_cache: bool = False,
) -> list[TestResult]:
    results: list[TestResult] = []
    total = len(tests)
    start_all = time.monotonic()
    consecutive_skips = 0

    for i, tc in enumerate(tests, 1):
        if dry_run:
            print(f"[{i:3d}/{total}] {tc.id:<14s}  {tc.category:<12s}  {tc.task[:60]}")
            continue

        elapsed_so_far = time.monotonic() - start_all
        if i > 1 and results:
            avg = elapsed_so_far / (i - 1)
            eta = avg * (total - i + 1)
            eta_str = f"  ETA {format_duration(eta)}"
        else:
            eta_str = ""

        # Back off after consecutive timeouts
        if consecutive_skips >= 2:
            cooldown = min(30, consecutive_skips * 10)
            print(dim(f"    [{consecutive_skips} consecutive timeouts, cooling down {cooldown}s...]"))
            time.sleep(cooldown)

        t0 = time.monotonic()
        response = send_chat(base_url, tc.task, model, timeout, no_cache=no_cache)
        duration = time.monotonic() - t0

        result = verify_test(tc, response, duration)
        if result.verdict == SKIP:
            consecutive_skips += 1
        else:
            consecutive_skips = 0
        results.append(result)

        # Write full response to log file (JSONL)
        if log_file is not None:
            log_entry = {
                "test_id": tc.id,
                "category": tc.category,
                "task": tc.task,
                "verdict": result.verdict,
                "tool_called": result.tool_called,
                "detail": result.detail,
                "duration_s": round(duration, 2),
                "message_content": (response or {}).get("message", {}).get("content", ""),
                "oap_debug": (response or {}).get("oap_debug"),
                "oap_experience_cache": (response or {}).get("oap_experience_cache"),
            }
            log_file.write(json.dumps(log_entry) + "\n")
            log_file.flush()

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

        if consecutive_skips >= 5:
            print(red(f"\n  Stopping: {consecutive_skips} consecutive timeouts — Ollama may be stuck"))
            break

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
        cat = r.test_id.rsplit("-", 1)[0]
        if cat not in categories:
            categories[cat] = {PASS: 0, SOFT: 0, WARN: 0, FAIL: 0, SKIP: 0}
        categories[cat][r.verdict] = categories[cat].get(r.verdict, 0) + 1

    failures = [r for r in results if r.verdict == FAIL]

    print("\n" + bold("=" * 56))
    print(bold("  Advanced Test Harness — Results"))
    print(bold("=" * 56))

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
        items = []
        for cat, v in cats_sorted:
            cat_total = sum(v.values())
            cat_pass = v[PASS] + v[SOFT]
            cat_pct = (cat_pass / cat_total * 100) if cat_total else 0
            c = green if cat_pct >= 80 else yellow if cat_pct >= 60 else red
            items.append(f"    {cat:<14s}{c(f'{cat_pass}/{cat_total}')} ({cat_pct:.0f}%)")
        for i in range(0, len(items), 2):
            pair = items[i:i+2]
            print("  ".join(pair))

    softs = [r for r in results if r.verdict == SOFT]
    if softs:
        print(f"\n  Soft passes (correct output, different mechanism):")
        for r in softs:
            detail = r.detail or "alternative mechanism"
            print(f"    {yellow(r.test_id)}: {detail}")

    if failures:
        print(f"\n  Failures:")
        for r in failures:
            detail = r.detail or "unknown reason"
            print(f"    {red(r.test_id)}: {detail}")

    print(bold("=" * 56))


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
        description="OAP Advanced Test Harness — file, parse, pipeline, and impossible-task tests",
    )
    parser.add_argument("--url", default="http://localhost:8300",
                        help="Discovery API base URL (default: http://localhost:8300)")
    parser.add_argument("--model", default="qwen3:8b",
                        help="Ollama model (default: qwen3:8b)")
    parser.add_argument("--timeout", type=float, default=120,
                        help="Per-request timeout in seconds (default: 120)")
    parser.add_argument("--category",
                        help="Comma-separated categories to run (e.g. file,parse)")
    parser.add_argument("--test",
                        help="Run a specific test by ID (e.g. file-001)")
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
    parser.add_argument("--log",
                        help="Write full response log (JSONL) for post-mortem analysis")
    parser.add_argument("--no-cache", action="store_true",
                        help="Skip experience cache (always run full discovery)")
    parser.add_argument("--token",
                        help="Backend auth token (required for /health check)")
    parser.add_argument("--keep-fixtures", action="store_true",
                        help="Don't remove fixture files after tests")
    parser.add_argument("--no-setup", action="store_true",
                        help="Skip fixture creation (assumes fixtures already exist)")

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

    print(bold(f"  OAP Advanced Test Harness"))
    print(f"  URL: {args.url}  Model: {args.model}  Tests: {len(all_tests)}")

    # Determine if we need fixtures (any non-impossible test)
    needs_fixtures = any(t.category != "impossible" for t in all_tests)

    # Setup fixtures
    if needs_fixtures and not args.no_setup:
        setup_fixtures()
    elif needs_fixtures and args.no_setup:
        if not os.path.exists(FIXTURE_DIR):
            print(red(f"  --no-setup but {FIXTURE_DIR} does not exist"), file=sys.stderr)
            sys.exit(1)
        print(f"  Using existing fixtures in {FIXTURE_DIR}/")

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

    log_file = open(args.log, "w") if args.log else None
    if log_file:
        print(f"  Logging responses to {args.log}")

    start = time.monotonic()
    try:
        results = run_tests(
            all_tests,
            args.url,
            args.model,
            args.timeout,
            args.fail_fast,
            args.verbose,
            args.dry_run,
            log_file,
            no_cache=args.no_cache,
        )
    finally:
        # Teardown fixtures unless --keep-fixtures or --no-setup
        if needs_fixtures and not args.keep_fixtures and not args.no_setup:
            teardown_fixtures()

    total_duration = time.monotonic() - start

    if log_file:
        log_file.close()
        print(f"\n  Response log: {args.log}")

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

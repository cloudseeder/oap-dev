#!/usr/bin/env python3
"""Synthetic test harness for RAG memory selection.

Sends chat messages to the agent and parses SSE responses.
Watch the agent logs alongside for Memory RAG/inject-all lines.

Usage:
    python scripts/test-memory-rag.py [--url http://localhost:8303]
"""

import argparse
import json
import sys
import httpx

# Test cases: (label, message, expected_behavior)
TESTS = [
    # --- Short messages: should inject-all ---
    ("short-greeting", "good morning", "inject-all (short)"),
    ("short-thanks", "thanks!", "inject-all (short)"),
    ("short-hi", "hey there", "inject-all (short)"),

    # --- Greetings with enough words: still likely generic ---
    ("greeting-long", "good morning, how are you today?", "inject-all (generic)"),

    # --- Topical queries: should trigger RAG ---
    ("topic-location", "what is the weather like where I live?", "RAG (location facts)"),
    ("topic-work", "can you help me with a coding problem at work?", "RAG (work/skills facts)"),
    ("topic-food", "what should I make for dinner tonight?", "RAG (food/preference facts)"),
    ("topic-family", "tell me about my family members", "RAG (family facts)"),
    ("topic-health", "I need to remember to take my medications", "RAG (health facts)"),
    ("topic-hobby", "I want to do something fun this weekend", "RAG (hobby/interest facts)"),

    # --- Edge cases ---
    ("generic-long", "I was just thinking about things and wondering what you think", "inject-all (generic)"),
    ("question-about-self", "what do you know about me?", "RAG or inject-all"),
    ("emotional", "I'm feeling really sad today and could use some company", "RAG (emotional/personal)"),
]


def send_chat(url: str, message: str, timeout: int = 60) -> dict:
    """Send a chat message, parse SSE response. Returns parsed result."""
    resp = httpx.post(
        f"{url}/v1/agent/chat",
        json={"message": message},
        timeout=timeout,
    )
    resp.raise_for_status()

    # Parse SSE events
    events = []
    for line in resp.text.split("\n"):
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
        elif line.startswith("event: "):
            events.append({"_event": line[7:]})

    # Extract assistant response
    assistant_content = ""
    conv_id = None
    for evt in events:
        if isinstance(evt, dict):
            if evt.get("message", {}).get("role") == "assistant":
                assistant_content = evt["message"].get("content", "")
            if evt.get("conversation_id"):
                conv_id = evt["conversation_id"]

    return {
        "content": assistant_content[:200],
        "conversation_id": conv_id,
        "events": len(events),
    }


def cleanup_conversation(url: str, conv_id: str):
    """Delete the test conversation."""
    try:
        httpx.delete(f"{url}/v1/agent/conversations/{conv_id}", timeout=10)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Test RAG memory selection")
    parser.add_argument("--url", default="http://localhost:8303", help="Agent URL")
    parser.add_argument("--test", help="Run a single test by label")
    parser.add_argument("--dry-run", action="store_true", help="Show tests without running")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout")
    args = parser.parse_args()

    tests = TESTS
    if args.test:
        tests = [(l, m, e) for l, m, e in TESTS if l == args.test]
        if not tests:
            print(f"Unknown test: {args.test}")
            print(f"Available: {', '.join(l for l, _, _ in TESTS)}")
            sys.exit(1)

    if args.dry_run:
        print(f"{'Label':<20} {'Expected':<25} Message")
        print("-" * 80)
        for label, message, expected in tests:
            print(f"{label:<20} {expected:<25} {message}")
        return

    # Check connectivity
    try:
        health = httpx.get(f"{args.url}/v1/agent/health", timeout=5)
        health.raise_for_status()
    except Exception as e:
        print(f"Cannot reach agent at {args.url}: {e}")
        sys.exit(1)

    # Get current fact count
    try:
        mem = httpx.get(f"{args.url}/v1/agent/memory", timeout=5).json()
        total_facts = mem.get("total", 0)
        pinned = sum(1 for f in mem.get("facts", []) if f.get("pinned"))
        print(f"Facts: {total_facts} total, {pinned} pinned\n")
    except Exception:
        print("Could not fetch memory stats\n")

    print(f"{'Label':<20} {'Expected':<25} {'Result':<12} Response preview")
    print("=" * 100)

    passed = 0
    for label, message, expected in tests:
        try:
            result = send_chat(args.url, message, timeout=args.timeout)
            preview = result["content"][:60].replace("\n", " ")
            conv_id = result["conversation_id"]

            # Check the agent logs for the actual behavior
            # (we can't see logs from here, but we print what we can)
            print(f"{label:<20} {expected:<25} {'ok':<12} {preview}")
            passed += 1

            # Clean up test conversation
            if conv_id:
                cleanup_conversation(args.url, conv_id)

        except Exception as e:
            print(f"{label:<20} {expected:<25} {'FAIL':<12} {e}")

    print(f"\n{passed}/{len(tests)} completed — check agent logs for Memory RAG/inject-all lines")


if __name__ == "__main__":
    main()

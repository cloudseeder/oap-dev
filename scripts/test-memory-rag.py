#!/usr/bin/env python3
"""Synthetic test harness for RAG memory selection.

Sends chat messages to the agent and reads just the first SSE event
(message_saved) — enough to confirm memory selection happened without
waiting for the full LLM response. Watch agent logs for the real signal.

Usage:
    python scripts/test-memory-rag.py [--url http://localhost:8303]
    python scripts/test-memory-rag.py --test topic-location
    python scripts/test-memory-rag.py --full   # wait for LLM responses
"""

import argparse
import json
import sys
import time
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


def send_chat_quick(url: str, message: str, timeout: int = 30) -> dict:
    """Send a chat message and read just the first SSE data event.

    Memory selection happens before the stream starts, so by the time
    we get the first event, the Memory RAG/inject-all log line has
    already been written. We close immediately — no need to wait for
    the full LLM response.
    """
    conv_id = None

    with httpx.stream(
        "POST",
        f"{url}/v1/agent/chat",
        json={"message": message},
        timeout=httpx.Timeout(timeout, connect=10),
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    conv_id = data.get("conversation_id")
                except json.JSONDecodeError:
                    pass
                # Got first data event — memory selection is done
                break

    return {"conversation_id": conv_id}


def send_chat_full(url: str, message: str, timeout: int = 300) -> dict:
    """Send a chat message and wait for the full LLM response."""
    assistant_content = ""
    conv_id = None

    with httpx.stream(
        "POST",
        f"{url}/v1/agent/chat",
        json={"message": message},
        timeout=httpx.Timeout(timeout, connect=10),
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    msg = data.get("message", {})
                    if msg.get("role") == "assistant":
                        assistant_content = msg.get("content", "")
                    if data.get("conversation_id"):
                        conv_id = data["conversation_id"]
                except json.JSONDecodeError:
                    pass

    return {"content": assistant_content[:200], "conversation_id": conv_id}


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
    parser.add_argument("--full", action="store_true", help="Wait for full LLM responses")
    parser.add_argument("--timeout", type=int, default=300, help="Request timeout (--full mode)")
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
        print(f"Facts: {total_facts} total, {pinned} pinned")
    except Exception:
        print("Could not fetch memory stats")

    mode = "full (waiting for LLM)" if args.full else "quick (memory selection only)"
    print(f"Mode: {mode}\n")

    header = f"{'Label':<20} {'Expected':<25} {'Time':<8}"
    if args.full:
        header += " Response preview"
    print(header)
    print("=" * 90)

    passed = 0
    for label, message, expected in tests:
        try:
            t0 = time.time()
            if args.full:
                result = send_chat_full(args.url, message, timeout=args.timeout)
                elapsed = time.time() - t0
                preview = result.get("content", "")[:50].replace("\n", " ")
                print(f"{label:<20} {expected:<25} {elapsed:5.1f}s  {preview}")
            else:
                result = send_chat_quick(args.url, message)
                elapsed = time.time() - t0
                print(f"{label:<20} {expected:<25} {elapsed:5.1f}s")
            passed += 1

            # Clean up test conversation
            conv_id = result.get("conversation_id")
            if conv_id:
                cleanup_conversation(args.url, conv_id)

            # Small delay between tests to avoid queuing on Ollama
            if args.full:
                time.sleep(1)

        except Exception as e:
            elapsed = time.time() - t0
            err = str(e)[:60]
            print(f"{label:<20} {expected:<25} {elapsed:5.1f}s  FAIL: {err}")

    print(f"\n{passed}/{len(tests)} completed — check agent logs for Memory RAG/inject-all lines")


if __name__ == "__main__":
    main()

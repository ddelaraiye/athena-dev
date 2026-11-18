"""
M0 — Text engine instrumentation test.

Runs varied conversations against the running Athena server and
records Ollama response metadata (done, done_reason, total_duration,
load_duration, prompt_eval_count, eval_count, eval_duration) to
establish whether response truncation is caused by num_predict limits,
context overflow, stop sequences, model termination, frontend rendering,
or backend response handling.

Prerequisites:
  - Athena server running on http://127.0.0.1:8765
  - Ollama running with athena-llama:3b loaded

Run:
  C:\Athena\.venv\Scripts\python.exe tests/test_m0_text_engine.py
"""

import json
import sys
import time

import httpx

BASE_URL = "http://127.0.0.1:8765"
REQUEST_TIMEOUT = 120.0  # seconds per request

# Varied conversations to exercise the text engine.
# Each entry: name, messages (turns to send sequentially).
# Multi-turn conversations share one conversation_id to test continuity.
CONVERSATIONS = [
    {
        "name": "1_short_greeting",
        "messages": ["Hello, who are you?"],
    },
    {
        "name": "2_factual_explanation",
        "messages": ["Explain how a refrigerator works in two paragraphs."],
    },
    {
        "name": "3_reasoning_puzzle",
        "messages": [
            "A farmer has 17 sheep. All but 9 die. How many are left? "
            "Explain your reasoning step by step."
        ],
    },
    {
        "name": "4_creative_story",
        "messages": [
            "Write a short science-fiction story (about 200 words) about "
            "a robot that discovers music for the first time."
        ],
    },
    {
        "name": "5_technical_summary",
        "messages": [
            "Summarise the concept of CPU cache locality and why it "
            "matters for program performance. Keep it under 250 words."
        ],
    },
    {
        "name": "6_multi_turn_a",
        "messages": [
            "What is the capital of Japan?",
            "And what is its population?",
        ],
    },
    {
        "name": "7_multi_turn_b",
        "messages": [
            "Tell me about the Python programming language.",
            "Can you show me a simple example of a list comprehension?",
        ],
    },
    {
        "name": "8_long_prompt",
        "messages": [
            "Please read the following passage and answer the question at "
            "the end: "
            + ("The quick brown fox jumps over the lazy dog. " * 40)
            + "Question: What animal jumps over the lazy dog?"
        ],
    },
    {
        "name": "9_open_ended",
        "messages": [
            "What are the trade-offs between using a relational database "
            "versus a document store for a personal project?"
        ],
    },
    {
        "name": "10_emotive_support",
        "messages": [
            "I'm feeling overwhelmed with work. Can you offer some "
            "practical, gentle advice for managing stress?"
        ],
    },
]


def check_health(client):
    r = client.get(f"{BASE_URL}/api/health", timeout=10.0)
    r.raise_for_status()
    data = r.json()
    print(f"[health] status={data['status']} ollama={data['ollama']} "
          f"model={data['model']}", flush=True)
    return data


def chat_once(client, message, conversation_id=None):
    """Send one message and return (reply, metadata, elapsed_s, conv_id)."""
    payload = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    start = time.perf_counter()
    r = client.post(f"{BASE_URL}/api/chat", json=payload,
                    timeout=REQUEST_TIMEOUT)
    elapsed = time.perf_counter() - start
    r.raise_for_status()
    data = r.json()
    reply = data.get("reply", "")
    metadata = data.get("ollama_metadata", {})
    return reply, metadata, elapsed, data.get("conversation_id")


def truncation_flags(metadata):
    """Heuristics for detecting response truncation."""
    flags = []
    done_reason = metadata.get("done_reason")
    eval_count = metadata.get("eval_count")

    if done_reason == "length":
        flags.append("done_reason=length (hit num_predict limit)")
    if done_reason is None:
        flags.append("done_reason missing from Ollama response")
    if eval_count == 1000:
        flags.append("eval_count==1000 (likely hit num_predict=1000)")
    return flags


def main():
    client = httpx.Client(timeout=10.0)

    print("=" * 72, flush=True)
    print("M0 — Athena text engine instrumentation", flush=True)
    print("=" * 72, flush=True)

    health = check_health(client)
    if health["ollama"] != "connected":
        print("ERROR: Ollama is not connected. Aborting.", flush=True)
        sys.exit(1)

    results = []

    for conv in CONVERSATIONS:
        name = conv["name"]
        print(f"\n--- {name} ---", flush=True)
        conversation_id = None
        turn_results = []

        for i, message in enumerate(conv["messages"]):
            try:
                reply, metadata, elapsed, conversation_id = chat_once(
                    client, message, conversation_id
                )
            except httpx.HTTPError as exc:
                print(f"  Turn {i+1} ERROR: {exc}", flush=True)
                turn_results.append({
                    "turn": i + 1,
                    "message_len": len(message),
                    "error": str(exc),
                })
                continue
            except httpx.TimeoutException as exc:
                print(f"  Turn {i+1} TIMEOUT: {exc}", flush=True)
                turn_results.append({
                    "turn": i + 1,
                    "message_len": len(message),
                    "error": f"timeout: {exc}",
                })
                continue

            flags = truncation_flags(metadata)
            turn = {
                "turn": i + 1,
                "message_len": len(message),
                "reply_len": len(reply),
                "done": metadata.get("done"),
                "done_reason": metadata.get("done_reason"),
                "eval_count": metadata.get("eval_count"),
                "eval_duration_ms": metadata.get("eval_duration"),
                "total_duration_ms": metadata.get("total_duration"),
                "load_duration_ms": metadata.get("load_duration"),
                "prompt_eval_count": metadata.get("prompt_eval_count"),
                "elapsed_s": round(elapsed, 3),
                "truncation_flags": flags,
                "reply_preview": reply[:120].replace("\n", " "),
            }
            turn_results.append(turn)
            print(
                f"  Turn {i+1}: msg={len(message)}ch reply={len(reply)}ch "
                f"done_reason={metadata.get('done_reason')} "
                f"eval_count={metadata.get('eval_count')} "
                f"total_dur={metadata.get('total_duration')}ms "
                f"elapsed={elapsed:.2f}s",
                flush=True,
            )
            if flags:
                print(f"    FLAGS: {', '.join(flags)}", flush=True)

        results.append({"name": name, "turns": turn_results})

    client.close()

    # ---- Summary report ----
    print("\n" + "=" * 72, flush=True)
    print("M0 SUMMARY", flush=True)
    print("=" * 72, flush=True)

    total_turns = 0
    total_flags = 0
    length_hits = 0
    stop_reasons = 0

    for conv_result in results:
        for turn in conv_result["turns"]:
            total_turns += 1
            if turn.get("truncation_flags"):
                total_flags += len(turn["truncation_flags"])
            if turn.get("done_reason") == "length":
                length_hits += 1
            if turn.get("done_reason") == "stop":
                stop_reasons += 1

    print(f"Total turns tested: {total_turns}", flush=True)
    print(f"Total truncation flags: {total_flags}", flush=True)
    print(f"done_reason=length (num_predict limit): {length_hits}", flush=True)
    print(f"done_reason=stop (normal completion): {stop_reasons}", flush=True)

    suspicious = []
    for conv_result in results:
        for turn in conv_result["turns"]:
            if turn.get("done_reason") == "length":
                suspicious.append(
                    f"  {conv_result['name']} turn {turn['turn']}: "
                    f"done_reason=length, eval_count={turn.get('eval_count')}, "
                    f"reply_len={turn.get('reply_len')}"
                )

    if suspicious:
        print("\nPOTENTIAL TRUNCATION (done_reason=length):", flush=True)
        for s in suspicious:
            print(s, flush=True)
    else:
        print("\nNo done_reason=length detected. Responses appear complete.",
              flush=True)

    # Save detailed results to JSON
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": health["model"],
        "num_predict": 1000,
        "results": results,
        "summary": {
            "total_turns": total_turns,
            "total_truncation_flags": total_flags,
            "done_reason_length": length_hits,
            "done_reason_stop": stop_reasons,
        },
    }
    report_path = "tests/m0_results.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nDetailed results written to {report_path}", flush=True)

    if length_hits > 0:
        print("\nM0 RESULT: Truncation detected via done_reason=length.", flush=True)
        return 1
    print("\nM0 RESULT: No truncation detected. Text engine stable.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

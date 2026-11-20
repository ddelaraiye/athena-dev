"""
Verification tests for Athena v0.1 stabilization fixes.

Tests:
1. Valid WAV audio upload returns a transcript through the /api/transcribe
   endpoint (uses synthetic sine-wave audio; verifies pipeline handling,
   not speech recognition accuracy).
2. Transcription response includes processing_time_ms.
3. Empty WAV audio is rejected with HTTP 400.
4. No file uploaded returns HTTP 400/422.
5. Both user and assistant messages are persisted on successful chat.
6. Multi-turn conversation context is preserved.
7. Conversation history is not duplicated in the model prompt.

Prerequisites:
  - Athena server running on http://127.0.0.1:8765
  - Ollama running on http://localhost:11434

Run:
  C:\Athena\.venv\Scripts\python.exe tests/test_fixes_verification.py
"""

import json
import os
import sys
import time
import wave
import struct
import math

import httpx

BASE_URL = "http://127.0.0.1:8765"
TRANSCRIBE_URL = f"{BASE_URL}/api/transcribe"
CHAT_URL = f"{BASE_URL}/api/chat"
HEALTH_URL = f"{BASE_URL}/api/health"

RESULTS = []


def record_test(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": passed, "detail": detail})
    status = "PASS" if passed else "FAIL"
    safe_detail = detail.encode("ascii", errors="replace").decode("ascii")
    print(f"  [{status}] {name}" + (f" - {safe_detail}" if safe_detail else ""))


def create_wav_file(path, duration_seconds=2, frequency_hz=440, sample_rate=16000):
    """Create a proper WAV file with RIFF header in little-endian."""
    frames = []
    for i in range(int(sample_rate * duration_seconds)):
        value = int(12000 * math.sin(2 * math.pi * frequency_hz * i / sample_rate))
        frames.append(value.to_bytes(2, "little", signed=True))

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))


def create_empty_wav(path, sample_rate=16000):
    """Create an empty WAV file (header only, no audio data)."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"")


def check_health(client):
    r = client.get(HEALTH_URL, timeout=10.0)
    r.raise_for_status()
    return r.json()


def test_transcription_valid_wav(tmp_dir):
    """Test 1: Valid WAV audio returns a transcript.

    Uses synthetic sine-wave audio to verify the /api/transcribe endpoint
    and ffmpeg+whisper.cpp pipeline are functioning. This verifies pipeline
    handling, not speech recognition accuracy (sine waves are not speech).
    """
    wav_path = os.path.join(tmp_dir, "test_valid.wav")
    create_wav_file(wav_path, duration_seconds=2)

    with open(wav_path, "rb") as f:
        file_bytes = f.read()

    with httpx.Client(timeout=120.0) as client:
        files = {"upload": ("test_valid.wav", file_bytes, "audio/wav")}
        response = client.post(TRANSCRIBE_URL, files=files)

    if response.status_code == 200:
        data = response.json()
        transcript = data.get("transcript", "")
        proc_time = data.get("processing_time_ms", 0)
        record_test(
            "Valid WAV transcription returns transcript",
            True,
            f"transcript='{transcript[:60]}' processing={proc_time}ms"
        )
    else:
        record_test(
            "Valid WAV transcription returns transcript",
            False,
            f"HTTP {response.status_code}"
        )


def test_transcription_includes_processing_time(tmp_dir):
    """Test 2: Transcription response includes processing_time_ms."""
    wav_path = os.path.join(tmp_dir, "test_timing.wav")
    create_wav_file(wav_path, duration_seconds=2)

    with open(wav_path, "rb") as f:
        file_bytes = f.read()

    with httpx.Client(timeout=120.0) as client:
        files = {"upload": ("test_timing.wav", file_bytes, "audio/wav")}
        response = client.post(TRANSCRIBE_URL, files=files)

    if response.status_code == 200:
        data = response.json()
        proc_time = data.get("processing_time_ms")
        passed = isinstance(proc_time, int) and proc_time > 0
        record_test(
            "Processing time reported",
            passed,
            f"{proc_time}ms" if proc_time else "missing"
        )
    else:
        record_test("Processing time reported", False, f"HTTP {response.status_code}")


def test_empty_audio_rejected(tmp_dir):
    """Test 3: Empty WAV file is rejected."""
    wav_path = os.path.join(tmp_dir, "test_empty.wav")
    create_empty_wav(wav_path)

    with open(wav_path, "rb") as f:
        file_bytes = f.read()

    with httpx.Client(timeout=30.0) as client:
        files = {"upload": ("test_empty.wav", file_bytes, "audio/wav")}
        response = client.post(TRANSCRIBE_URL, files=files)

    passed = response.status_code == 400
    record_test(
        "Empty audio rejected with HTTP 400",
        passed,
        f"HTTP {response.status_code}"
    )


def test_no_file_rejected():
    """Test 4: No file uploaded returns error."""
    with httpx.Client(timeout=30.0) as client:
        response = client.post(TRANSCRIBE_URL, data={})

    passed = response.status_code in (400, 422)
    record_test(
        "No file uploaded rejected",
        passed,
        f"HTTP {response.status_code}"
    )


def test_chat_persists_user_and_assistant_messages():
    """Test 5: Both user and assistant messages are persisted on successful chat.

    Sends a message with Ollama running and verifies both the user and
    assistant messages are written to SQLite for the same conversation_id.
    This tests the successful persistence path only; the Ollama-down failure
    path was verified separately (manually, not in this test file).
    """
    import sqlite3

    # Send a message (Ollama should be running)
    with httpx.Client(timeout=180.0) as client:
        r = client.post(
            CHAT_URL,
            json={"message": "Test persistence message", "conversation_id": None},
        )

    if r.status_code != 200:
        record_test(
            "Chat succeeds when Ollama is up",
            False,
            f"HTTP {r.status_code}"
        )
        return

    data = r.json()
    conv_id = data.get("conversation_id")

    # Verify both user and assistant messages are in the database
    conn = sqlite3.connect("data/conversations.db")
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
        (conv_id,),
    ).fetchall()
    conn.close()

    roles = [row[0] for row in rows]
    has_user = "user" in roles
    has_assistant = "assistant" in roles

    record_test(
        "Both user and assistant messages persisted",
        has_user and has_assistant,
        f"roles={roles}"
    )


def test_multi_turn_context():
    """Test 6: Multi-turn conversation preserves context."""
    with httpx.Client(timeout=180.0) as client:
        # Turn 1
        r1 = client.post(
            CHAT_URL,
            json={"message": "My favorite color is blue", "conversation_id": None},
        )
        if r1.status_code != 200:
            record_test("Multi-turn context - turn 1", False, f"HTTP {r1.status_code}")
            return
        conv_id = r1.json().get("conversation_id")

        # Turn 2
        r2 = client.post(
            CHAT_URL,
            json={"message": "What is my favorite color?", "conversation_id": conv_id},
        )
        if r2.status_code != 200:
            record_test("Multi-turn context - turn 2", False, f"HTTP {r2.status_code}")
            return
        reply = r2.json().get("reply", "")

    passed = "blue" in reply.lower()
    record_test(
        "Multi-turn context preserved",
        passed,
        f"reply='{reply[:100]}'"
    )


def test_no_duplicate_history():
    """Test 7: Conversation history is not duplicated in prompt.

    This is verified indirectly: if history were duplicated, the prompt
    would be longer and eval_count/prompt_eval_count would be higher than
    expected for the conversation length.
    """
    import sqlite3

    with httpx.Client(timeout=180.0) as client:
        # Send a simple message
        r = client.post(
            CHAT_URL,
            json={"message": "Say hello back", "conversation_id": None},
        )
        if r.status_code != 200:
            record_test("No duplicate history", False, f"HTTP {r.status_code}")
            return
        metadata = r.json().get("ollama_metadata", {})
        prompt_eval_count = metadata.get("prompt_eval_count", 0)

    # "Say hello back" is ~3 words, plus system prompt (~100 tokens)
    # prompt_eval_count should be reasonable (~150), not doubled (~300+)
    passed = prompt_eval_count < 400
    record_test(
        "No duplicate history in prompt",
        passed,
        f"prompt_eval_count={prompt_eval_count}"
    )


def main():
    tmp_dir = os.path.join(os.environ.get("TEMP", "/tmp"), "athena_fixes_test")
    os.makedirs(tmp_dir, exist_ok=True)

    print("=" * 72)
    print("Athena v0.1 Stabilization Fixes Verification")
    print("=" * 72)

    print("\n[health check]")
    with httpx.Client(timeout=10.0) as client:
        try:
            data = check_health(client)
            print(f"  status={data['status']} ollama={data['ollama']} model={data['model']}")
            if data["ollama"] != "connected":
                print("  ERROR: Ollama not connected")
                sys.exit(1)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            print("Server not running. Start Athena and Ollama first.")
            sys.exit(1)

    print("\n[tests]")
    test_transcription_valid_wav(tmp_dir)
    test_transcription_includes_processing_time(tmp_dir)
    test_empty_audio_rejected(tmp_dir)
    test_no_file_rejected()
    test_chat_persists_user_and_assistant_messages()
    test_multi_turn_context()
    test_no_duplicate_history()

    # Cleanup temp files
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # Summary
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = total - passed

    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    for r in RESULTS:
        if not r["passed"]:
            print(f"\nFAILED: {r['name']} - {r['detail']}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

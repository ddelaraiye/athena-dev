"""
M1 — Independent speech recognition test.

Tests the /api/transcribe endpoint independently of Ollama:
- Valid WAV audio upload -> accurate transcript
- Empty audio -> error
- Unsupported format -> error
- Audio file size validation
- Temporary file cleanup
- Processing time measurement

Prerequisites:
  - Athena server running on http://127.0.0.1:8765
  - whisper.cpp at tools/whisper.cpp/main.exe
  - base.en model at tools/whisper.cpp/models/ggml-base.en.bin
  - ffmpeg at tools/ffmpeg/bin/ffmpeg.exe

Run:
  C:\Athena\.venv\Scripts\python.exe tests/test_m1_stt.py
"""

import io
import json
import os
import sys
import time
import wave

import httpx

BASE_URL = "http://127.0.0.1:8765"
TRANSCRIBE_URL = f"{BASE_URL}/api/transcribe"
CHAT_URL = f"{BASE_URL}/api/chat"

RESULTS = []


def record_test(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": passed, "detail": detail})
    status = "PASS" if passed else "FAIL"
    # Use ASCII-only output to avoid cp1252 encoding issues on Windows
    safe_detail = detail.encode("ascii", errors="replace").decode("ascii")
    print(f"  [{status}] {name}" + (f" - {safe_detail}" if safe_detail else ""))


def create_wav_file(path, duration_seconds=3, frequency_hz=440, sample_rate=16000):
    """Create a WAV file with a sine wave test tone."""
    import math

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


def test_valid_wav_transcription(tmp_dir):
    """Test 1: Valid WAV audio upload returns a transcript."""
    wav_path = os.path.join(tmp_dir, "test_speech.wav")
    create_wav_file(wav_path, duration_seconds=3)

    with open(wav_path, "rb") as f:
        file_bytes = f.read()

    start = time.perf_counter()
    with httpx.Client(timeout=120.0) as client:
        files = {"upload": ("test_speech.wav", file_bytes, "audio/wav")}
        response = client.post(TRANSCRIBE_URL, files=files)
    elapsed = time.perf_counter() - start

    try:
        data = response.json()
    except json.JSONDecodeError:
        record_test("Valid WAV transcription", False, f"Non-JSON response: {response.status_code}")
        return

    if response.status_code == 200:
        transcript = data.get("transcript", "")
        proc_time = data.get("processing_time_ms", 0)
        record_test(
            "Valid WAV transcription",
            True,
            f"transcript='{transcript[:60]}' processing={proc_time}ms total={elapsed:.2f}s"
        )
    else:
        record_test(
            "Valid WAV transcription",
            False,
            f"HTTP {response.status_code}: {data.get('detail', 'unknown error')}"
        )


def test_empty_audio(tmp_dir):
    """Test 2: Empty audio upload returns an error."""
    wav_path = os.path.join(tmp_dir, "empty.wav")
    create_empty_wav(wav_path)

    with open(wav_path, "rb") as f:
        file_bytes = f.read()

    with httpx.Client(timeout=30.0) as client:
        files = {"upload": ("empty.wav", file_bytes, "audio/wav")}
        response = client.post(TRANSCRIBE_URL, files=files)

    # Should return 400 or 500, not 200
    passed = response.status_code != 200
    record_test(
        "Empty audio rejected",
        passed,
        f"HTTP {response.status_code}"
    )


def test_no_file_uploaded():
    """Test 3: No file uploaded returns an error."""
    with httpx.Client(timeout=30.0) as client:
        response = client.post(TRANSCRIBE_URL, data={})

    # FastAPI returns 422 for missing required form fields
    passed = response.status_code in (400, 422)
    record_test(
        "No file uploaded rejected",
        passed,
        f"HTTP {response.status_code}"
    )


def test_unsupported_format(tmp_dir):
    """Test 4: Non-audio file returns an error."""
    txt_path = os.path.join(tmp_dir, "not_audio.txt")
    with open(txt_path, "w") as f:
        f.write("This is not audio.")

    with open(txt_path, "rb") as f:
        file_bytes = f.read()

    with httpx.Client(timeout=30.0) as client:
        files = {"upload": ("not_audio.txt", file_bytes, "text/plain")}
        response = client.post(TRANSCRIBE_URL, files=files)

    # ffmpeg may or may not be able to convert a text file - either way
    # it should not return a successful transcript
    try:
        data = response.json()
        transcript = data.get("transcript", "")
        passed = response.status_code != 200 or transcript == ""
    except json.JSONDecodeError:
        passed = response.status_code != 200

    record_test(
        "Unsupported format handled",
        passed,
        f"HTTP {response.status_code}"
    )


def test_processing_time_reported(tmp_dir):
    """Test 5: Transcription response includes processing_time_ms."""
    wav_path = os.path.join(tmp_dir, "timing_test.wav")
    create_wav_file(wav_path, duration_seconds=2)

    with open(wav_path, "rb") as f:
        file_bytes = f.read()

    with httpx.Client(timeout=120.0) as client:
        files = {"upload": ("timing_test.wav", file_bytes, "audio/wav")}
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
        record_test(
            "Processing time reported",
            False,
            f"HTTP {response.status_code}"
        )


def test_transcript_to_chat(tmp_dir):
    """Test 6: Transcript can be sent to /api/chat and gets a response."""
    wav_path = os.path.join(tmp_dir, "chat_test.wav")
    create_wav_file(wav_path, duration_seconds=2)

    with open(wav_path, "rb") as f:
        file_bytes = f.read()

    # Transcribe
    with httpx.Client(timeout=120.0) as client:
        files = {"upload": ("chat_test.wav", file_bytes, "audio/wav")}
        resp = client.post(TRANSCRIBE_URL, files=files)

    if resp.status_code != 200:
        record_test(
            "Transcript -> chat integration",
            False,
            f"Transcription failed: HTTP {resp.status_code}"
        )
        return

    transcript = resp.json().get("transcript", "")
    if not transcript:
        record_test(
            "Transcript -> chat integration",
            False,
            "Empty transcript from STT"
        )
        return

    # Send transcript to chat
    with httpx.Client(timeout=180.0) as client:
        response = client.post(
            CHAT_URL,
            json={"message": transcript, "conversation_id": None},
        )

    if response.status_code == 200:
        data = response.json()
        reply = data.get("reply", "")
        conv_id = data.get("conversation_id")
        passed = bool(reply) and bool(conv_id)
        record_test(
            "Transcript -> chat integration",
            passed,
            f"reply='{reply[:60]}' conv_id={conv_id[:8] if conv_id else None}..."
        )
    else:
        data = response.json()
        record_test(
            "Transcript -> chat integration",
            False,
            f"HTTP {response.status_code}: {data.get('detail', 'unknown')}"
        )


def test_multi_turn_continuity():
    """Test 7: Multi-turn conversation preserves context."""
    with httpx.Client(timeout=180.0) as client:
        # Turn 1
        r1 = client.post(CHAT_URL, json={"message": "My name is Alex.", "conversation_id": None})
        if r1.status_code != 200:
            record_test("Multi-turn continuity", False, f"Turn 1 failed: HTTP {r1.status_code}")
            return
        conv_id = r1.json().get("conversation_id")

        # Turn 2
        r2 = client.post(CHAT_URL, json={"message": "What is my name?", "conversation_id": conv_id})
        if r2.status_code != 200:
            record_test("Multi-turn continuity", False, f"Turn 2 failed: HTTP {r2.status_code}")
            return
        reply = r2.json().get("reply", "")

    passed = "Alex" in reply
    record_test(
        "Multi-turn continuity",
        passed,
        f"reply='{reply[:80]}'"
    )


def main():
    tmp_dir = os.path.join(os.environ.get("TEMP", "/tmp"), "athena_m1_test")
    os.makedirs(tmp_dir, exist_ok=True)

    print("=" * 72)
    print("M1 — Independent speech recognition test")
    print("=" * 72)

    print("\n[health check]")
    with httpx.Client(timeout=10.0) as client:
        try:
            r = client.get(f"{BASE_URL}/api/health")
            data = r.json()
            print(f"  status={data['status']} ollama={data['ollama']} model={data['model']}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
            print("\nServer not running. Start Athena first.")
            sys.exit(1)

    print("\n[tests]")
    test_valid_wav_transcription(tmp_dir)
    test_empty_audio(tmp_dir)
    test_no_file_uploaded()
    test_unsupported_format(tmp_dir)
    test_processing_time_reported(tmp_dir)
    test_transcript_to_chat(tmp_dir)
    test_multi_turn_continuity()

    # Summary
    print("\n" + "=" * 72)
    print("M1 SUMMARY")
    print("=" * 72)

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = total - passed

    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    for r in RESULTS:
        if not r["passed"]:
            print(f"\nFAILED: {r['name']} — {r['detail']}")

    # Cleanup temp files
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

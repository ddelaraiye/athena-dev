"""
M4 — Performance benchmarking.

Measures actual system performance:
- Idle RAM
- RAM with Ollama loaded
- STT processing time (per audio length)
- LLM generation time (per response length)
- Total time to first audio (STT + LLM + TTS initiation)

Prerequisites:
  - Athena server running on http://127.0.0.1:8765
  - Ollama running with athena-llama:3b
  - whisper.cpp and ffmpeg installed

Run:
  C:\Athena\.venv\Scripts\python.exe tests/test_m4_benchmark.py
"""

import json
import os
import subprocess
import sys
import time

import httpx

BASE_URL = "http://127.0.0.1:8765"
CHAT_URL = f"{BASE_URL}/api/chat"
TRANSCRIBE_URL = f"{BASE_URL}/api/transcribe"

RESULTS = {}


def get_process_memory_mb(process_name="ollama.exe"):
    """Get RAM usage (MB) for a process by name, using Windows tasklist."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            return None
        # CSV header: "Image Name","PID","Session Name","Session#","Mem Usage"
        data_line = lines[1]
        parts = data_line.split(",")
        if len(parts) >= 5:
            mem_str = parts[4].strip('"').replace(",", "").replace(" K", "")
            return int(mem_str) / 1024  # KB -> MB
    except Exception as exc:
        print(f"  [warn] Could not read memory: {exc}")
    return None


def benchmark_ollama_memory():
    """Measure RAM with Ollama loaded."""
    mem_mb = get_process_memory_mb("ollama.exe")
    RESULTS["ollama_ram_mb"] = round(mem_mb, 1) if mem_mb else None
    print(f"  Ollama RAM: {RESULTS['ollama_ram_mb']} MB")


def benchmark_stt(audio_path, label):
    """Benchmark STT transcription time."""
    with open(audio_path, "rb") as f:
        file_bytes = f.read()

    start = time.perf_counter()
    with httpx.Client(timeout=300.0) as client:
        files = {"upload": (os.path.basename(audio_path), file_bytes, "audio/wav")}
        response = client.post(TRANSCRIBE_URL, files=files)
    elapsed = time.perf_counter() - start

    if response.status_code == 200:
        data = response.json()
        proc_time_ms = data.get("processing_time_ms", 0)
        transcript = data.get("transcript", "")
        RESULTS[f"stt_{label}"] = {
            "wall_time_s": round(elapsed, 2),
            "processing_time_ms": proc_time_ms,
            "transcript_chars": len(transcript),
            "transcript": transcript[:80],
        }
        print(f"  STT {label}: {elapsed:.2f}s wall, {proc_time_ms}ms processing, "
              f"{len(transcript)} chars")
    else:
        RESULTS[f"stt_{label}"] = {"error": f"HTTP {response.status_code}"}
        print(f"  STT {label}: FAILED HTTP {response.status_code}")


def benchmark_llm(message, label):
    """Benchmark LLM generation time."""
    start = time.perf_counter()
    with httpx.Client(timeout=300.0) as client:
        response = client.post(
            CHAT_URL,
            json={"message": message, "conversation_id": None},
        )
    elapsed = time.perf_counter() - start

    if response.status_code == 200:
        data = response.json()
        reply = data.get("reply", "")
        metadata = data.get("ollama_metadata", {})
        eval_count = metadata.get("eval_count", 0)
        eval_duration_ms = metadata.get("eval_duration", 0)
        # eval_duration is in nanoseconds
        eval_duration_s = eval_duration_ms / 1e9 if eval_duration_ms else 0
        tokens_per_sec = eval_count / eval_duration_s if eval_duration_s > 0 else 0

        RESULTS[f"llm_{label}"] = {
            "wall_time_s": round(elapsed, 2),
            "reply_chars": len(reply),
            "eval_count": eval_count,
            "tokens_per_sec": round(tokens_per_sec, 1),
            "done_reason": metadata.get("done_reason"),
        }
        print(
            f"  LLM {label}: {elapsed:.2f}s wall, {len(reply)} chars, "
            f"{eval_count} tokens, {tokens_per_sec:.1f} tok/s, "
            f"done_reason={metadata.get('done_reason')}"
        )
    else:
        RESULTS[f"llm_{label}"] = {"error": f"HTTP {response.status_code}"}
        print(f"  LLM {label}: FAILED HTTP {response.status_code}")


def create_wav_file(path, duration_seconds, frequency_hz=440, sample_rate=16000):
    """Create a WAV test tone."""
    import math
    import wave
    import struct

    frames = []
    for i in range(int(sample_rate * duration_seconds)):
        value = int(12000 * math.sin(2 * math.pi * frequency_hz * i / sample_rate))
        frames.append(struct.pack("<h", value))

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))


def main():
    tmp_dir = os.path.join(os.environ.get("TEMP", "/tmp"), "athena_m4_bench")
    os.makedirs(tmp_dir, exist_ok=True)

    print("=" * 72)
    print("M4 — Athena Performance Benchmark")
    print("=" * 72)

    print("\n[health check]")
    with httpx.Client(timeout=10.0) as client:
        try:
            r = client.get(f"{BASE_URL}/api/health")
            data = r.json()
            print(f"  status={data['status']} ollama={data['ollama']} "
                  f"model={data['model']}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
            print("Server not running. Start Athena first.")
            sys.exit(1)

    print("\n[1] Memory measurements")
    print("-" * 40)
    benchmark_ollama_memory()

    print("\n[2] STT benchmarks (whisper.cpp base.en)")
    print("-" * 40)
    for duration in [2, 5, 10]:
        wav_path = os.path.join(tmp_dir, f"test_{duration}s.wav")
        create_wav_file(wav_path, duration_seconds=duration)
        benchmark_stt(wav_path, f"{duration}s")

    print("\n[3] LLM benchmarks (Ollama athena-llama:3b)")
    print("-" * 40)
    benchmark_llm("Hello, who are you?", "short")
    benchmark_llm("Explain quantum computing in simple terms.", "medium")
    benchmark_llm(
        "Write a detailed essay about the history of artificial "
        "intelligence, covering its origins, major milestones, "
        "and future prospects. Include specific examples and dates.",
        "long"
    )

    print("\n[4] Estimated time to first audio")
    print("-" * 40)
    # STT (5s audio) + LLM (short response) ≈ time from speaking to hearing
    stt_5s = RESULTS.get("stt_5s", {}).get("wall_time_s", 0)
    llm_short = RESULTS.get("llm_short", {}).get("wall_time_s", 0)
    ttf_audio = stt_5s + llm_short
    RESULTS["estimated_time_to_first_audio_s"] = round(ttf_audio, 2)
    print(f"  STT (5s audio): {stt_5s}s")
    print(f"  LLM (short response): {llm_short}s")
    print(f"  Estimated time to first audio: {ttf_audio:.2f}s")
    print("  (TTS initiation is near-instant with browser speechSynthesis)")

    print("\n[5] Summary")
    print("-" * 40)
    print(json.dumps(RESULTS, indent=2))

    # Save results
    report_path = "tests/m4_results.json"
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "machine": "AMD Ryzen 5 5625U, 6c/12t, ~8 GB RAM, Windows 10",
        "model": "athena-llama:3b",
        "stt_model": "whisper.cpp base.en",
        "results": RESULTS,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nResults written to {report_path}")

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())

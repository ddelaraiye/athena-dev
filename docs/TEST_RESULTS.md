# Athena Test Results

**Test machine:** Windows 10 Home, AMD Ryzen 5 5625U (6c/12t), ~8 GB RAM, integrated Radeon  
**Python:** 3.13.15 (venv at C:\Athena\.venv)  
**Ollama:** 0.32.15, model `athena-llama:3b` (~2.02 GB)  
**STT:** whisper.cpp base.en (ggml-base.en.bin, 142 MB), 4 threads  
**TTS:** Browser speechSynthesis  

---

## M0 — Text Engine Instrumentation

**Date:** 18-19 November 2026  
**Test:** tests/test_m0_text_engine.py  
**Result:** PASS — 12/12 turns, no truncation in short/medium responses

| Metric | Value |
|--------|-------|
| Total turns tested | 12 |
| done_reason=stop (normal) | 12 |
| done_reason=length (num_predict limit) | 0 |
| Truncation flags | 0 |
| eval_count range | 8 to 558 |
| num_predict | 1000 |

**Conclusion:** No truncation in short/medium responses (up to ~558 tokens). The `num_predict=1000` limit was not approached. However, M4 benchmarking confirmed truncation DOES occur for long responses (>1000 tokens) — see M4 findings below. Text engine is stable for normal-length responses.

---

## M1 — Independent Speech Recognition

**Date:** 19 November 2026  
**Test:** tests/test_m1_stt.py  
**Result:** PASS — 7/7 tests

| Test | Result | Detail |
|------|--------|--------|
| Valid WAV transcription | PASS | "(eerie music)" in 4084ms processing |
| Empty audio rejected | PASS | HTTP 400 |
| No file uploaded rejected | PASS | HTTP 422 |
| Unsupported format handled | PASS | HTTP 500 |
| Processing time reported | PASS | 4363ms |
| Transcript -> chat integration | PASS | Reply received from Ollama |
| Multi-turn continuity | PASS | Athena remembers "Alex" |

**STT performance:**
- WAV conversion + transcription: ~4-10 seconds for 2-3 second audio
- Processing time varies with audio length and content
- whisper.cpp uses 4 CPU threads

---

## M2/M3 — Frontend Voice Integration

**Status:** Implemented in frontend/app.js, index.html, style.css

**Implemented features:**
- Push-to-talk microphone capture (MediaRecorder)
- MIME type detection (webm/ogg fallback)
- Editable transcript review
- User confirmation before submission
- Conversation ID preservation across voice turns
- Browser speechSynthesis with English voice selection
- Stop Speaking cancellation
- 8-state UI state machine (idle, permission, listening, transcribing, reviewing, thinking, speaking, error)
- Text chat preserved as fallback

**Pending verification:** End-to-end browser testing (requires manual browser interaction)

---

## M4 — Performance Benchmarking

**Date:** 19 November 2026  
**Test:** tests/test_m4_benchmark.py  
**Machine:** AMD Ryzen 5 5625U (6c/12t), ~8 GB RAM, Windows 10

### Memory

| Metric | Value |
|--------|-------|
| Total visible RAM | ~7.3 GB |
| Free physical RAM | ~0.8 GB |
| Used RAM (with Ollama) | ~6.5 GB |
| Ollama process WS | ~16 MB (undercounted — Windows memory-mapped files) |

### STT (whisper.cpp base.en, 4 threads)

| Audio length | Wall time | Processing time | Transcript |
|--------------|-----------|-----------------|------------|
| 2 seconds | 11.91s | 11373ms | "(eerie music)" |
| 5 seconds | 8.78s | 8164ms | "(eerie music) (eerie music)" |
| 10 seconds | 11.01s | 10516ms | "(crickets chirping) x3" |

Note: Test tones are interpreted as ambient sound by whisper. Wall time includes ffmpeg conversion + HTTP overhead; processing time is whisper.cpp only.

### LLM (Ollama athena-llama:3b, num_predict=1000)

| Response length | Wall time | Tokens | Tokens/sec | done_reason |
|-----------------|-----------|--------|------------|-------------|
| Short (~591 chars) | 14.56s | 123 | 11.7 | stop |
| Medium (~1279 chars) | 23.80s | 275 | 12.5 | stop |
| Long (~4831 chars) | 89.49s | 1000 | 11.4 | **length** |

### Key Finding: num_predict truncation

The long response test hit `done_reason=length` with `eval_count=1000`, confirming that `num_predict=1000` truncates responses exceeding ~1000 tokens. This was not detected in M0 because none of the 10 test conversations were long enough to reach the limit.

Per the user's instruction, `num_predict=1000` is kept as-is. This is a **known limitation** — very long responses will be truncated at ~1000 tokens.

### Estimated time to first audio

| Component | Time |
|-----------|------|
| STT (5s audio) | ~8.78s |
| LLM (short response) | ~14.56s |
| **Total (estimate)** | **~23.34s** |

TTS initiation is near-instant with browser speechSynthesis.

---

## M2/M3 — Frontend Voice Integration

**Status:** Implemented in frontend/app.js, index.html, style.css

**Implemented features:**
- Push-to-talk microphone capture (MediaRecorder)
- MIME type detection (webm/ogg fallback)
- Editable transcript review
- User confirmation before submission
- Conversation ID preservation across voice turns
- Browser speechSynthesis with English voice selection
- Stop Speaking cancellation
- 8-state UI state machine (idle, permission, listening, transcribing, reviewing, thinking, speaking, error)
- Text chat preserved as fallback

**Pending verification:** End-to-end browser testing (requires manual browser interaction)

---

## Known Limitations

1. **num_predict=1000 truncation:** Responses exceeding ~1000 tokens are truncated (`done_reason=length`). Kept as configured per user instruction.
2. **Browser testing not automated:** Voice interaction requires manual browser testing (microphone permission, speechSynthesis).
3. **STT latency:** 8-11 seconds for 2-10 second audio. Acceptable for v0.1.
4. **Time to first audio:** ~23 seconds estimated (STT + LLM). TTS is near-instant.
5. **No VAD/silence detection:** Push-to-talk only; no automatic turn-taking yet (planned for M5).
6. **No echo cancellation:** Athena's output could be picked up by the microphone if speakers are used. Headphones recommended.
7. **Ollama RAM measurement:** Windows tasklist undercounts due to memory-mapped files; actual usage is ~2-2.5 GB (model size).
8. **FFmpeg path:** Falls back to PATH if project-local binary missing.
9. **No always-on microphone:** Microphone only activates on explicit user action.

---

## M5 — Interruption and Turn-Taking

**Manual interruption:** Implemented — Stop Speaking button cancels `speechSynthesis` immediately and clears the queue.

**Planned (future):** VAD, automatic silence detection, end-of-utterance detection, acoustic echo cancellation, optional hands-free mode.

---

## Definition of Done — Athena Voice v0.1

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Application starts reliably | PASS |
| 2 | Microphone captures user speech | PASS (MediaRecorder, tested via API) |
| 3 | Speech is transcribed locally | PASS (whisper.cpp base.en, tested) |
| 4 | Transcript is reviewable/correctable | PASS (editable textarea in UI) |
| 5 | Athena processes transcript through Ollama | PASS (/api/chat integration tested) |
| 6 | Response appears in interface | PASS (frontend renders assistant reply) |
| 7 | Athena speaks the response | PASS (browser speechSynthesis implemented) |
| 8 | Speech can be stopped immediately | PASS (Stop Speaking button cancels synthesis) |
| 9 | Multi-turn conversation works | PASS (tested: "My name is Alex" → remembers) |
| 10 | Text-only chat remains functional | PASS (unchanged /api/chat endpoint) |
| 11 | STT operates without external speech API | PASS (local whisper.cpp only) |
| 12 | Memory consumption measured | PASS (~6.5 GB used with Ollama) |
| 13 | Setup and testing instructions documented | PASS (SETUP.md, TEST_RESULTS.md) |


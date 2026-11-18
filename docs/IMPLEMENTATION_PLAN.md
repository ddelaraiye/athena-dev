# Athena Implementation Plan

**Date:** 18 November 2026  
**Status:** Draft — awaiting approval before implementation

---

## 1. Existing Architecture

- **Backend:** FastAPI (`app/main.py`), config via `app/config.py` + `.env`.
- **Language model:** Ollama local chat API (`/api/chat`), model `athena-llama:3b`, `stream=false`, `num_ctx=2048`, `num_predict=1000` (code) / 500 (task doc), `temperature=0.7`.
- **Persistence:** SQLite (`data/conversations.db`), table `messages(id, conversation_id, role, content, created_at)`, synchronous `sqlite3`.
- **Frontend:** `frontend/index.html`, `app.js`, `style.css`; text-only chat, static file mount at `/`.
- **Environment:** Python 3.13.15 venv at `C:\Athena\.venv`; Ollama 0.32.15 on `localhost:11434`; Windows 10, Ryzen 5 5625U, ~8 GB RAM.

---

## 2. Proposed Architecture

Speech providers are replaceable behind clean internal modules. The existing FastAPI + Ollama + SQLite stack is preserved.

```
Microphone
  → Browser MediaRecorder (push-to-talk, user-initiated only)
  → Audio file upload (POST /api/transcribe)
  → Backend: validate type/size → temp file → convert to WAV 16kHz mono 16-bit (ffmpeg)
  → Local whisper.cpp base.en → transcript
  → Transcript returned to frontend (editable)
  → User confirms → POST /api/chat {transcript, conversation_id}
  → Existing Ollama chat → assistant response
  → Backend: save messages to SQLite
  → Frontend: render response
  → Browser speechSynthesis → speak response (cancelable, non-overlapping)
```

### New internal modules (suggested, follow project conventions)
- `app/stt.py` — Whisper.cpp invocation, temp-file handling, audio validation/conversion orchestration.
- `app/speech.py` — STT provider boundary + `/api/transcribe` route handler.
- `app/tts.py` — Placeholder for future local TTS (Piper); browser speechSynthesis stays on the frontend.
- `app/audio.py` — Audio format conversion helpers (ffmpeg wrapper).

### New endpoint
- `POST /api/transcribe` — receive uploaded audio, validate, convert, transcribe, return `{transcript, processing_time_ms}`.

### Retained endpoint
- `POST /api/chat` — unchanged contract.

### Frontend additions
- Microphone button (push-to-talk), recording indicator, editable transcript, send/confirm, stop-speaking, existing text input, per-state UI (idle / permission / listening / transcribing / reviewing / thinking / speaking / error).

---

## 3. Files to Create or Modify

### Create
| File | Purpose |
|------|---------|
| `docs/PROJECT_AUDIT.md` | This audit (done) |
| `docs/IMPLEMENTATION_PLAN.md` | This plan (done) |
| `docs/ARCHITECTURE.md` | Final architecture after implementation |
| `docs/DEVELOPMENT_LOG.md` | Chronological change log |
| `docs/TEST_RESULTS.md` | Actual test measurements |
| `docs/SETUP.md` | Installation & startup instructions |
| `app/stt.py` | Whisper.cpp STT integration |
| `app/speech.py` | STT route + provider boundary |
| `app/tts.py` | TTS placeholder / future Piper integration |
| `app/audio.py` | Audio conversion helpers |
| `tests/` | Repeatable test suite |

### Modify
| File | Change |
|------|--------|
| `app/main.py` | Add `/api/transcribe` route; improve health to verify model availability; add request validation/timeouts |
| `app/conversation.py` | Fix persistence timing; add conversation ID validation; inspect/log Ollama metadata; consider `num_predict` |
| `app/config.py` | Add STT/TTS config (whisper path, model, audio settings) |
| `frontend/index.html` | Add microphone button, transcript area, stop-speaking button, state indicators |
| `frontend/app.js` | Add MediaRecorder capture, transcript edit/confirm, speechSynthesis, state machine, error UI |
| `frontend/style.css` | Voice-state styling (recording indicator, speaking state) |
| `requirements.txt` | Add any Python deps (whisper.cpp Python bindings only if chosen) |
| `.env` | Add STT/TTS config values |

### Not to modify unless justified
- Existing `/api/chat` contract (preserve).
- Ollama model `athena-llama:3b` (do not replace without evidence).
- System prompt identity (preserve).

---

## 4. New Dependencies

| Dependency | Purpose | Installation |
|------------|---------|--------------|
| whisper.cpp (portable binary or Python binding) | Local STT, base.en | Project-local or portable; NOT global |
| ffmpeg | Audio conversion to WAV 16kHz mono 16-bit | Portable binary or system install |
| (future) Piper TTS | Local neural TTS | Evaluate in Milestone 4 only |

**Rule:** Never install globally when a project-local/portable alternative is practical. Do not install multiple speech frameworks without justification. Do not introduce paid APIs, Docker, vector DBs, or agent frameworks.

---

## 5. Installation Requirements

- Python 3.13 venv at `C:\Athena\.venv` (existing).
- `pip install -r requirements.txt` (existing deps).
- whisper.cpp binary (project-local) + base.en model.
- ffmpeg available on PATH or bundled project-local.
- Ollama running with `athena-llama:3b` pulled.
- Windows microphone access enabled.

---

## 6. Testing Strategy

### Repeatable tests
1. Existing text conversation (baseline).
2. Long responses (truncation check).
3. Ollama disconnection.
4. Missing model.
5. Microphone permission denial.
6. Audio upload failure.
7. Unsupported recording format.
8. Empty recording.
9. Whisper transcription failure.
10. Incorrect transcription.
11. TTS playback.
12. Playback cancellation.
13. Repeated submissions / duplicate retries.
14. Conversation continuity (multi-turn).
15. Offline speech processing (STT + TTS local).

### Benchmarks (actual measured values, no fabrication)
- Idle RAM.
- RAM with Ollama loaded.
- STT peak RAM.
- STT processing time.
- LLM generation time.
- TTS synthesis time.
- Total time to first audio.
- CPU utilisation.

### Test conditions documented
- Machine specs, model, audio length, ambient conditions.

---

## 7. Hardware Constraints

- ~8 GB RAM: CPU-first inference; sequential STT → LLM → TTS; avoid simultaneous heavy inference.
- Start with whisper.cpp base.en (small); avoid large Whisper models.
- Measure memory pressure before changing Ollama model residency.
- Do not assume Ollama model must be unloaded.

---

## 8. Risks and Unresolved Questions

| Risk | Mitigation |
|------|------------|
| whisper.cpp not available / hard to build on Windows | Use portable binary; evaluate Python binding as fallback |
| ffmpeg not installed | Bundle portable ffmpeg or use system install; validate early |
| 8 GB RAM pressure with STT + Ollama | Sequential processing; measure peak RAM; use base.en only |
| Browser audio MIME type inconsistency | Check `MediaRecorder.isTypeSupported()`; handle webm/ogg/wav |
| Mid-sentence truncation cause unknown | Milestone 0 measures Ollama metadata before any voice work |
| `num_predict` discrepancy (500 vs 1000) | Confirm with owner during Milestone 0 |
| Microphone permission denied | Graceful degradation to text-only chat; clear error UI |
| Python 3.13 compatibility of speech packages | Verify before installing; prefer portable binaries |

### Unresolved questions (require owner input)
1. Confirm `num_predict`: 500 (task doc) or 1000 (current code).
2. Confirm venv location remains `C:\Athena\.venv`.
3. Is `ffmpeg` available on the machine?
4. Is whisper.cpp portable binary acceptable, or preferred Python binding?
5. Approval to proceed to implementation.

---

## 9. Milestones (in order)

- **M0 — Stabilise text engine:** Measure Ollama metadata across 10 conversations; confirm truncation cause; fix confirmed defects only; text chat intact.
- **M1 — Independent STT:** Microphone capture + `POST /api/transcribe` + whisper.cpp; spoken sentence → accurate transcript, no Ollama call.
- **M2 — Integrate speech with conversation:** Editable transcript + user confirmation → `/api/chat`; multi-turn works; text chat preserved.
- **M3 — Speech output:** Browser speechSynthesis; voice discovery/selection; stop button; queue management; no overlapping speech.
- **M4 — Performance:** Benchmark; evaluate Piper only if measured; implement only measured improvements.
- **M5 — Interruption:** Cancel playback, stop queue, new recording, prevent Athena echo; then evaluate VAD/silence/echo cancellation optionally.

---

## 10. Definition of Done (Athena Voice v0.1)

1. Application starts reliably.
2. Microphone captures user speech.
3. Speech is transcribed locally.
4. Transcript is reviewable/correctable.
5. Athena processes transcript through Ollama.
6. Response appears in interface.
7. Athena speaks the response.
8. Speech can be stopped immediately.
9. Multi-turn conversation works.
10. Text-only chat remains functional.
11. STT operates without external speech API.
12. Memory consumption measured and acceptable.
13. Setup and testing instructions documented.

---

## 11. Immediate Next Step

**This plan is presented for your approval.** No substantial code changes will be made until you approve. Once approved, implementation begins at Milestone 0, incrementally, with tests and documentation after each milestone.

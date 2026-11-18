# Athena Voice — Architecture

**Version:** 0.1.0 (M1 complete)  
**Status:** Working voice-first local AI companion

---

## 1. Architecture Overview

Athena Voice is a local-first, voice-first personal AI companion. The design
keeps speech recognition, language generation, and speech synthesis independent
behind replaceable provider boundaries, while preserving the existing FastAPI +
Ollama + SQLite text chat stack.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (Frontend)                       │
│                                                                 │
│  Microphone  →  MediaRecorder  →  Audio blob  →  /api/transcribe│
│       ↓                                                    ↓     │
│  Editable transcript ─────────────────────────→  /api/chat      │
│       ↓                                                    ↓     │
│  speechSynthesis  ←  Assistant response  ←  Ollama /api/chat    │
│                                                                 │
│  Text input ─────────────────────────────────→  /api/chat       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend                          │
│                                                                 │
│  POST /api/transcribe  →  audio.py  →  ffmpeg  →  whisper.cpp   │
│         ↓                                      (local STT)      │
│  POST /api/chat      →  conversation.py  →  Ollama /api/chat    │
│                                                                 │
│  SQLite: messages(conversation_id, role, content, created_at)   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Flow (Voice)

```
1. User clicks & holds microphone button
2. Browser: MediaRecorder captures audio (push-to-talk only)
3. User releases button → recording stops
4. Frontend: POST /api/transcribe {audio blob}
5. Backend (speech.py):
   a. Validate file type/size (audio.py)
   b. Save to temp file
   c. Convert to WAV 16 kHz mono 16-bit PCM (ffmpeg)
   d. Transcribe with whisper.cpp base.en (stt.py)
   e. Delete temp file
6. Backend: Return {transcript, processing_time_ms}
7. Frontend: Display editable transcript
8. User clicks Send to Athena
9. Frontend: POST /api/chat {transcript, conversation_id}
10. Backend (conversation.py):
    a. Load last 12 messages from SQLite
    b. Build [system, history, user] prompt
    c. POST Ollama /api/chat (stream=false)
    d. Save user + assistant messages to SQLite
    e. Return {conversation_id, reply, ollama_metadata}
11. Frontend: Display assistant response
12. Frontend: speechSynthesis.speak(reply) (English voice)
13. User can click Stop Speaking to cancel playback
```

---

## 3. Data Flow (Text)

```
1. User types message in text box
2. Frontend: POST /api/chat {message, conversation_id}
3. Backend: Same as steps 10-11 above
4. Frontend: Display assistant response
5. Frontend: speechSynthesis.speak(reply)
```

Text chat is preserved as a fallback and works identically to before.

---

## 4. Components

### 4.1 Frontend (`frontend/`)

| File | Responsibility |
|------|---------------|
| `index.html` | Markup: voice panel, mic button, transcript box, stop-speaking, text composer |
| `app.js` | MediaRecorder capture, /api/transcribe, /api/chat, speechSynthesis, 8-state UI state machine |
| `style.css` | Styles: recording indicator, speaking orb, transcript box, voice error |

### 4.2 Backend (`app/`)

| File | Responsibility |
|------|---------------|
| `main.py` | FastAPI app, routes (`/api/health`, `/api/chat`, `/api/transcribe`) |
| `config.py` | `.env` loading, path constants |
| `conversation.py` | SQLite persistence, Ollama chat, metadata capture |
| `audio.py` | Audio validation, ffmpeg conversion to WAV 16k mono 16-bit |
| `stt.py` | whisper.cpp `main.exe` invocation, transcript parsing |
| `speech.py` | `/api/transcribe` endpoint, temp file lifecycle |

### 4.3 Portable Tools (`tools/`, gitignored)

| Tool | Purpose | Source |
|------|---------|--------|
| `ffmpeg.exe` | Audio format conversion | gyan.dev FFmpeg 9.0 |
| `main.exe` | whisper.cpp STT CLI | regstuff/whisper.cpp_windows |
| `ggml-base.en.bin` | Whisper English base model | Hugging Face ggerganov/whisper.cpp |

---

## 5. Provider Boundaries (Replaceable)

| Layer | Current Provider | Replace With |
|-------|-----------------|--------------|
| STT | whisper.cpp base.en (local, CPU) | Whisper large, faster-whisper, etc. |
| LLM | Ollama `athena-llama:3b` (local, CPU) | Any Ollama-compatible model |
| TTS | Browser speechSynthesis | Piper TTS (evaluated in M4) |
| Audio conversion | ffmpeg | Any WAV conversion tool |
| Persistence | SQLite | (not planned — no vector DBs) |

---

## 6. State Machine (Frontend)

| State | Trigger | Next State |
|-------|---------|------------|
| idle | App load / after cycle completes | — |
| permission | Mic button mousedown | listening or error |
| listening | Microphone stream active | transcribing |
| transcribing | Audio uploaded to /api/transcribe | reviewing |
| reviewing | Transcript displayed (editable) | thinking or idle (cancel) |
| thinking | Send to /api/chat | speaking |
| speaking | speechSynthesis active | idle |
| error | Any failure | idle (user recovers) |

---

## 7. Constraints & Design Decisions

| Constraint | Decision |
|------------|----------|
| ~8 GB RAM | Sequential processing: STT → LLM → TTS, never simultaneous |
| CPU-first inference | whisper.cpp base.en, Ollama llama 3B Q4_K_M, no GPU |
| No always-on mic | Push-to-talk only, explicit user gesture |
| No external APIs | All STT/LLM/TTS local (TTS is browser-based but local) |
| No Docker, vector DBs, agent frameworks | Simple SQLite + FastAPI + Ollama |
| Replaceable providers | STT, LLM, TTS behind clean module boundaries |
| No model replacement without evidence | `athena-llama:3b` kept as default |

---

## 8. Performance Profile (Measured, M1)

| Metric | Value |
|--------|-------|
| WAV conversion + STT (2-3s audio) | 4-10 seconds |
| LLM generation (short response) | 2-6 seconds |
| LLM generation (long response) | 30-60 seconds |
| Memory (Ollama loaded) | ~2.5 GB (model) + overhead |
| Memory (STT, base.en) | ~200-500 MB |

---

## 9. Future Evolution (M4-M5)

- **M4:** Benchmark, evaluate Piper TTS, optimize time-to-first-audio
- **M5:** Manual interruption (already works via Stop Speaking), VAD,
  silence detection, echo cancellation

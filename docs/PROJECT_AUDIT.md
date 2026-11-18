# Athena Project Audit

**Date:** 18 November 2026  
**Auditor:** Senior Software Engineer (OpenCode agent)  
**Status:** Complete — awaiting approval before implementation

---

## 1. Directory Structure

```
C:\Athena\
├── .git/
├── .venv\                    # Python 3.13 virtual environment
├── app\
│   ├── __pycache__\
│   ├── config.py             # Configuration / env loading
│   ├── conversation.py       # SQLite persistence + Ollama chat
│   └── main.py               # FastAPI entry point + routes
├── data\
│   └── conversations.db      # SQLite conversation store
├── docs\                     # (empty — documentation to be created)
├── frontend\
│   ├── app.js                # Frontend chat logic
│   ├── index.html            # Frontend markup
│   └── style.css             # Frontend styles
├── tests\                    # (empty — no tests exist)
├── .env                      # Runtime configuration (gitignored)
├── .gitignore
├── Modelfile                 # Ollama model definition
├── requirements.txt          # Python dependencies
└── Athena-improvement-review_20261118-2338.json  # Prior review notes (untracked)
```

---

## 2. File Responsibilities

### `app/main.py` — FastAPI backend entry point
- Creates the FastAPI application (`title=ATHENA`, version `0.1.0`).
- `lifespan` context manager: calls `initialise_database()` on startup.
- `ChatRequest` Pydantic model: `message` (min 1, max 10000 chars), optional `conversation_id`.
- `GET /api/health`: checks Ollama `/api/tags`, returns `{status, ollama, model}`.
- `POST /api/chat`: resolves conversation ID, calls `generate_response`, returns `{conversation_id, reply}`. Handles `httpx.HTTPError` (503) and `KeyError/ValueError` (502).
- Mounts `frontend/` as static files at `/`.

### `app/config.py` — Configuration
- Loads `.env` from project root via `python-dotenv`.
- `APP_NAME` (default "ATHENA"), `OLLAMA_BASE_URL` (default `http://localhost:11434`), `OLLAMA_MODEL` (default `athena-llama:3b`), `OLLAMA_NUM_CTX` (default 2048).
- `DATABASE_PATH` = `data/conversations.db`, `FRONTEND_DIR` = `frontend`.

### `app/conversation.py` — Persistence + language processing
- `SYSTEM_PROMPT`: defines Athena's identity and behaviour.
- `initialise_database()`: creates `messages` table (`id`, `conversation_id`, `role`, `content`, `created_at`) and index `idx_conversation`.
- `save_message(conversation_id, role, content)`: inserts one message (synchronous `sqlite3`).
- `get_history(conversation_id, limit=12)`: returns last 12 messages ordered chronologically (synchronous `sqlite3`).
- `generate_response(conversation_id, user_message)` (async): builds message list `[system, *history, user]`, calls Ollama `/api/chat` with `stream=false`, `num_ctx=2048`, `num_predict=1000`, `temperature=0.7`, 180 s timeout. Saves user + assistant messages **after** receiving the response. Returns assistant content.
- `create_conversation_id()`: returns `uuid4`.

### `frontend/index.html` — Frontend markup
- Header with Athena "orb" logo, identity, status text ("Initialising..."), "New conversation" button.
- `#messages` section with a default welcome card.
- `#chat-form`: textarea + Send button.
- Footer: "LOCAL SESSION — ATHENA 0.1".
- Loads `/style.css` and `/app.js`.

### `frontend/app.js` — Frontend logic
- `addMessage(role, content)`: appends a message div, removes welcome card, scrolls to bottom.
- `checkHealth()`: polls `/api/health`, updates status text.
- Form submit handler: sends `{message, conversation_id}` to `/api/chat`, displays reply, stores `conversation_id`.
- "New conversation" button: resets `conversationId` and restores welcome card.
- No microphone, no speech, no transcription, no TTS, no playback controls.

### `frontend/style.css` — Frontend styles
- Dark theme (`#090e18` background), blue accent (`#2388c8`), Segoe UI font.
- Responsive max-width container, message bubbles, composer layout.

### `requirements.txt` — Python dependencies
- `fastapi==0.163.1`, `uvicorn==0.54.0`, `httpx==0.28.1`, `pydantic==2.14.3`, `python-dotenv==1.2.4`, plus transitive packages. No speech/audio dependencies.

### `.env` — Runtime config
- `APP_NAME=ATHENA`, `OLLAMA_BASE_URL=http://localhost:11434`, `OLLAMA_MODEL=athena-llama:3b`, `OLLAMA_NUM_CTX=2048`.

### `Modelfile`
- `FROM llama3.2:3b`, `PARAMETER num_ctx 2048`. Defines the `athena-llama:3b` model in Ollama.

### `data/conversations.db`
- Existing SQLite database with the `messages` schema.

---

## 3. Environment Verification

| Item | Finding |
|------|---------|
| Python | 3.13.15 (venv at `C:\Athena\.venv`) |
| Ollama | 0.32.15, running on `localhost:11434` |
| Model `athena-llama:3b` | Present, ~2.02 GB, Q4_K_M, llama family, ctx 131072 |
| Other models | `llama3.2:3b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, `gemma:2b`, `tinyllama`, `hermes-local:latest` |
| App startup | Starts successfully; health endpoint reachable |
| Git | One commit (`b39c7ab` initial env); `app/`, `frontend/`, `.env`, `Modelfile` are untracked |

---

## 4. Identified Issues and Defects

### 4.1 Response truncation (unconfirmed — prior report)
A previous response terminated mid-sentence; cause not established. Candidates:
- `num_predict=1000` in `conversation.py` (the task description states `num_predict=500` — there is a discrepancy between documented config and actual code).
- Ollama `done_reason` (length, stop, etc.) is not inspected or logged.
- Frontend renders `result.reply` verbatim; no indication whether the response was truncated.

**Action:** Measure Ollama metadata (`done`, `done_reason`, `eval_count`, `eval_duration`, `total_duration`) across varied conversations (Milestone 0).

### 4.2 `num_predict` discrepancy
Task states `num_predict=500`; code uses `1000`. This should be confirmed as intentional or corrected during stabilisation.

### 4.3 Synchronous database calls inside async handlers
`initialise_database()`, `save_message()`, and `get_history()` use blocking `sqlite3` calls directly inside async FastAPI handlers and the lifespan. On a 6-core CPU this is a minor concern now but blocks the event loop and should be addressed as the system grows (no async SQLite driver is currently used).

### 4.4 Message persistence timing
User and assistant messages are saved **after** the Ollama response arrives. If the Ollama call fails, the user message is never persisted, breaking continuity. If the assistant save fails after the user save, the history is asymmetric.

### 4.5 No conversation ID validation
`conversation_id` is accepted as-is from the client with no format or existence validation. A malformed or foreign ID would be stored without error.

### 4.6 Health-check accuracy
`GET /api/health` only verifies Ollama responds to `/api/tags`. It does **not** verify the configured model (`athena-llama:3b`) is actually available or loaded. A missing model would report "online" while chat would fail.

### 4.7 No streaming
`stream=false` means the client waits for the full response before rendering anything. This hurts perceived latency for voice, where time-to-first-audio matters.

### 4.8 Frontend limitations
- No microphone capture, no transcription, no TTS, no playback controls.
- Only a status line (`#status`) for errors; no dedicated error UI, no per-state indicators (listening, transcribing, thinking, speaking).
- No editable transcript; messages are appended directly.
- No conversation-ID display or management.
- No protection against duplicate submissions beyond the disabled Send button during a request.

### 4.9 Missing dependencies for voice
No speech-recognition, audio, or TTS packages are installed. No `ffmpeg` or `whisper.cpp` presence has been verified yet.

### 4.10 No tests
`tests/` is empty. No repeatable test suite exists.

### 4.11 Untracked project files
`app/`, `frontend/`, `.env`, and `Modelfile` are not committed to Git (only `.gitignore` and `requirements.txt` are tracked).

---

## 5. Current Data Flow (Text-Only)

```
User types message
    → Frontend POST /api/chat {message, conversation_id}
    → Backend: load last 12 messages from SQLite
    → Build [system, history, user] prompt
    → POST Ollama /api/chat (stream=false)
    → Ollama returns full assistant text
    → Backend: save user + assistant messages to SQLite
    → Frontend: render assistant reply
```

No audio, no STT, no TTS exists.

---

## 6. Hardware & Resource Constraints (Observed)

- **Machine:** Windows 10 Home, AMD Ryzen 5 5625U (6c/12t), ~8 GB RAM, integrated Radeon.
- **Ollama model `athena-llama:3b`:** ~2.02 GB on disk; CPU inference (ggml runner).
- **RAM budget:** ~8 GB total. Must avoid simultaneous heavy STT + LLM + TTS. Sequential processing preferred.
- **Python:** 3.13.15 in a project-local venv. Prefer project-local or portable binaries; avoid global installs.

---

## 7. What Works Today

- FastAPI server starts and serves the frontend.
- `GET /api/health` confirms Ollama connectivity.
- `POST /api/chat` returns a model response.
- Conversation history persists in SQLite across requests (within the same conversation ID).
- Text chat is functional end-to-end.

---

## 8. What Does Not Exist (Voice System)

| Component | Status |
|-----------|--------|
| Microphone capture (getUserMedia / MediaRecorder) | Missing |
| Local STT (whisper.cpp) | Missing |
| `POST /api/transcribe` endpoint | Missing |
| Editable transcript UI | Missing |
| Speech output (speechSynthesis / Piper) | Missing |
| Playback controls (stop, queue) | Missing |
| Interruption / turn-taking | Missing |
| Voice-specific error states | Missing |

---

## 9. Recommended Next Steps (Milestone 0)

Per the task requirements, before implementing voice:
1. Record Ollama metadata (`done`, `done_reason`, `total_duration`, `load_duration`, `prompt_eval_count`, `eval_count`, `eval_duration`) across ten varied conversations.
2. Establish whether mid-sentence termination is caused by `num_predict`, context overflow, stop sequences, model termination, frontend rendering, or backend handling.
3. Fix only confirmed defects.
4. Confirm text chat remains intact.

Then proceed to voice implementation milestones 1–5.

---

## 10. Open Questions for the Owner

1. Confirm `num_predict` should be 500 (per task description) or 1000 (current code).
2. Confirm the venv at `C:\Athena\.venv` should remain the active environment.
3. Confirm whether `ffmpeg` is available on the machine (needed for audio conversion in STT).
4. Confirm whether `whisper.cpp` (or a portable binary) is acceptable to install, or whether a Python STT package is preferred.
5. Approve proceeding to implementation after reviewing this audit and the implementation plan.

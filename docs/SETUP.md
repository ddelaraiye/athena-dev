# Athena Voice — Setup & Startup Guide

**Version:** 0.1.0 (M1 complete)  
**Platform:** Windows 10, Python 3.13, Ollama local  
**All processing is local — no external APIs, no cloud dependencies.**

---

## 1. Prerequisites

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.13.15 | Project venv at `C:\Athena\.venv` |
| Ollama | 0.32.15 | Running on `http://localhost:11434` |
| Model | `athena-llama:3b` | Must be pulled in Ollama |
| FFmpeg | 9.0 | Portable, project-local |
| whisper.cpp | v0.0.2 | Windows x64 build, project-local |
| Whisper model | base.en | ~142 MB, project-local |

---

## 2. First-Time Installation

### 2.1 Python environment

The project uses a virtual environment at `C:\Athena\.venv`. If it doesn't exist:

```cmd
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` includes `python-multipart` (needed for file uploads).

### 2.2 Ollama

Install Ollama from https://ollama.com, then pull the model:

```cmd
ollama pull athena-llama:3b
# or create it from the Modelfile:
ollama create athena-llama:3b -f Modelfile
```

Verify it's available:
```cmd
curl http://localhost:11434/api/tags
```

Ollama must be running before starting Athena.

### 2.3 Portable audio tools (project-local)

Download and place the following under `C:\Athena\tools\`:

**FFmpeg** (`tools/ffmpeg/bin/ffmpeg.exe`):
- From https://www.gyan.dev/ffmpeg/builds/ or via winget (`winget install Gyan.FFmpeg`)
- Copy `ffmpeg.exe` to `tools/ffmpeg/bin/`

**whisper.cpp** (`tools/whisper.cpp/main.exe`, `whisper.dll`):
- From https://github.com/regstuff/whisper.cpp_windows (pre-built Windows x64)
- Extract `main.exe` and `whisper.dll` to `tools/whisper.cpp/`

**Whisper base.en model** (`tools/whisper.cpp/models/ggml-base.en.bin`):
- From https://huggingface.co/ggerganov/whisper.cpp (resolve `main/ggml-base.en.bin`)
- Place at `tools/whisper.cpp/models/ggml-base.en.bin`

> The `tools/` directory is gitignored (binaries are large). Each developer
> downloads these once. The expected structure is documented here so the
> project can be recreated on another machine.

Expected `tools/` layout:
```
tools/
├── ffmpeg/
│   └── bin/
│       └── ffmpeg.exe
└── whisper.cpp/
    ├── main.exe
    ├── whisper.dll
    ├── stream.exe
    ├── SDL2.dll
    └── models/
        └── ggml-base.en.bin
```

### 2.4 Verify installation

```cmd
# FFmpeg
.\tools\ffmpeg\bin\ffmpeg.exe -version

# whisper.cpp
.\tools\whisper.cpp\main.exe --help

# Ollama model
curl http://localhost:11434/api/tags
```

---

## 3. Starting Athena

### 3.1 Start Ollama (if not running)

```cmd
ollama serve
```

### 3.2 Start Athena

From `C:\Athena`:

```cmd
.\.venv\Scripts\activate
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

### 3.3 Open the frontend

Open your browser to: `http://127.0.0.1:8765/`

---

## 4. Using Athena Voice

### Text chat (always available)

1. Type in the text box at the bottom and press **Send** or Enter.
2. Athena replies in the conversation area.
3. Multi-turn context is preserved via conversation ID.

### Voice chat (push-to-talk)

1. **Click and hold** the microphone button (� Hold to speak).
2. Speak your question or statement.
3. **Release** the button to stop recording.
4. Athena transcribes locally and shows the transcript in an editable box.
5. Review and correct the transcript if needed.
6. Click **Send to Athena** to submit.
7. Athena responds via Ollama and speaks the reply.
8. Click **Stop Speaking** at any time to cancel playback.

### States

The status indicator shows: Idle → Permission → Listening → Transcribing → Reviewing → Thinking → Speaking → Error.

---

## 5. Configuration

Edit `.env` (not committed to git):

```env
APP_NAME=ATHENA
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=athena-llama:3b
OLLAMA_NUM_CTX=2048
```

Edit `app/config.py` for code-level constants (whisper threads, audio limits).

---

## 6. Directory Layout

```
C:\Athena\
├── app/
│   ├── main.py           # FastAPI entry point + routes
│   ├── config.py         # Configuration (.env loading)
│   ├── conversation.py   # SQLite persistence + Ollama chat
│   ├── audio.py          # Audio validation + ffmpeg conversion
│   ├── stt.py            # whisper.cpp STT integration
│   └── speech.py         # /api/transcribe endpoint handler
├── data/
│   └── conversations.db  # SQLite (gitignored)
├── docs/
│   ├── PROJECT_AUDIT.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT_LOG.md
│   ├── TEST_RESULTS.md
│   └── SETUP.md
├── frontend/
│   ├── index.html        # Voice UI markup
│   ├── app.js            # Voice + text frontend logic
│   └── style.css         # Styles incl. voice states
├── tests/
│   ├── test_m0_text_engine.py
│   ├── test_m1_stt.py
│   └── m0_results.json
├── tools/                # (gitignored - portable binaries)
│   ├── ffmpeg/bin/ffmpeg.exe
│   └── whisper.cpp/
│       ├── main.exe
│       └── models/ggml-base.en.bin
├── .env                  # (gitignored - runtime config)
├── .gitignore
├── Modelfile
├── requirements.txt
└── README.md
```

---

## 7. Troubleshooting

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| Server won't start | Missing `python-multipart` | `pip install python-multipart` |
| /api/transcribe returns 502 | whisper.cpp or model missing | Check `tools/whisper.cpp/` paths |
| /api/transcribe returns 500 | ffmpeg missing | Check `tools/ffmpeg/bin/ffmpeg.exe` |
| Microphone button does nothing | Browser blocked mic | Click the lock icon in the address bar, allow mic |
| Athena doesn't speak | No voices installed | Check Windows voice settings; use text chat as fallback |
| Empty transcript | Silence or noise in recording | Speak closer to microphone, try again |
| Slow transcription | base.en on CPU, 8 GB RAM | Expected; close other apps to free RAM |

---

## 8. Uninstall / Clean Start

- Delete `data/conversations.db` to clear conversation history.
- Delete `.env` to reset configuration (will be regenerated with defaults).
- The `tools/` binaries can be kept for reuse.

# Athena Voice v0.1

Athena is a local-first, voice-enabled personal AI companion. She runs entirely on your machine — no cloud APIs, no paid services, no external inference. Athena listens via your microphone, transcribes locally with Whisper, reasons through a local Ollama model, and speaks back using your browser's built-in speech synthesis.

## Project Overview

Athena transforms a text-only local chatbot into a voice-first companion. The user pushes a button to speak, reviews an editable transcript, sends it to a local language model, and hears the response spoken aloud. Everything runs locally on your hardware.

**Goals:**
- Natural voice interaction through local speech input, recognition, language-model processing, and speech output
- Privacy — all processing stays on your machine
- Continuity — conversation history persists locally in SQLite
- Text chat remains fully functional as a fallback

## Current Architecture

```
Microphone
  → Browser MediaRecorder (push-to-talk)
  → Audio file upload (POST /api/transcribe)
  → Backend: validate → convert to WAV 16 kHz mono 16-bit PCM (ffmpeg)
  → Local whisper.cpp base.en → transcript
  → Editable transcript review (frontend)
  → User confirms → POST /api/chat {transcript, conversation_id}
  → Existing FastAPI backend → Ollama /api/chat (athena-llama:3b)
  → Assistant response → Browser speechSynthesis → playback
```

### Components

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.13) |
| Language model | Ollama — `athena-llama:3b` (llama3.2:3b derivative, CPU inference) |
| Speech recognition | whisper.cpp `base.en` (portable Windows executable) |
| Audio conversion | ffmpeg 9.0 (portable) |
| Speech output | Browser `speechSynthesis` API |
| Conversation storage | SQLite (`data/conversations.db`) |
| Frontend | HTML/CSS/JavaScript (vanilla, no framework) |

## Features Implemented in v0.1

- Push-to-talk microphone capture via `MediaRecorder`
- Local speech transcription via whisper.cpp `base.en`
- Editable transcript — review and correct before submitting
- Conversation continuity — multi-turn context preserved via SQLite
- Assistant responses spoken via browser `speechSynthesis`
- Stop Speaking — cancel playback immediately
- Replay — re-hear any previous assistant response (code implemented; browser acceptance testing outstanding)
- Text chat — fully functional fallback
- 8-state UI state machine: Idle, Permission, Listening, Transcribing, Reviewing, Thinking, Speaking, Error

## Hardware & Software Requirements

**Machine tested:**
- Windows 10 Home
- AMD Ryzen 5 5625U (6 cores / 12 threads)
- ~8 GB RAM
- Integrated Radeon graphics
- CPU inference only

**Software:**
- Python 3.13.15 (project virtual environment at `C:\Athena\.venv`)
- Ollama 0.32.15 with `athena-llama:3b` model
- FFmpeg 9.0 (portable, `tools/ffmpeg/bin/ffmpeg.exe`)
- whisper.cpp (portable Windows build, `tools/whisper.cpp/main.exe`)
- Whisper `base.en` model (`tools/whisper.cpp/models/ggml-base.en.bin`, ~142 MB)

## Installation & Startup

### 1. Python environment

```cmd
cd C:\Athena
\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Ollama

Install Ollama from https://ollama.com, then:

```cmd
ollama serve
ollama pull athena-llama:3b
```

Or create the model from the included `Modelfile`:

```cmd
ollama create athena-llama:3b -f Modelfile
```

### 3. Portable audio tools

Download and place the following under `C:\Athena\tools\` (directory is gitignored):

- **ffmpeg.exe** → `tools/ffmpeg/bin/ffmpeg.exe`
- **whisper.cpp** `main.exe` + `whisper.dll` → `tools/whisper.cpp/`
- **base.en model** `ggml-base.en.bin` → `tools/whisper.cpp/models/ggml-base.en.bin`

Expected layout:

```
tools/
├── ffmpeg/
│   └── bin/
│       └── ffmpeg.exe
└── whisper.cpp/
    ├── main.exe
    ├── whisper.dll
    └── models/
        └── ggml-base.en.bin
```

### 4. Start Athena

```cmd
cd C:\Athena
\.venv\Scripts\activate
\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Then open: `http://127.0.0.1:8765/`

## Known Limitations

- **`num_predict=1000` truncation:** Responses exceeding ~1000 tokens (~4,800 characters) are truncated by Ollama with `done_reason=length`. Kept as configured.
- **STT latency:** 8–12 seconds for 2–10 seconds of audio on the test hardware.
- **Estimated time to first audio:** ~23 seconds (STT + LLM), calculated not measured end-to-end.
- **Memory:** ~6.5 GB of ~7.3 GB RAM used with Ollama loaded on the test machine.
- **Replay browser testing:** The Replay feature is implemented in code but **has not been verified in a browser**. Browser acceptance testing remains outstanding.
- **Speech recognition accuracy:** Verified using synthetic sine-wave audio for pipeline testing; not yet verified with real human speech.
- **No VAD/silence detection:** Push-to-talk only; microphone activates on explicit user gesture.
- **No echo cancellation:** Headphones recommended when using speakers.
- **Browser-dependent TTS:** Speech output quality and available voices depend on the browser and Windows voice configuration.

## Project Status

**Athena Voice v0.1 — Release candidate.** Core voice loop is implemented and API-level tests pass (7/7 verification tests, 7/7 STT tests, 12/12 text-engine turns). Browser-based end-to-end testing with real human speech remains outstanding.

## Repository Contents

```
app/              FastAPI backend (main.py, conversation.py, config.py, audio.py, stt.py, speech.py)
frontend/         HTML/CSS/JavaScript UI
tests/            Verification test scripts
docs/             Architecture, audit, setup, test results, development log
tools/            (gitignored) Portable ffmpeg and whisper.cpp binaries
data/             (gitignored) SQLite conversation database
.env              (gitignored) Local runtime configuration
.venv/            (gitignored) Python virtual environment
```

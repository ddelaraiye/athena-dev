"""Speech-to-text integration using local whisper.cpp.

Invokes the whisper.cpp `main.exe` CLI to transcribe WAV audio files
using the base.en model. All processing is local and CPU-based.
"""

import logging
import re
import subprocess
import tempfile
from pathlib import Path

from app.audio import (
    AudioError,
    convert_to_wav_16k_mono,
    cleanup_temp_file,
)
from app.config import ROOT_DIR

logger = logging.getLogger("athena.stt")

# Project-local whisper.cpp executable
WHISPER_EXE = ROOT_DIR / "tools" / "whisper.cpp" / "main.exe"
WHISPER_MODEL = ROOT_DIR / "tools" / "whisper.cpp" / "models" / "ggml-base.en.bin"

# Number of CPU threads for whisper (leave some headroom for Ollama)
WHISPER_THREADS = 4


class STTError(Exception):
    """Raised when speech-to-text transcription fails."""


def transcribe_wav(wav_path: Path) -> tuple[str, float]:
    """Transcribe a WAV file using whisper.cpp base.en.

    Args:
        wav_path: Path to a WAV file (16 kHz mono 16-bit PCM preferred).

    Returns:
        Tuple of (transcript_text, processing_time_seconds).

    Raises:
        STTError: If whisper.exe is missing, the model is missing, or
            transcription fails.
    """
    if not WHISPER_EXE.exists():
        raise STTError(
            f"whisper.cpp executable not found at {WHISPER_EXE}. "
            "Download a portable Windows build and place it at tools/whisper.cpp/main.exe."
        )

    if not WHISPER_MODEL.exists():
        raise STTError(
            f"Whisper model not found at {WHISPER_MODEL}. "
            "Download ggml-base.en.bin to tools/whisper.cpp/models/."
        )

    import time

    start = time.perf_counter()

    cmd = [
        str(WHISPER_EXE),
        "-m", str(WHISPER_MODEL),
        "-f", str(wav_path),
        "-t", str(WHISPER_THREADS),
        "-l", "en",
        "-nt",  # no timestamps
    ]

    logger.info(
        "Transcribing with whisper.cpp: model=%s file=%s threads=%d",
        WHISPER_MODEL.name,
        wav_path.name,
        WHISPER_THREADS,
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise STTError("Whisper transcription timed out.") from exc
    except FileNotFoundError as exc:
        raise STTError("whisper.cpp executable not found.") from exc

    elapsed = time.perf_counter() - start

    if result.returncode != 0:
        logger.error(
            "whisper.cpp failed (rc=%d): %s",
            result.returncode,
            result.stderr.strip()[:500],
        )
        raise STTError(
            f"Whisper transcription failed (exit {result.returncode})."
        )

    transcript = _parse_whisper_output(result.stdout)

    logger.info(
        "Whisper transcription complete: %.3fs, %d chars",
        elapsed,
        len(transcript),
    )

    return transcript, elapsed


def _parse_whisper_output(stdout: str) -> str:
    """Extract plain transcript text from whisper.cpp stdout.

    whisper.cpp prints each segment with optional timestamps. We strip
    timestamps and join the text.
    """
    lines = stdout.splitlines()
    text_parts = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # whisper.cpp output format: "[00:00.000 --> 00:05.000]  text"
        # or with -nt: just "text"
        # Remove leading timestamp brackets if present
        cleaned = re.sub(r"^\[\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}\.\d{3}\]\s*", "", line)
        cleaned = cleaned.strip()

        if cleaned:
            text_parts.append(cleaned)

    transcript = " ".join(text_parts).strip()
    return transcript


def transcribe_audio_file(
    input_path: Path, content_type: str | None = None
) -> tuple[str, float]:
    """Validate, convert, and transcribe an audio file.

    This is the full STT pipeline: validate input -> convert to WAV
    16kHz mono -> transcribe with whisper.cpp -> cleanup temp files.

    Args:
        input_path: Path to the uploaded audio file.
        content_type: MIME type from the upload (for diagnostics only).

    Returns:
        Tuple of (transcript_text, total_processing_time_seconds).

    Raises:
        STTError: If any step fails.
    """
    import time

    total_start = time.perf_counter()
    temp_wav: Path | None = None

    try:
        # Convert to Whisper format (WAV 16 kHz mono 16-bit PCM)
        wav_path = convert_to_wav_16k_mono(input_path)

        # Track whether we created a temp file (for cleanup)
        temp_wav = wav_path if wav_path != input_path else None

        # Transcribe
        transcript, stt_elapsed = transcribe_wav(wav_path)

        total_elapsed = time.perf_counter() - total_start
        logger.info(
            "STT pipeline complete: %.3fs total (whisper: %.3fs)",
            total_elapsed,
            stt_elapsed,
        )

        return transcript, total_elapsed

    finally:
        # Always clean up temporary WAV files
        if temp_wav is not None:
            cleanup_temp_file(temp_wav)

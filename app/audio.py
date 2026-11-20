"""Audio conversion utilities for Athena Voice.

Handles format validation, conversion to Whisper's required format
(WAV 16 kHz mono 16-bit PCM), and temporary file cleanup using ffmpeg.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from app.config import ROOT_DIR

logger = logging.getLogger("athena.audio")

# Project-local ffmpeg binary (falls back to PATH if not present)
FFMPEG_PATH = ROOT_DIR / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
if not FFMPEG_PATH.exists():
    FFMPEG_PATH = Path("ffmpeg")  # fall back to PATH

# Whisper target audio format
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # 16-bit PCM

# Allowed input MIME types (browser MediaRecorder may produce various)
ALLOWED_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/webm",
    "audio/ogg",
    "audio/opus",
    "audio/mpeg",
    "audio/mp4",
    "audio/aac",
    "audio/flac",
}

# Maximum upload size: 25 MB
MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024


class AudioError(Exception):
    """Raised when audio processing fails."""


def validate_audio_file(file_bytes: bytes, content_type: str | None = None) -> None:
    """Validate uploaded audio file type and size.

    Args:
        file_bytes: Raw audio file contents.
        content_type: MIME type from the upload (may be None or unreliable).

    Raises:
        AudioError: If the file is empty, too large, or of an unsupported type.
    """
    if not file_bytes:
        raise AudioError("Empty audio upload.")

    if len(file_bytes) > MAX_AUDIO_SIZE_BYTES:
        raise AudioError(
            f"Audio file too large: {len(file_bytes)} bytes "
            f"(max {MAX_AUDIO_SIZE_BYTES} bytes)."
        )

    # Quick WAV header check: reject WAV files with no audio data chunk.
    # Browser recordings always contain at least some data when speech occurs.
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WAVE":
        # Find the 'data' chunk and check its size
        pos = 12
        while pos + 8 <= len(file_bytes):
            chunk_id = file_bytes[pos:pos + 4]
            chunk_size = int.from_bytes(file_bytes[pos + 4:pos + 8], "little")
            if chunk_id == b"data":
                if chunk_size == 0:
                    raise AudioError("Empty audio recording: no audio data.")
                break
            pos += 8 + chunk_size

    # Browser MIME types are unreliable; we validate by attempting conversion
    # rather than rejecting outright. content_type is logged for diagnostics.
    logger.debug(
        "Audio upload: %d bytes, content_type=%s",
        len(file_bytes),
        content_type,
    )


def convert_to_wav_16k_mono(
    input_path: Path, output_path: Path | None = None
) -> Path:
    """Convert an audio file to WAV 16 kHz mono 16-bit PCM using ffmpeg.

    Args:
        input_path: Path to the source audio file.
        output_path: Optional path for the converted WAV file. If not
            provided, a temporary file is created.

    Returns:
        Path to the converted WAV file.

    Raises:
        AudioError: If ffmpeg is not found or conversion fails.
    """
    if not FFMPEG_PATH.exists():
        raise AudioError(
            f"ffmpeg not found at {FFMPEG_PATH}. "
            "Install ffmpeg or place a portable binary at tools/ffmpeg/bin/ffmpeg.exe."
        )

    if output_path is None:
        fd, tmp_name = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        output_path = Path(tmp_name)

    cmd = [
        str(FFMPEG_PATH),
        "-y",  # overwrite output
        "-i", str(input_path),
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", str(TARGET_CHANNELS),
        "-sample_fmt", "s16",  # 16-bit PCM
        str(output_path),
    ]

    logger.info(
        "Converting audio: %s -> %s (16kHz mono 16-bit PCM)",
        input_path,
        output_path,
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioError("Audio conversion timed out.") from exc
    except FileNotFoundError as exc:
        raise AudioError("ffmpeg executable not found.") from exc

    if result.returncode != 0:
        logger.error(
            "ffmpeg conversion failed (rc=%d): %s",
            result.returncode,
            result.stderr.strip()[:500] if result.stderr else "",
        )
        raise AudioError(
            f"Audio conversion failed: {result.stderr.strip()[:200] if result.stderr else ''}"
        )

    return output_path


def cleanup_temp_file(path: Path) -> None:
    """Safely remove a temporary file if it exists.

    Never raises; errors are logged only.
    """
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        logger.warning("Failed to delete temp file %s: %s", path, exc)

"""Speech provider boundary for Athena Voice.

Handles the /api/transcribe endpoint: receives uploaded audio, validates,
converts to Whisper format, transcribes locally with whisper.cpp, and
cleans up temporary files. Returns transcript and processing time.
"""

import logging
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.audio import AudioError, cleanup_temp_file, validate_audio_file
from app.stt import STTError, transcribe_audio_file

logger = logging.getLogger("athena.speech")


async def handle_transcribe(upload: UploadFile) -> dict:
    """Process an uploaded audio file through the STT pipeline.

    Args:
        upload: FastAPI UploadFile from the client.

    Returns:
        Dict with transcript, processing_time_ms, and file metadata.

    Raises:
        HTTPException: On validation or transcription failure.
    """
    if not upload.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio file provided.",
        )

    content_type = upload.content_type
    logger.info(
        "Transcribe request: filename=%s content_type=%s",
        upload.filename,
        content_type,
    )

    # Read the uploaded file into memory
    try:
        file_bytes = await upload.read()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to read uploaded audio: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read audio upload.",
        ) from exc

    # Validate type and size
    try:
        validate_audio_file(file_bytes, content_type)
    except AudioError as exc:
        logger.warning("Audio validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Write to a temporary file for processing
    suffix = Path(upload.filename).suffix or ".bin"
    fd, tmp_name = tempfile.mkstemp(suffix=suffix)
    tmp_path = Path(tmp_name)

    try:
        # Ensure all bytes are written (os.write may write fewer bytes on some platforms)
        bytes_written = os.write(fd, file_bytes)
        while bytes_written < len(file_bytes):
            bytes_written += os.write(fd, file_bytes[bytes_written:])
    finally:
        os.close(fd)

    try:
        transcript, processing_time = transcribe_audio_file(
            tmp_path, content_type=content_type
        )

        if not transcript:
            logger.warning("Whisper returned empty transcript.")
            transcript = ""

        return {
            "transcript": transcript,
            "processing_time_ms": round(processing_time * 1000),
            "filename": upload.filename,
            "content_type": content_type,
        }

    except STTError as exc:
        logger.error("STT error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except AudioError as exc:
        logger.error("Audio processing error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    finally:
        # Always delete the temporary upload file
        cleanup_temp_file(tmp_path)

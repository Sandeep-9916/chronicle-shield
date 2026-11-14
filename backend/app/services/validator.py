import hashlib
import os
import re
from typing import Tuple
from fastapi import HTTPException, status
from backend.app.config import settings


ALLOWED_EXTENSIONS = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "pdf": "application/pdf",
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "txt": "text/plain",
}


def compute_sha256(content: bytes) -> str:
    """Computes SHA-256 server-side over raw bytes."""
    return hashlib.sha256(content).hexdigest()


def sanitize_filename(filename: str) -> str:
    """
    Sanitizes original filename: strips path traversal, removes unsafe chars,
    and returns a clean, safe filename for metadata storage.
    """
    # Extract basename only
    base = os.path.basename(filename).strip()
    # Remove control characters and quotes
    clean = re.sub(r'[\r\n\t\\/:"*?<>|]', '_', base)
    if not clean or clean.startswith('.'):
        clean = f"evidence_{clean}" if clean else "evidence_file"
    return clean[:255]


def validate_file(filename: str, content: bytes) -> Tuple[str, str]:
    """
    Validates file size, extension, and magic bytes / encoding.
    Allowed types: jpg, png, pdf, wav, mp3, m4a, and plain-text (txt) validated as UTF-8.
    Returns: (detected_mime_type, file_extension)
    """
    # 1. Size check
    if len(content) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty."
        )

    # 2. Extract extension
    parts = filename.rsplit(".", 1)
    if len(parts) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has no extension. Allowed: jpg, png, pdf, wav, mp3, m4a, txt"
        )
    ext = parts[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS.keys()))}"
        )

    # 3. Magic bytes / Content validation
    detected_mime = None

    # JPEG
    if ext in ("jpg", "jpeg"):
        if content.startswith(b"\xff\xd8\xff"):
            detected_mime = "image/jpeg"

    # PNG
    elif ext == "png":
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            detected_mime = "image/png"

    # PDF
    elif ext == "pdf":
        if content.startswith(b"%PDF"):
            detected_mime = "application/pdf"

    # WAV
    elif ext == "wav":
        if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WAVE":
            detected_mime = "audio/wav"

    # MP3
    elif ext == "mp3":
        if content.startswith(b"ID3") or (
            len(content) >= 2 and content[0] == 0xFF and (content[1] & 0xE0) == 0xE0
        ):
            detected_mime = "audio/mpeg"

    # M4A (MPEG-4 Audio container)
    elif ext == "m4a":
        if len(content) >= 12 and content[4:8] == b"ftyp":
            sub_brand = content[8:12]
            if sub_brand in (b"M4A ", b"mp42", b"isom", b"dash", b"M4B "):
                detected_mime = "audio/mp4"

    # Plain-text chat export (UTF-8 validation)
    elif ext == "txt":
        try:
            content.decode("utf-8")
            detected_mime = "text/plain"
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text file must be valid UTF-8 encoded text."
            )

    if not detected_mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File signature mismatch. The file content does not match the expected format for '{ext}'."
        )

    return detected_mime, ext


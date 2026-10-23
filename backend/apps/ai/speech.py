"""Server-side speech-to-text (optional). Browser speech recognition is the default.

Transcripts are never invented: if server STT is not configured the caller is
told so, and the candidate reviews/edits a browser or typed transcript instead.
"""
import httpx
from django.conf import settings

from .errors import AIConfigurationError, AIProviderError

LANGUAGE_CODES = {"en": "en", "ta": "ta"}


def server_stt_available() -> bool:
    return bool(settings.OPENAI_API_KEY)


def transcribe(audio_bytes: bytes, filename: str, content_type: str, language: str = "en") -> str:
    if not settings.OPENAI_API_KEY:
        raise AIConfigurationError("Server-side transcription is not configured (OPENAI_API_KEY missing).")
    try:
        r = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            data={"model": settings.OPENAI_STT_MODEL, "language": LANGUAGE_CODES.get(language, "en")},
            files={"file": (filename, audio_bytes, content_type or "audio/webm")},
            timeout=settings.AI_REQUEST_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise AIProviderError(f"Could not reach the transcription service: {exc.__class__.__name__}") from exc
    if r.status_code != 200:
        raise AIProviderError(f"Transcription error {r.status_code}: {r.text[:200]}")
    return (r.json().get("text") or "").strip()

"""Local speech-to-text via faster-whisper (CTranslate2)."""

from __future__ import annotations

from faster_whisper import WhisperModel

_model: WhisperModel | None = None


def init(
    model_size: str = "base",
    device: str = "auto",
    compute_type: str = "auto",
) -> None:
    """Load a Whisper model. Call once at startup."""
    global _model
    _model = WhisperModel(model_size, device=device, compute_type=compute_type)


def transcribe(audio_path: str, language: str | None = None) -> str:
    """Transcribe an audio file to text. Returns the full transcript."""
    if _model is None:
        raise RuntimeError("Whisper model not loaded — call init() first")
    segments, _ = _model.transcribe(audio_path, language=language, beam_size=5)
    return " ".join(seg.text.strip() for seg in segments)

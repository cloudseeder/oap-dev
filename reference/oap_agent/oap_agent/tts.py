"""Local text-to-speech via Piper TTS (ONNX neural voices)."""

from __future__ import annotations

import io
import json
import logging
import re
import wave
from pathlib import Path

log = logging.getLogger("oap.agent.tts")

_voices: dict = {}  # name -> PiperVoice instance
_default_voice: str = ""
_models_dir: str = ""


def init(model_path: str, models_dir: str = "") -> None:
    """Load the default Piper voice model. Call once at startup."""
    global _default_voice, _models_dir
    from piper.voice import PiperVoice

    name = Path(model_path).stem
    _voices[name] = PiperVoice.load(model_path)
    _default_voice = name
    _models_dir = models_dir
    log.info("Piper voice loaded: %s", name)


def _get_voice(name: str | None = None):
    """Return a cached voice, loading on demand if needed."""
    if not name or name == _default_voice:
        v = _voices.get(_default_voice)
        if v is None:
            raise RuntimeError("Piper voice not loaded — call init() first")
        return v

    if name in _voices:
        return _voices[name]

    # Try loading from models_dir
    if _models_dir:
        onnx_path = Path(_models_dir) / f"{name}.onnx"
        if onnx_path.exists():
            from piper.voice import PiperVoice
            log.info("Loading voice on demand: %s", name)
            _voices[name] = PiperVoice.load(str(onnx_path))
            return _voices[name]

    log.warning("Voice %r not found, falling back to default %r", name, _default_voice)
    return _voices[_default_voice]


def _strip_markdown(text: str) -> str:
    """Convert markdown to plain text for natural TTS output."""
    # Code blocks → remove entirely (not speakable)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Bold/italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"___(.+?)___", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    # Strikethrough
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    # Headings
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Links: [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Images: ![alt](url) → remove
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    # Unordered list markers
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    # Ordered list markers
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Blockquotes
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _make_wav_header(pcm_length: int, sample_rate: int = 22050, channels: int = 1, sample_width: int = 2) -> bytes:
    """Build a 44-byte WAV header for raw PCM data."""
    import struct
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    data_size = pcm_length
    file_size = 36 + data_size
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", file_size, b"WAVE",
        b"fmt ", 16,          # subchunk1 size
        1,                    # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,     # bits per sample
        b"data", data_size,
    )


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences for streaming synthesis."""
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def synthesize_stream(text: str, voice: str | None = None):
    """Yield per-sentence WAV bytes. Each yield is a complete mini-WAV."""
    v = _get_voice(voice)
    text = _strip_markdown(text)

    if hasattr(v, "synthesize_stream_raw"):
        # Native streaming — yields raw PCM per sentence
        sr = getattr(v.config, "sample_rate", 22050)
        for pcm_bytes in v.synthesize_stream_raw(text):
            if not pcm_bytes:
                continue
            header = _make_wav_header(len(pcm_bytes), sample_rate=sr)
            yield header + pcm_bytes
    else:
        # Fallback — synthesize each sentence individually
        for sentence in _split_sentences(text):
            buf = io.BytesIO()
            wav_file = wave.open(buf, "wb")
            v.synthesize_wav(sentence, wav_file)
            wav_file.close()
            data = buf.getvalue()
            if data:
                yield data


def synthesize(text: str, voice: str | None = None) -> bytes:
    """Synthesize text to WAV bytes using the specified (or default) voice."""
    v = _get_voice(voice)
    text = _strip_markdown(text)
    buf = io.BytesIO()
    wav_file = wave.open(buf, "wb")
    v.synthesize_wav(text, wav_file)
    wav_file.close()
    data = buf.getvalue()
    log.info("Synthesized %d bytes for %d chars (voice=%s)", len(data), len(text), voice or _default_voice)
    return data


def list_voices(models_dir: str) -> list[dict]:
    """Scan a directory for *.onnx files with matching *.onnx.json config."""
    result = []
    d = Path(models_dir)
    if not d.is_dir():
        return result
    for onnx in sorted(d.glob("*.onnx")):
        config_path = onnx.with_suffix(".onnx.json")
        info: dict = {"name": onnx.stem, "path": str(onnx)}
        if config_path.exists():
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
                lang = cfg.get("language", {})
                info["language"] = lang.get("name_english", "")
                info["sample_rate"] = cfg.get("audio", {}).get("sample_rate", 22050)
            except Exception:
                pass
        result.append(info)
    return result


def get_loaded_voice() -> str:
    """Return the name of the default loaded voice, or empty string."""
    return _default_voice

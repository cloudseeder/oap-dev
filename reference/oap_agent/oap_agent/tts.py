"""Local text-to-speech via Piper TTS (ONNX neural voices)."""

from __future__ import annotations

import io
import json
import logging
import wave
from pathlib import Path

log = logging.getLogger("oap.agent.tts")

_voice = None  # PiperVoice instance
_voice_name: str = ""


def init(model_path: str) -> None:
    """Load a Piper voice model. Call once at startup."""
    global _voice, _voice_name
    from piper.voice import PiperVoice

    _voice = PiperVoice.load(model_path)
    _voice_name = Path(model_path).stem
    log.info("Piper voice loaded: %s", _voice_name)


def synthesize(text: str) -> bytes:
    """Synthesize text to WAV bytes."""
    if _voice is None:
        raise RuntimeError("Piper voice not loaded — call init() first")
    buf = io.BytesIO()
    wav_file = wave.open(buf, "wb")
    # synthesize_wav sets WAV format (channels/sampwidth/framerate) and writes frames
    _voice.synthesize_wav(text, wav_file)
    wav_file.close()
    data = buf.getvalue()
    log.info("Synthesized %d bytes for %d chars", len(data), len(text))
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
    """Return the name of the currently loaded voice, or empty string."""
    return _voice_name

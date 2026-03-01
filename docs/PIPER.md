# Piper TTS — Local Neural Text-to-Speech

## What

Piper is a local neural text-to-speech engine that runs entirely on CPU via ONNX Runtime. The Manifest agent uses Piper to speak assistant replies aloud — replacing the browser's built-in Web Speech API with natural-sounding voices at zero API cost.

Architecture:

```
Frontend (browser)                    Backend (FastAPI :8303)
┌──────────────────┐  POST /v1/agent/tts  ┌──────────────────┐
│  useTTS hook     │ ──── { text } ──────►│  tts.py (Piper)  │
│  (fetch WAV)     │ ◄── audio/wav ─────── │  PiperVoice model│
│  HTMLAudioElement │                      └──────────────────┘
│  .play()         │  GET /v1/agent/tts/voices
└──────────────────┘ ──────────────────────► list .onnx files
```

The backend synthesizes text to a WAV response (~0.5-1s on Apple Silicon). The frontend fetches the WAV, creates a blob URL, and plays it via `HTMLAudioElement`. No streaming — sentences are short and Piper is fast enough that full-response delivery is simpler with negligible latency difference.

## Why

The browser's Web Speech API (`window.speechSynthesis`) produces robotic, dated-sounding voices that vary across browsers and platforms. Piper gives:

- **Natural speech** — neural voices trained on real speaker recordings
- **Consistency** — same voice on every device, every browser
- **Local-first** — no API calls, no cloud dependency, no usage fees
- **Fast** — medium-quality voices synthesize in under a second on M4
- **Multi-voice** — drop in new `.onnx` models to add voices, selectable in Settings

## Setup

### 1. Download a voice model

```bash
mkdir -p piper-voices && cd piper-voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

Each voice is an `.onnx` model file paired with an `.onnx.json` config file. Both are required.

### 2. Configure

Add to `config.yaml` (use absolute paths if the agent runs from a different working directory):

```yaml
voice:
  tts_enabled: true
  tts_model_path: /path/to/piper-voices/en_US-lessac-medium.onnx
  tts_models_dir: /path/to/piper-voices
```

| Field | Default | Description |
|-------|---------|-------------|
| `tts_enabled` | `true` | Enable/disable Piper TTS |
| `tts_model_path` | `""` | Path to the `.onnx` voice file loaded at startup |
| `tts_models_dir` | `piper-voices` | Directory scanned for available voices |

### 3. Install dependency

```bash
pip install -e reference/oap_agent  # pulls piper-tts>=1.2.0
```

### 4. Restart

```bash
launchctl kickstart -k gui/$(id -u)/com.oap.agent
```

Look for in the logs:

```
Piper TTS loaded — voice output ready
```

## Adding voices

Browse available voices at: https://rhasspy.github.io/piper-samples/

Each voice has quality tiers — `low`, `medium`, `high`. Higher quality means a larger model, slightly slower synthesis, and better sound.

To add a voice, download the `.onnx` + `.onnx.json` pair into your `tts_models_dir`:

```bash
cd /path/to/piper-voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
```

New voices appear immediately in the Settings voice picker (the endpoint scans the directory on each request). To **switch** the active voice, update `tts_model_path` in `config.yaml` and restart the agent service.

## API

### `POST /v1/agent/tts`

Synthesize text to audio.

**Request**: `{"text": "Hello world"}` (max 10,000 chars)

**Response**: `audio/wav` (16-bit PCM mono)

### `GET /v1/agent/tts/voices`

List available voice models.

**Response**: `{"voices": [{"name": "en_US-lessac-medium", "path": "...", "language": "English (US)", "sample_rate": 22050}], "current": "en_US-lessac-medium"}`

### `GET /v1/agent/voice/status`

Check voice subsystem availability.

**Response**: `{"enabled": true, "tts_enabled": true}`

## Frontend

The `useTTS` hook (`frontend/src/hooks/useTTS.ts`) provides:

- **`useTTS()`** — `speak(text)` fetches `/v1/agent/tts`, plays via `HTMLAudioElement`; `stop()` pauses playback; `speaking` tracks state
- **`useAnySpeaking()`** — event-driven global speaking detection via `useSyncExternalStore` (no polling); drives avatar halo animation
- **`useVoices()`** — fetches Piper voice list from backend for Settings picker

Speaker buttons on assistant messages are gated on `ttsAvailable` (fetched from `/v1/agent/voice/status` on mount). Auto-speak mode speaks every assistant reply via the same hook.

## Key files

| File | Role |
|------|------|
| `oap_agent/tts.py` | Piper module: `init()`, `synthesize()`, `list_voices()` |
| `oap_agent/config.py` | `VoiceConfig` with `tts_enabled`, `tts_model_path`, `tts_models_dir` |
| `oap_agent/api.py` | TTS endpoints + Piper loading in lifespan |
| `frontend/src/hooks/useTTS.ts` | Fetch-and-play hook, audio tracking, voice list |
| `frontend/src/components/SettingsView.tsx` | Voice picker + preview button |

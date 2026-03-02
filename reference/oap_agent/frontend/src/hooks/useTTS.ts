import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'

// ---------------------------------------------------------------------------
// Module-level audio tracking (replaces speechSynthesis.speaking polling)
// ---------------------------------------------------------------------------

const _activeAudios = new Set<HTMLAudioElement>()
const _listeners = new Set<() => void>()

function _notify() {
  for (const fn of _listeners) fn()
}

function _trackAudio(audio: HTMLAudioElement) {
  _activeAudios.add(audio)
  _notify()
  const cleanup = () => {
    _activeAudios.delete(audio)
    _notify()
  }
  audio.addEventListener('ended', cleanup, { once: true })
  audio.addEventListener('pause', cleanup, { once: true })
  audio.addEventListener('error', cleanup, { once: true })
}

function _stopAll() {
  for (const audio of _activeAudios) {
    audio.pause()
    audio.currentTime = 0
  }
  _activeAudios.clear()
  _notify()
}

function _subscribe(fn: () => void): () => void {
  _listeners.add(fn)
  return () => { _listeners.delete(fn) }
}

function _isAnySpeaking(): boolean {
  return _activeAudios.size > 0
}

// ---------------------------------------------------------------------------
// useTTS — fetch WAV from backend, play via HTMLAudioElement
// ---------------------------------------------------------------------------

export function useTTS(voice?: string) {
  const [speaking, setSpeaking] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const blobUrlRef = useRef<string | null>(null)

  const speak = useCallback(async (text: string) => {
    // Stop any current playback first
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    if (abortRef.current) {
      abortRef.current.abort()
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }

    abortRef.current = new AbortController()
    setSpeaking(true)

    try {
      const res = await fetch('/v1/agent/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice: voice || undefined }),
        signal: abortRef.current.signal,
      })
      if (!res.ok) {
        setSpeaking(false)
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      blobUrlRef.current = url

      const audio = new Audio(url)
      audioRef.current = audio

      audio.addEventListener('ended', () => {
        setSpeaking(false)
        URL.revokeObjectURL(url)
        blobUrlRef.current = null
      }, { once: true })

      audio.addEventListener('error', () => {
        setSpeaking(false)
        URL.revokeObjectURL(url)
        blobUrlRef.current = null
      }, { once: true })

      _trackAudio(audio)
      await audio.play()
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setSpeaking(false)
      }
    }
  }, [voice])

  const stop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
    }
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }
    setSpeaking(false)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current)
    }
  }, [])

  return { speaking, speak, stop, supported: true }
}

// ---------------------------------------------------------------------------
// useAnySpeaking — event-driven (no rAF polling)
// ---------------------------------------------------------------------------

export function useAnySpeaking(): boolean {
  return useSyncExternalStore(_subscribe, _isAnySpeaking, _isAnySpeaking)
}

// ---------------------------------------------------------------------------
// useVoices — fetch Piper voices from backend
// ---------------------------------------------------------------------------

export interface PiperVoice {
  name: string
  path: string
  language?: string
  sample_rate?: number
}

export function useVoices() {
  const [voices, setVoices] = useState<PiperVoice[]>([])

  useEffect(() => {
    fetch('/v1/agent/tts/voices')
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.voices) setVoices(data.voices)
      })
      .catch(() => {})
  }, [])

  return voices
}

/** Stop all active TTS audio globally. */
export function stopAllTTS() {
  _stopAll()
}

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
// useTTS — stream WAV chunks from backend, play sequentially
// ---------------------------------------------------------------------------

export function useTTS(voice?: string) {
  const [speaking, setSpeaking] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const blobUrlsRef = useRef<string[]>([])

  const revokeAll = useCallback(() => {
    for (const url of blobUrlsRef.current) {
      URL.revokeObjectURL(url)
    }
    blobUrlsRef.current = []
  }, [])

  const speak = useCallback(async (text: string) => {
    // Stop any current playback first
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    if (abortRef.current) {
      abortRef.current.abort()
    }
    revokeAll()

    const controller = new AbortController()
    abortRef.current = controller
    setSpeaking(true)

    try {
      const res = await fetch('/v1/agent/tts/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice: voice || undefined }),
        signal: controller.signal,
      })

      if (!res.ok || !res.body) {
        setSpeaking(false)
        return
      }

      const reader = res.body.getReader()
      const chunks: Blob[] = []
      let buffer = new Uint8Array(0)

      // Read length-prefixed WAV chunks from the stream
      const readChunks = async () => {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          // Append to buffer
          const next = new Uint8Array(buffer.length + value.length)
          next.set(buffer)
          next.set(value, buffer.length)
          buffer = next
          // Parse complete chunks from buffer
          while (buffer.length >= 4) {
            const len = (buffer[0] << 24) | (buffer[1] << 16) | (buffer[2] << 8) | buffer[3]
            if (buffer.length < 4 + len) break
            const wavData = buffer.slice(4, 4 + len)
            buffer = buffer.slice(4 + len)
            chunks.push(new Blob([wavData], { type: 'audio/wav' }))
          }
        }
      }

      // Start reading chunks in the background
      const readPromise = readChunks()

      // Play chunks sequentially as they arrive
      let chunkIndex = 0
      const playNext = (): Promise<void> => {
        return new Promise((resolve) => {
          const tryPlay = () => {
            if (controller.signal.aborted) {
              resolve()
              return
            }
            if (chunkIndex < chunks.length) {
              const blob = chunks[chunkIndex++]
              const url = URL.createObjectURL(blob)
              blobUrlsRef.current.push(url)

              const audio = new Audio(url)
              audioRef.current = audio
              _trackAudio(audio)

              audio.addEventListener('ended', () => {
                resolve()
              }, { once: true })

              audio.addEventListener('error', () => {
                resolve()
              }, { once: true })

              audio.play().catch(() => resolve())
            } else {
              // No chunk yet — wait a bit and retry
              setTimeout(tryPlay, 50)
            }
          }
          tryPlay()
        })
      }

      // Play loop: play each chunk then move to next
      const playLoop = async () => {
        let streamDone = false
        readPromise.then(() => { streamDone = true })
        while (!controller.signal.aborted) {
          if (chunkIndex < chunks.length) {
            await playNext()
          } else if (streamDone) {
            break
          } else {
            // Wait for more chunks
            await new Promise((r) => setTimeout(r, 50))
          }
        }
      }

      await Promise.all([readPromise, playLoop()])
      if (!controller.signal.aborted) {
        setSpeaking(false)
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setSpeaking(false)
      }
    }
  }, [voice, revokeAll])

  const stop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
    }
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    revokeAll()
    setSpeaking(false)
  }, [revokeAll])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      revokeAll()
    }
  }, [revokeAll])

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

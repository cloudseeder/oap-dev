import { useRef, useState, useCallback } from 'react'

// --- Continuous listening thresholds ---
const SPEECH_THRESHOLD = 0.03    // RMS level to detect speech onset
const SILENCE_THRESHOLD = 0.015  // RMS level to detect silence
const ONSET_FRAMES = 10          // ~170ms of speech before capture starts
const SILENCE_DURATION = 1500    // ms of silence before auto-stop
const MIN_UTTERANCE_MS = 500     // ignore clicks/bumps shorter than this

interface StartOptions {
  continuous?: boolean
  wakeWord?: string
}

/** Strip wake word prefix from transcript. Returns remaining text or null if no match. */
function stripWakeWord(transcript: string, wakeWord: string): string | null {
  if (!wakeWord) return transcript
  const clean = transcript.replace(/^[,.\-!?\s]+/, '').toLowerCase()
  const wk = wakeWord.toLowerCase().replace(/[^a-z0-9\s]/g, '')
  // Match patterns: "kai ...", "hey kai ...", "ok kai ...", "okay kai ..."
  const prefixes = [
    wk,
    `hey ${wk}`,
    `ok ${wk}`,
    `okay ${wk}`,
  ]
  for (const prefix of prefixes) {
    // Check if transcript starts with prefix, allowing trailing punctuation/space
    const re = new RegExp(`^${prefix.replace(/\s+/g, '[,\\s]+')}[,\\s]*`, 'i')
    const match = clean.match(re)
    if (match) {
      const remainder = clean.slice(match[0].length).trim()
      return remainder || null // null if wake word only (no content)
    }
  }
  return null // no wake word match
}

export function useVoiceRecorder(onResult: (text: string) => void) {
  const [recording, setRecording] = useState(false)
  const [listening, setListening] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const analyserRef = useRef<AnalyserNode | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  /** Live mic audio level (0-1), updated every animation frame while recording. */
  const audioLevelRef = useRef(0)
  const levelRafRef = useRef(0)

  // Continuous mode state
  const continuousRef = useRef(false)
  const wakeWordRef = useRef('')
  const speechFramesRef = useRef(0)
  const silenceStartRef = useRef(0)
  const captureStartRef = useRef(0)
  const stateRef = useRef<'passive' | 'capturing' | 'processing'>('passive')
  // Prevent re-entry when restarting passive monitoring after transcription
  const restartingRef = useRef(false)

  const onResultRef = useRef(onResult)
  onResultRef.current = onResult

  /** Transcribe a blob and handle wake word filtering + restart for continuous mode. */
  const transcribeBlob = useCallback(async (blob: Blob) => {
    if (blob.size === 0) {
      // Empty blob — restart passive if continuous
      if (continuousRef.current) restartPassive()
      return
    }

    setTranscribing(true)
    try {
      const form = new FormData()
      form.append('file', blob, 'recording.webm')
      const res = await fetch('/v1/agent/transcribe', {
        method: 'POST',
        body: form,
      })
      if (res.ok) {
        const { text } = await res.json()
        if (text?.trim()) {
          const trimmed = text.trim()
          if (wakeWordRef.current) {
            const stripped = stripWakeWord(trimmed, wakeWordRef.current)
            if (stripped !== null) {
              onResultRef.current(stripped)
            }
            // No match or wake-word-only: silently discard
          } else {
            onResultRef.current(trimmed)
          }
        }
      }
    } finally {
      setTranscribing(false)
      // Restart passive monitoring if in continuous mode
      if (continuousRef.current) restartPassive()
    }
  }, [])

  /** Restart passive monitoring after transcription (continuous mode). */
  function restartPassive() {
    if (!continuousRef.current || restartingRef.current) return
    if (!analyserRef.current || !streamRef.current) return
    restartingRef.current = true
    stateRef.current = 'passive'
    speechFramesRef.current = 0
    silenceStartRef.current = 0
    captureStartRef.current = 0
    setRecording(false)
    setListening(true)
    restartingRef.current = false
  }

  const start = useCallback(async (opts?: StartOptions) => {
    const continuous = opts?.continuous ?? false
    const wakeWord = opts?.wakeWord ?? ''
    continuousRef.current = continuous
    wakeWordRef.current = wakeWord

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Set up Web Audio analyser for real-time level metering
      const audioCtx = new AudioContext()
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.4
      source.connect(analyser)
      audioCtxRef.current = audioCtx
      analyserRef.current = analyser

      const dataArray = new Uint8Array(analyser.frequencyBinCount)

      if (continuous) {
        // --- Continuous listening mode ---
        stateRef.current = 'passive'
        speechFramesRef.current = 0
        silenceStartRef.current = 0
        setListening(true)

        function updateLevelContinuous() {
          if (!analyserRef.current) return
          analyserRef.current.getByteFrequencyData(dataArray)
          let sum = 0
          for (let i = 0; i < dataArray.length; i++) {
            const v = dataArray[i] / 255
            sum += v * v
          }
          const rms = Math.min(1, Math.sqrt(sum / dataArray.length) * 2.5)
          audioLevelRef.current = rms

          if (stateRef.current === 'passive') {
            if (rms > SPEECH_THRESHOLD) {
              speechFramesRef.current++
              if (speechFramesRef.current >= ONSET_FRAMES) {
                // Speech detected — start MediaRecorder
                stateRef.current = 'capturing'
                captureStartRef.current = Date.now()
                silenceStartRef.current = 0
                startMediaRecorder(stream)
                setRecording(true)
                setListening(false)
              }
            } else {
              speechFramesRef.current = 0
            }
          } else if (stateRef.current === 'capturing') {
            if (rms < SILENCE_THRESHOLD) {
              if (silenceStartRef.current === 0) {
                silenceStartRef.current = Date.now()
              } else if (
                Date.now() - silenceStartRef.current > SILENCE_DURATION &&
                Date.now() - captureStartRef.current > MIN_UTTERANCE_MS
              ) {
                // Silence detected — stop recording
                stateRef.current = 'processing'
                if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
                  mediaRecorderRef.current.stop()
                }
                setRecording(false)
              }
            } else {
              silenceStartRef.current = 0
            }
          }
          // In 'processing' state, keep the RAF loop running but do nothing

          levelRafRef.current = requestAnimationFrame(updateLevelContinuous)
        }
        levelRafRef.current = requestAnimationFrame(updateLevelContinuous)
      } else {
        // --- Single-shot mode (existing behavior) ---
        function updateLevel() {
          if (!analyserRef.current) return
          analyserRef.current.getByteFrequencyData(dataArray)
          let sum = 0
          for (let i = 0; i < dataArray.length; i++) {
            const v = dataArray[i] / 255
            sum += v * v
          }
          audioLevelRef.current = Math.min(1, Math.sqrt(sum / dataArray.length) * 2.5)
          levelRafRef.current = requestAnimationFrame(updateLevel)
        }
        levelRafRef.current = requestAnimationFrame(updateLevel)

        startMediaRecorder(stream)
        setRecording(true)
      }
    } catch {
      // getUserMedia denied or unavailable
    }
  }, [transcribeBlob])

  /** Create and start a MediaRecorder on the given stream. */
  function startMediaRecorder(stream: MediaStream) {
    const recorder = new MediaRecorder(stream, {
      mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm',
    })
    chunksRef.current = []

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }

    recorder.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: 'audio/webm' })

      if (continuousRef.current) {
        // Continuous mode: transcribe without tearing down mic/analyser
        await transcribeBlob(blob)
      } else {
        // Single-shot mode: tear down everything
        cancelAnimationFrame(levelRafRef.current)
        audioLevelRef.current = 0
        analyserRef.current = null
        audioCtxRef.current?.close()
        audioCtxRef.current = null
        stream.getTracks().forEach((t) => t.stop())
        streamRef.current = null

        if (blob.size === 0) return

        setTranscribing(true)
        try {
          const form = new FormData()
          form.append('file', blob, 'recording.webm')
          const res = await fetch('/v1/agent/transcribe', {
            method: 'POST',
            body: form,
          })
          if (res.ok) {
            const { text } = await res.json()
            if (text?.trim()) onResultRef.current(text.trim())
          }
        } finally {
          setTranscribing(false)
        }
      }
    }

    recorder.start()
    mediaRecorderRef.current = recorder
  }

  const stop = useCallback(() => {
    continuousRef.current = false
    stateRef.current = 'passive'

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }

    // Tear down audio infrastructure
    cancelAnimationFrame(levelRafRef.current)
    audioLevelRef.current = 0
    analyserRef.current = null
    audioCtxRef.current?.close()
    audioCtxRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null

    setRecording(false)
    setListening(false)
  }, [])

  const supported =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined'

  return { recording, listening, transcribing, start, stop, supported, audioLevelRef }
}

import { useRef, useState, useCallback } from 'react'

// --- Continuous listening thresholds ---
const SPEECH_THRESHOLD = 0.03    // RMS level to detect speech onset
const ONSET_FRAMES = 10          // ~170ms of speech before capture starts
const SILENCE_DURATION = 1500    // ms of silence before auto-stop
const MIN_UTTERANCE_MS = 500     // ignore clicks/bumps shorter than this
const SILENCE_DROP_RATIO = 0.3   // silence = RMS drops to 30% of peak speech level
const AMBIENT_EMA_ALPHA = 0.01   // slow EMA for tracking ambient noise floor
const SPEECH_EMA_ALPHA = 0.15    // faster EMA for tracking speech level during capture

interface StartOptions {
  continuous?: boolean
  wakeWord?: string
}

/** Strip wake word prefix (and repeated hallucinations) from transcript.
 *  Returns remaining text, or null if no wake word match or only wake words. */
function stripWakeWord(transcript: string, wakeWord: string): string | null {
  if (!wakeWord) return transcript
  let clean = transcript.replace(/^[,.\-!?\s]+/, '').toLowerCase()
  const wk = wakeWord.toLowerCase().replace(/[^a-z0-9\s]/g, '')

  // First check: does the transcript contain the wake word at all?
  if (!clean.includes(wk)) return null

  // Strip all leading wake word repetitions and prefixes like "hey/ok/okay"
  // Handles: "kai", "kai, kai, kai", "hey kai", "ok kai, kai", etc.
  const wkPattern = wk.replace(/\s+/g, '[,\\s]+')
  const repPattern = new RegExp(
    `^(?:(?:hey|ok|okay)[,\\s]+)?${wkPattern}[,\\.\\s]*`, 'i'
  )
  let prev = ''
  while (clean !== prev) {
    prev = clean
    clean = clean.replace(repPattern, '').trim()
  }

  // If nothing left after stripping, it was just wake word repetitions
  return clean || null
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
  // Adaptive level tracking
  const ambientLevelRef = useRef(0)   // slow EMA of ambient noise floor (passive mode)
  const speechPeakRef = useRef(0)     // EMA of speech level during capture
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
    speechPeakRef.current = 0
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
        ambientLevelRef.current = 0
        speechPeakRef.current = 0
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
            // Track ambient noise floor with slow EMA
            ambientLevelRef.current = ambientLevelRef.current === 0
              ? rms
              : ambientLevelRef.current * (1 - AMBIENT_EMA_ALPHA) + rms * AMBIENT_EMA_ALPHA

            // Speech onset: RMS must exceed both absolute threshold AND
            // be significantly above the ambient floor
            const onsetThreshold = Math.max(SPEECH_THRESHOLD, ambientLevelRef.current * 2.5)
            if (rms > onsetThreshold) {
              speechFramesRef.current++
              if (speechFramesRef.current >= ONSET_FRAMES) {
                // Speech detected — start MediaRecorder
                stateRef.current = 'capturing'
                captureStartRef.current = Date.now()
                silenceStartRef.current = 0
                speechPeakRef.current = rms
                startMediaRecorder(stream)
                setRecording(true)
                setListening(false)
              }
            } else {
              speechFramesRef.current = 0
            }
          } else if (stateRef.current === 'capturing') {
            // Track speech level with faster EMA
            if (rms > speechPeakRef.current) {
              speechPeakRef.current = rms
            } else {
              speechPeakRef.current = speechPeakRef.current * (1 - SPEECH_EMA_ALPHA) + rms * SPEECH_EMA_ALPHA
            }

            // Silence = RMS dropped to SILENCE_DROP_RATIO of the speech peak,
            // or back down near the ambient floor
            const silenceThreshold = Math.max(
              speechPeakRef.current * SILENCE_DROP_RATIO,
              ambientLevelRef.current * 1.3,
            )
            if (rms < silenceThreshold) {
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

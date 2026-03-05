import { useRef, useState, useCallback } from 'react'

// --- Continuous listening thresholds ---
const SPEECH_THRESHOLD = 0.03    // RMS level to detect speech onset
const ONSET_FRAMES = 10          // ~170ms of speech before capture starts
const SILENCE_DURATION = 1500    // ms of silence before auto-stop
const SILENCE_DROP_RATIO = 0.3   // silence = RMS drops to 30% of peak speech level
const AMBIENT_EMA_ALPHA = 0.01   // slow EMA for tracking ambient noise floor
const SPEECH_EMA_ALPHA = 0.15    // faster EMA for tracking speech level during capture
const ATTENTIVE_TIMEOUT = 8000   // ms to wait for follow-up speech after wake word

interface StartOptions {
  continuous?: boolean
  wakeWord?: string
}

/** Simple similarity — exact, starts-with, contains, or edit distance <= 1. */
function fuzzyMatch(a: string, b: string): boolean {
  if (a === b) return true
  if (a.length > 1 && b.length > 1) {
    if (a.startsWith(b) || b.startsWith(a)) return true
    if (a.includes(b) || b.includes(a)) return true
  }
  if (Math.abs(a.length - b.length) > 1) return false
  let diffs = 0
  const longer = a.length >= b.length ? a : b
  const shorter = a.length >= b.length ? b : a
  if (longer.length === shorter.length) {
    for (let i = 0; i < longer.length; i++) {
      if (longer[i] !== shorter[i]) diffs++
    }
    return diffs <= 1
  }
  let si = 0
  for (let li = 0; li < longer.length; li++) {
    if (si < shorter.length && longer[li] === shorter[si]) si++
    else diffs++
  }
  return diffs <= 1
}

/** Check if transcript contains the wake word. Returns { found, remainder }.
 *  remainder is the text after the wake word, or empty if just the wake word. */
function parseWakeWord(transcript: string, wakeWord: string): { found: boolean; remainder: string } {
  if (!wakeWord) return { found: true, remainder: transcript }
  const wk = wakeWord.toLowerCase().replace(/[^a-z0-9\s]/g, '')
  const words = transcript.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(Boolean)
  if (words.length === 0) return { found: false, remainder: '' }

  const skipWords = new Set(['hey', 'ok', 'okay', 'hi', 'hello'])
  let wakeEnd = -1

  for (let i = 0; i < Math.min(words.length, 6); i++) {
    if (fuzzyMatch(words[i], wk)) {
      wakeEnd = i + 1
      // Consume repeated wake words (hallucination)
      while (wakeEnd < words.length && fuzzyMatch(words[wakeEnd], wk)) wakeEnd++
      break
    }
    if (!skipWords.has(words[i])) break
  }

  if (wakeEnd === -1) return { found: false, remainder: '' }

  // Reconstruct remainder from original transcript
  let charPos = 0
  const lower = transcript.toLowerCase()
  for (let i = 0; i < wakeEnd; i++) {
    const idx = lower.indexOf(words[i], charPos)
    if (idx >= 0) charPos = idx + words[i].length
  }
  while (charPos < transcript.length && /[,.\-!?\s]/.test(transcript[charPos])) charPos++
  return { found: true, remainder: transcript.slice(charPos).trim() }
}

export function useVoiceRecorder(onResult: (text: string) => void) {
  const [recording, setRecording] = useState(false)
  const [listening, setListening] = useState(false)
  const [attentive, setAttentive] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const analyserRef = useRef<AnalyserNode | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  /** Live mic audio level (0-1), updated every animation frame. */
  const audioLevelRef = useRef(0)
  const levelRafRef = useRef(0)

  // Continuous mode state
  const continuousRef = useRef(false)
  const wakeWordRef = useRef('')
  const speechFramesRef = useRef(0)
  const silenceStartRef = useRef(0)
  const captureStartRef = useRef(0)
  // States: passive → capturing → processing → (attentive → capturing_request → processing_request) → passive
  const stateRef = useRef<'passive' | 'capturing' | 'processing' | 'attentive' | 'capturing_request' | 'processing_request'>('passive')
  // Adaptive level tracking
  const ambientLevelRef = useRef(0)
  const speechPeakRef = useRef(0)
  const attentiveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const restartingRef = useRef(false)

  const onResultRef = useRef(onResult)
  onResultRef.current = onResult

  /** Transcribe a blob. Phase 1 (wake word check) or Phase 2 (send request). */
  const transcribeBlob = useCallback(async (blob: Blob, isRequest: boolean) => {
    if (blob.size === 0) {
      if (continuousRef.current) goPassive()
      return
    }

    setTranscribing(true)
    try {
      const form = new FormData()
      form.append('file', blob, 'recording.webm')
      const res = await fetch('/v1/agent/transcribe', { method: 'POST', body: form })
      if (!res.ok) return

      const { text } = await res.json()
      const trimmed = text?.trim()
      if (!trimmed) return

      if (isRequest) {
        // Phase 2: this is the actual request — send it directly
        onResultRef.current(trimmed)
      } else if (wakeWordRef.current) {
        // Phase 1: check for wake word
        const { found, remainder } = parseWakeWord(trimmed, wakeWordRef.current)
        if (found && remainder) {
          // Wake word + request in one utterance — send it
          onResultRef.current(remainder)
        } else if (found) {
          // Wake word only — go attentive, wait for the real request
          goAttentive()
          return // don't restart passive
        }
        // No wake word found — discard, back to passive
      } else {
        // No wake word configured — send everything
        onResultRef.current(trimmed)
      }
    } finally {
      setTranscribing(false)
      // Return to passive unless we went attentive
      if (continuousRef.current && stateRef.current !== 'attentive' && stateRef.current !== 'capturing_request') {
        goPassive()
      }
    }
  }, [])

  /** Enter attentive state — avatar shows listening, waiting for the real request. */
  function goAttentive() {
    stateRef.current = 'attentive'
    speechFramesRef.current = 0
    silenceStartRef.current = 0
    speechPeakRef.current = 0
    setTranscribing(false)
    setRecording(true)  // show recording state in avatar
    setListening(false)
    setAttentive(true)

    // Timeout: if no speech comes within ATTENTIVE_TIMEOUT, go back to passive
    if (attentiveTimerRef.current) clearTimeout(attentiveTimerRef.current)
    attentiveTimerRef.current = setTimeout(() => {
      if (stateRef.current === 'attentive') goPassive()
    }, ATTENTIVE_TIMEOUT)
  }

  /** Return to passive monitoring. */
  function goPassive() {
    if (!continuousRef.current || restartingRef.current) return
    if (!analyserRef.current || !streamRef.current) return
    restartingRef.current = true
    if (attentiveTimerRef.current) { clearTimeout(attentiveTimerRef.current); attentiveTimerRef.current = null }
    stateRef.current = 'passive'
    speechFramesRef.current = 0
    silenceStartRef.current = 0
    captureStartRef.current = 0
    speechPeakRef.current = 0
    setRecording(false)
    setListening(true)
    setAttentive(false)
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

          const state = stateRef.current

          if (state === 'passive') {
            // Track ambient noise floor
            ambientLevelRef.current = ambientLevelRef.current === 0
              ? rms
              : ambientLevelRef.current * (1 - AMBIENT_EMA_ALPHA) + rms * AMBIENT_EMA_ALPHA

            const onsetThreshold = Math.max(SPEECH_THRESHOLD, ambientLevelRef.current * 2.5)
            if (rms > onsetThreshold) {
              speechFramesRef.current++
              if (speechFramesRef.current >= ONSET_FRAMES) {
                // Speech detected — start recording for wake word check
                stateRef.current = 'capturing'
                captureStartRef.current = Date.now()
                silenceStartRef.current = 0
                speechPeakRef.current = rms
                startMediaRecorder(stream, false)
                setRecording(true)
                setListening(false)
              }
            } else {
              speechFramesRef.current = 0
            }
          } else if (state === 'capturing' || state === 'capturing_request') {
            // Track speech peak
            if (rms > speechPeakRef.current) {
              speechPeakRef.current = rms
            } else {
              speechPeakRef.current = speechPeakRef.current * (1 - SPEECH_EMA_ALPHA) + rms * SPEECH_EMA_ALPHA
            }

            // Check for silence
            const silenceThreshold = Math.max(
              speechPeakRef.current * SILENCE_DROP_RATIO,
              ambientLevelRef.current * 1.3,
            )
            if (rms < silenceThreshold) {
              if (silenceStartRef.current === 0) {
                silenceStartRef.current = Date.now()
              } else if (Date.now() - silenceStartRef.current > SILENCE_DURATION) {
                // Silence detected — stop recording
                stateRef.current = state === 'capturing_request' ? 'processing_request' : 'processing'
                if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
                  mediaRecorderRef.current.stop()
                }
                setRecording(false)
              }
            } else {
              silenceStartRef.current = 0
            }
          } else if (state === 'attentive') {
            // Waiting for follow-up speech after wake word
            const onsetThreshold = Math.max(SPEECH_THRESHOLD, ambientLevelRef.current * 2.5)
            if (rms > onsetThreshold) {
              speechFramesRef.current++
              if (speechFramesRef.current >= ONSET_FRAMES) {
                // Speech started — capture the actual request
                if (attentiveTimerRef.current) { clearTimeout(attentiveTimerRef.current); attentiveTimerRef.current = null }
                stateRef.current = 'capturing_request'
                captureStartRef.current = Date.now()
                silenceStartRef.current = 0
                speechPeakRef.current = rms
                startMediaRecorder(stream, true)
                // recording is already true from goAttentive
              }
            } else {
              speechFramesRef.current = 0
            }
          }
          // processing / processing_request: RAF loop runs but does nothing

          levelRafRef.current = requestAnimationFrame(updateLevelContinuous)
        }
        levelRafRef.current = requestAnimationFrame(updateLevelContinuous)
      } else {
        // --- Single-shot mode ---
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

        startMediaRecorder(stream, false)
        setRecording(true)
      }
    } catch {
      // getUserMedia denied or unavailable
    }
  }, [transcribeBlob])

  /** Create and start a MediaRecorder. isRequest=true for phase 2 (actual request). */
  function startMediaRecorder(stream: MediaStream, isRequest: boolean) {
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
        await transcribeBlob(blob, isRequest)
      } else {
        // Single-shot: tear down everything
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
          const res = await fetch('/v1/agent/transcribe', { method: 'POST', body: form })
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
    if (attentiveTimerRef.current) { clearTimeout(attentiveTimerRef.current); attentiveTimerRef.current = null }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }

    cancelAnimationFrame(levelRafRef.current)
    audioLevelRef.current = 0
    analyserRef.current = null
    audioCtxRef.current?.close()
    audioCtxRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null

    setRecording(false)
    setListening(false)
    setAttentive(false)
  }, [])

  const supported =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined'

  return { recording, listening, attentive, transcribing, start, stop, supported, audioLevelRef }
}

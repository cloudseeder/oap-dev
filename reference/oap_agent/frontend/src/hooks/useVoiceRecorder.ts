import { useRef, useState, useCallback } from 'react'

export function useVoiceRecorder(onResult: (text: string) => void) {
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const analyserRef = useRef<AnalyserNode | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)

  /** Live mic audio level (0–1), updated every animation frame while recording. */
  const audioLevelRef = useRef(0)
  const levelRafRef = useRef(0)

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })

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
      function updateLevel() {
        if (!analyserRef.current) return
        analyserRef.current.getByteFrequencyData(dataArray)
        // RMS of frequency bins, normalized to 0–1
        let sum = 0
        for (let i = 0; i < dataArray.length; i++) {
          const v = dataArray[i] / 255
          sum += v * v
        }
        audioLevelRef.current = Math.min(1, Math.sqrt(sum / dataArray.length) * 2.5)
        levelRafRef.current = requestAnimationFrame(updateLevel)
      }
      levelRafRef.current = requestAnimationFrame(updateLevel)

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
        // Stop level metering
        cancelAnimationFrame(levelRafRef.current)
        audioLevelRef.current = 0
        analyserRef.current = null
        audioCtxRef.current?.close()
        audioCtxRef.current = null

        // Stop all tracks to release the microphone
        stream.getTracks().forEach((t) => t.stop())

        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
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
            if (text?.trim()) onResult(text.trim())
          }
        } finally {
          setTranscribing(false)
        }
      }

      recorder.start()
      mediaRecorderRef.current = recorder
      setRecording(true)
    } catch {
      // getUserMedia denied or unavailable
    }
  }, [onResult])

  const stop = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    setRecording(false)
  }, [])

  const supported =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined'

  return { recording, transcribing, start, stop, supported, audioLevelRef }
}

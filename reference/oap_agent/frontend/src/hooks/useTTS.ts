import { useCallback, useEffect, useRef, useState } from 'react'

export function useTTS(voiceURI?: string) {
  const [speaking, setSpeaking] = useState(false)
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null)

  const speak = useCallback((text: string) => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return

    window.speechSynthesis.cancel()

    const utterance = new SpeechSynthesisUtterance(text)

    if (voiceURI) {
      const voice = window.speechSynthesis.getVoices().find((v) => v.voiceURI === voiceURI)
      if (voice) utterance.voice = voice
    }

    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)
    utteranceRef.current = utterance

    setSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }, [voiceURI])

  const stop = useCallback(() => {
    if (typeof window !== 'undefined') {
      window.speechSynthesis?.cancel()
    }
    setSpeaking(false)
  }, [])

  const supported =
    typeof window !== 'undefined' && !!window.speechSynthesis

  return { speaking, speak, stop, supported }
}

/** Returns available system voices, updating when the browser loads them. */
export function useVoices() {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])

  useEffect(() => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return

    function load() {
      setVoices(window.speechSynthesis.getVoices())
    }

    load()
    window.speechSynthesis.addEventListener('voiceschanged', load)
    return () => window.speechSynthesis.removeEventListener('voiceschanged', load)
  }, [])

  return voices
}

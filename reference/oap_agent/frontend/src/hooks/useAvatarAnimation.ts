import { useEffect, useRef, useState, type MutableRefObject } from 'react'
import type { PersonaStyle } from '@/lib/personaStyles'

export type AvatarMode = 'idle' | 'speaking' | 'listening' | 'thinking'

export interface AvatarFrame {
  scale: number
  glowRadius: number
  glowAlpha: number
  rotation: number
  quirk: number
}

const INITIAL_FRAME: AvatarFrame = {
  scale: 1,
  glowRadius: 0,
  glowAlpha: 0,
  rotation: 0,
  quirk: 0,
}

interface AnimationInput {
  speaking: boolean
  recording: boolean
  streaming: boolean
  /** Real-time audio level 0–1 from mic analyser (recording) */
  audioLevelRef?: MutableRefObject<number>
}

export function useAvatarAnimation(input: AnimationInput, style: PersonaStyle): AvatarFrame {
  const [frame, setFrame] = useState<AvatarFrame>(INITIAL_FRAME)
  const rafRef = useRef<number>(0)
  const startRef = useRef<number>(0)

  const mode: AvatarMode = input.speaking
    ? 'speaking'
    : input.recording
      ? 'listening'
      : input.streaming
        ? 'thinking'
        : 'idle'

  useEffect(() => {
    startRef.current = performance.now()

    function tick(now: number) {
      const t = (now - startRef.current) / 1000

      let scale = 1
      let glowRadius = 0
      let glowAlpha = 0
      let rotation = 0
      let quirk = 0

      switch (mode) {
        case 'idle':
          // No halo at all — just gentle shape breathing
          scale = 1 + 0.015 * Math.sin(t * style.idleSpeed * 2)
          glowRadius = 0
          glowAlpha = 0
          break

        case 'speaking': {
          // Speech-like envelope — pulses between moderate and bold, never zero
          // Syllable rhythm at ~4Hz
          const syllable = Math.abs(Math.sin(t * 4.2))
          // Word-level modulation at ~1.8Hz — dips but never kills
          const word = 0.5 + 0.5 * Math.sin(t * 1.8)
          // Gentle sentence-level swell
          const emphasis = 0.75 + 0.25 * Math.sin(t * 0.5)
          // Texture
          const flutter = Math.sin(t * 19) * 0.08
          // Floor of 0.3 so halo is always present during speech
          const level = Math.min(1, 0.3 + 0.7 * (syllable * 0.5 + word * 0.3 + flutter) * emphasis)
          const intensity = style.speakIntensity

          scale = 1 + level * intensity * 0.25
          glowRadius = level * intensity * 2.0
          glowAlpha = level * intensity * 0.9
          break
        }

        case 'listening': {
          // Real mic audio — direct mapping, no smoothing on top of analyser
          const raw = input.audioLevelRef?.current ?? 0
          // Slight compression so quiet sounds register
          const mic = raw ** 0.5

          scale = 1 + mic * 0.35
          glowRadius = mic * 2.5
          glowAlpha = mic * 1.0
          break
        }

        case 'thinking':
          scale = 1 + 0.04 * Math.sin(t * 2)
          rotation = t * 1.5
          glowRadius = 0.15 + 0.08 * Math.sin(t * 3)
          glowAlpha = 0.1 + 0.06 * Math.abs(Math.sin(t * 1.5))
          break
      }

      // Persona quirk
      switch (style.quirk) {
        case 'droop':
          quirk = 0.15 + 0.05 * Math.sin(t * 0.5)
          break
        case 'wobble':
          quirk = Math.sin(t * style.idleSpeed * 3) * 0.08
          break
        case 'tilt':
          quirk = Math.sin(t * style.idleSpeed * 1.2) * 0.15
          break
        case 'rotate':
          rotation += t * style.idleSpeed * 0.3
          break
      }

      setFrame({ scale, glowRadius, glowAlpha, rotation, quirk })
      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [mode, style, input.audioLevelRef])

  return frame
}

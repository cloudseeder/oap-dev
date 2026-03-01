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
  glowRadius: 0.8,
  glowAlpha: 0.35,
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
      let glowRadius = 0.4
      let glowAlpha = 0.08
      let rotation = 0
      let quirk = 0

      switch (mode) {
        case 'idle':
          scale = 1 + 0.02 * Math.sin(t * style.idleSpeed * 2)
          glowRadius = 0.4 + 0.05 * Math.sin(t * style.idleSpeed * 1.5)
          glowAlpha = 0.06 + 0.04 * Math.sin(t * style.idleSpeed * 1.5)
          break

        case 'speaking': {
          // Simulated speech envelope — multiple overlapping rhythms
          const syllable = Math.abs(Math.sin(t * 4.2)) ** 0.6
          const word = (Math.sin(t * 2.1) * 0.5 + 0.5) ** 0.8
          const emphasis = Math.sin(t * 0.7) * 0.3 + 0.7
          const jitter = Math.sin(t * 17.3) * 0.15 + Math.sin(t * 31.7) * 0.08
          const raw = Math.min(1, (syllable * 0.5 + word * 0.3 + jitter) * emphasis)
          // Power curve: ramp up fast from dim to bright
          const level = raw ** 0.4
          const intensity = style.speakIntensity

          scale = 1 + level * intensity * 0.5
          glowRadius = 0.4 + level * intensity * 1.8
          glowAlpha = 0.08 + level * intensity * 0.92
          break
        }

        case 'listening': {
          // Real mic audio level — color organ style
          const raw = input.audioLevelRef?.current ?? 0
          // Power curve: small sounds still produce visible glow, loud = blazing
          const mic = raw ** 0.35
          scale = 1 + mic * 0.5
          glowRadius = 0.4 + mic * 2.0
          glowAlpha = 0.08 + mic * 0.92
          break
        }

        case 'thinking':
          scale = 1 + 0.04 * Math.sin(t * 2)
          rotation = t * 1.5
          glowRadius = 0.4 + 0.1 * Math.sin(t * 3)
          glowAlpha = 0.08 + 0.08 * Math.abs(Math.sin(t * 1.5))
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

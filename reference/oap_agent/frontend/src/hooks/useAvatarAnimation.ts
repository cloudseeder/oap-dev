import { useEffect, useRef, useState } from 'react'
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
  glowRadius: 0.6,
  glowAlpha: 0.15,
  rotation: 0,
  quirk: 0,
}

interface AnimationInput {
  speaking: boolean
  recording: boolean
  streaming: boolean
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
      let glowRadius = 0.8
      let glowAlpha = 0.4
      let rotation = 0
      let quirk = 0

      switch (mode) {
        case 'idle':
          scale = 1 + 0.03 * Math.sin(t * style.idleSpeed * 2)
          glowRadius = 0.8 + 0.1 * Math.sin(t * style.idleSpeed * 1.5)
          glowAlpha = 0.35 + 0.1 * Math.sin(t * style.idleSpeed * 1.5)
          break
        case 'speaking': {
          const base = Math.sin(t * 8) * 0.5 + 0.5
          const noise = Math.sin(t * 13.7) * 0.3 + Math.sin(t * 21.3) * 0.2
          scale = 1 + style.speakIntensity * 0.1 * (base + noise * 0.5)
          glowRadius = 0.9 + 0.2 * base
          glowAlpha = 0.45 + 0.25 * base
          break
        }
        case 'listening':
          scale = 1.05 + 0.02 * Math.sin(t * 3)
          glowRadius = 0.9 + 0.1 * Math.sin(t * 2)
          glowAlpha = 0.45 + 0.1 * Math.sin(t * 2)
          break
        case 'thinking':
          scale = 1 + 0.04 * Math.sin(t * 2)
          rotation = t * 1.5
          glowRadius = 0.8 + 0.15 * Math.sin(t * 3)
          glowAlpha = 0.3 + 0.15 * Math.abs(Math.sin(t * 1.5))
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
  }, [mode, style])

  return frame
}

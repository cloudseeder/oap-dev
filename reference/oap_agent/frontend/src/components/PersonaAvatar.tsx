import { useRef, useEffect, type MutableRefObject } from 'react'
import { getPersonaStyle } from '@/lib/personaStyles'
import { useAvatarAnimation } from '@/hooks/useAvatarAnimation'

interface PersonaAvatarProps {
  persona: string
  speaking: boolean
  recording: boolean
  streaming: boolean
  attentive?: boolean
  size?: number
  audioLevelRef?: MutableRefObject<number>
}

export default function PersonaAvatar({ persona, speaking, recording, streaming, attentive = false, size = 96, audioLevelRef }: PersonaAvatarProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const style = getPersonaStyle(persona)
  const frame = useAvatarAnimation({ speaking, recording, streaming, attentive, audioLevelRef }, style)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = size * dpr
    canvas.height = size * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const cx = size / 2
    const cy = size / 2
    const baseR = size * 0.28

    ctx.clearRect(0, 0, size, size)

    const shapeR = baseR * frame.scale

    // Wobbly halo ring — only drawn when glowAlpha > threshold (not idle)
    const g = frame.glowRadius  // 0 to ~2.5
    const a = frame.glowAlpha   // 0 to ~1.0
    const segments = 64

    if (a > 0.05) {
      const haloGap = baseR * 0.2 + baseR * g * 0.35
      const haloR = shapeR + haloGap
      const wobbleAmt = baseR * g * 0.15
      const lineWidth = 2 + a * 8

      ctx.strokeStyle = style.primary
      ctx.globalAlpha = Math.min(1, a * 0.9)
      ctx.lineWidth = lineWidth
      ctx.beginPath()
      for (let i = 0; i <= segments; i++) {
        const angle = (i / segments) * Math.PI * 2
        const wobble = Math.sin(angle * 5 + frame.rotation * 3) * wobbleAmt
          + Math.sin(angle * 3 - frame.rotation * 2) * wobbleAmt * 0.6
        const r = haloR + wobble
        const x = cx + Math.cos(angle) * r
        const y = cy + Math.sin(angle) * r
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.closePath()
      ctx.stroke()

      // Second halo ring at high levels
      if (a > 0.5) {
        const outerR = haloR + baseR * 0.3 + baseR * g * 0.15
        ctx.globalAlpha = Math.min(1, (a - 0.5) * 2)
        ctx.lineWidth = lineWidth * 0.5
        ctx.beginPath()
        for (let i = 0; i <= segments; i++) {
          const angle = (i / segments) * Math.PI * 2
          const wobble = Math.sin(angle * 4 - frame.rotation * 2.5) * wobbleAmt * 1.5
            + Math.sin(angle * 7 + frame.rotation * 1.5) * wobbleAmt * 0.7
          const r = outerR + wobble
          const x = cx + Math.cos(angle) * r
          const y = cy + Math.sin(angle) * r
          if (i === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.closePath()
        ctx.stroke()
      }
    }

    ctx.globalAlpha = 1.0

    ctx.save()
    ctx.translate(cx, cy)

    // Apply quirk offset
    if (style.quirk === 'droop') {
      ctx.translate(0, baseR * frame.quirk)
    } else if (style.quirk === 'wobble' || style.quirk === 'tilt') {
      ctx.rotate(frame.quirk)
    }

    const r = baseR * frame.scale

    // Main shape
    ctx.fillStyle = style.primary
    drawShape(ctx, style.shape, 0, 0, r, frame.rotation)

    // Inner highlight
    ctx.globalAlpha = 0.3
    ctx.fillStyle = style.secondary
    drawShape(ctx, style.shape, 0, 0, r * 0.6, frame.rotation)
    ctx.globalAlpha = 1.0

    ctx.restore()

    // Thinking particles
    if (streaming) {
      const particleCount = 3
      for (let i = 0; i < particleCount; i++) {
        const angle = frame.rotation * 2 + (i * Math.PI * 2) / particleCount
        const orbitR = baseR * 1.4
        const px = cx + Math.cos(angle) * orbitR
        const py = cy + Math.sin(angle) * orbitR
        ctx.fillStyle = style.secondary
        ctx.globalAlpha = 0.6
        ctx.beginPath()
        ctx.arc(px, py, 2.5, 0, Math.PI * 2)
        ctx.fill()
        ctx.globalAlpha = 1.0
      }
    }
  }, [frame, style, size, streaming])

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size }}
      className="pointer-events-none"
    />
  )
}

function drawShape(
  ctx: CanvasRenderingContext2D,
  shape: string,
  cx: number,
  cy: number,
  r: number,
  rotation: number,
) {
  ctx.beginPath()
  switch (shape) {
    case 'circle':
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      break
    case 'ellipse':
      ctx.ellipse(cx, cy, r, r * 0.7, 0, 0, Math.PI * 2)
      break
    case 'pentagon':
      drawPolygon(ctx, cx, cy, r, 5, rotation - Math.PI / 2)
      break
    case 'hexagon':
      drawPolygon(ctx, cx, cy, r, 6, rotation)
      break
    case 'triangle':
      drawPolygon(ctx, cx, cy, r, 3, rotation - Math.PI / 2)
      break
    default:
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
  }
  ctx.fill()
}

function drawPolygon(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  sides: number,
  rotation: number,
) {
  for (let i = 0; i < sides; i++) {
    const angle = rotation + (i * Math.PI * 2) / sides
    const x = cx + r * Math.cos(angle)
    const y = cy + r * Math.sin(angle)
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.closePath()
}

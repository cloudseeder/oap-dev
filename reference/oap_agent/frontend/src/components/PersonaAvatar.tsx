import { useRef, useEffect, type MutableRefObject } from 'react'
import { getPersonaStyle } from '@/lib/personaStyles'
import { useAvatarAnimation } from '@/hooks/useAvatarAnimation'

interface PersonaAvatarProps {
  persona: string
  speaking: boolean
  recording: boolean
  streaming: boolean
  size?: number
  audioLevelRef?: MutableRefObject<number>
}

export default function PersonaAvatar({ persona, speaking, recording, streaming, size = 96, audioLevelRef }: PersonaAvatarProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const style = getPersonaStyle(persona)
  const frame = useAvatarAnimation({ speaking, recording, streaming, audioLevelRef }, style)

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

    // Outer glow — use primary color with animated alpha for reliable rendering
    const glowR = baseR * (1 + frame.glowRadius)
    const gradient = ctx.createRadialGradient(cx, cy, baseR * 0.3, cx, cy, glowR)
    const cr = parseInt(style.primary.slice(1, 3), 16)
    const cg = parseInt(style.primary.slice(3, 5), 16)
    const cb = parseInt(style.primary.slice(5, 7), 16)
    gradient.addColorStop(0, `rgba(${cr},${cg},${cb},${frame.glowAlpha})`)
    gradient.addColorStop(0.6, `rgba(${cr},${cg},${cb},${frame.glowAlpha * 0.4})`)
    gradient.addColorStop(1, `rgba(${cr},${cg},${cb},0)`)
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)

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

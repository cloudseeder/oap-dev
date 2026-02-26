import { NextRequest, NextResponse } from 'next/server'
import { proxyFetch } from '@/lib/proxy'
import { RateLimiter, getClientIP } from '@/lib/security'
import { checkAgentAuth } from '@/lib/agentAuth'

export const maxDuration = 120

const AGENT_PORT = 8303
const limiter = new RateLimiter(5, 60 * 1000) // 5 SSE connections per minute per IP

export async function GET(request: NextRequest) {
  const authError = checkAgentAuth(request)
  if (authError) return authError
  const ip = getClientIP(request)
  const { allowed, retryAfterMs } = limiter.check(ip)
  if (!allowed) {
    return NextResponse.json({ error: 'Rate limit exceeded', retryAfterMs }, { status: 429 })
  }

  try {
    const backendResponse = await proxyFetch('/v1/agent/events', {
      headers: { 'Accept': 'text/event-stream' },
    }, { port: AGENT_PORT, timeout: 120000 })

    return new Response(backendResponse.body, {
      status: backendResponse.status,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    })
  } catch {
    return NextResponse.json({ error: 'Agent service unavailable' }, { status: 503 })
  }
}

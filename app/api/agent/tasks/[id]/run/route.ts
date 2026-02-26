import { NextRequest, NextResponse } from 'next/server'
import { proxyFetch } from '@/lib/proxy'
import { RateLimiter, getClientIP } from '@/lib/security'
import { checkAgentAuth } from '@/lib/agentAuth'

const AGENT_PORT = 8303
const limiter = new RateLimiter(5, 60 * 1000) // 5 per minute — triggers LLM work

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const authError = checkAgentAuth(request)
  if (authError) return authError
  const { id } = await params
  const ip = getClientIP(request)
  const { allowed, retryAfterMs } = limiter.check(ip)
  if (!allowed) {
    return NextResponse.json({ error: 'Rate limit exceeded', retryAfterMs }, { status: 429 })
  }

  try {
    const response = await proxyFetch(`/v1/agent/tasks/${id}/run`, {
      method: 'POST',
    }, { port: AGENT_PORT })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    return NextResponse.json({ error: 'Agent service unavailable' }, { status: 503 })
  }
}

import { NextRequest, NextResponse } from 'next/server'
import { proxyFetch } from '@/lib/proxy'
import { RateLimiter, getClientIP } from '@/lib/security'
import { checkAgentAuth } from '@/lib/agentAuth'

const AGENT_PORT = 8303
const limiter = new RateLimiter(30, 60 * 1000) // 30 per minute

export async function GET(request: NextRequest) {
  const authError = checkAgentAuth(request)
  if (authError) return authError
  const ip = getClientIP(request)
  const { allowed, retryAfterMs } = limiter.check(ip)
  if (!allowed) {
    return NextResponse.json({ error: 'Rate limit exceeded', retryAfterMs }, { status: 429 })
  }
  const { searchParams } = new URL(request.url)
  const page = Math.max(1, parseInt(searchParams.get('page') || '1', 10) || 1)
  const limit = Math.min(200, Math.max(1, parseInt(searchParams.get('limit') || '50', 10) || 50))

  try {
    const response = await proxyFetch(
      `/v1/agent/conversations?page=${page}&limit=${limit}`,
      {},
      { port: AGENT_PORT }
    )
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    return NextResponse.json({ error: 'Agent service unavailable' }, { status: 503 })
  }
}

export async function POST(request: NextRequest) {
  const authError = checkAgentAuth(request)
  if (authError) return authError
  const ip = getClientIP(request)
  const { allowed, retryAfterMs } = limiter.check(ip)
  if (!allowed) {
    return NextResponse.json({ error: 'Rate limit exceeded', retryAfterMs }, { status: 429 })
  }

  try {
    const body = await request.text()
    const response = await proxyFetch('/v1/agent/conversations', {
      method: 'POST',
      body,
    }, { port: AGENT_PORT })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    return NextResponse.json({ error: 'Agent service unavailable' }, { status: 503 })
  }
}

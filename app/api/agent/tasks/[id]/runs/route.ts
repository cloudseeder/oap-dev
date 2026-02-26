import { NextRequest, NextResponse } from 'next/server'
import { proxyFetch } from '@/lib/proxy'
import { RateLimiter, getClientIP } from '@/lib/security'
import { checkAgentAuth } from '@/lib/agentAuth'

const AGENT_PORT = 8303
const limiter = new RateLimiter(30, 60 * 1000) // 30 per minute

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const authError = checkAgentAuth(request)
  if (authError) return authError
  const ip = getClientIP(request)
  const { allowed, retryAfterMs } = limiter.check(ip)
  if (!allowed) {
    return NextResponse.json({ error: 'Rate limit exceeded', retryAfterMs }, { status: 429 })
  }
  const { id } = await params
  const { searchParams } = new URL(request.url)
  const page = Math.max(1, parseInt(searchParams.get('page') || '1', 10) || 1)
  const limit = Math.min(200, Math.max(1, parseInt(searchParams.get('limit') || '20', 10) || 20))

  try {
    const response = await proxyFetch(
      `/v1/agent/tasks/${id}/runs?page=${page}&limit=${limit}`,
      {},
      { port: AGENT_PORT }
    )
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    return NextResponse.json({ error: 'Agent service unavailable' }, { status: 503 })
  }
}

import { NextRequest, NextResponse } from 'next/server'

const AGENT_SECRET = process.env.AGENT_SECRET

/**
 * Check agent API authentication. When AGENT_SECRET env var is set,
 * requires matching Authorization Bearer or X-Agent-Token header.
 * Returns null if allowed, or a 401 response if denied.
 * When AGENT_SECRET is not configured (local dev), all requests pass through.
 */
export function checkAgentAuth(request: NextRequest): NextResponse | null {
  if (!AGENT_SECRET) return null
  const token =
    request.headers.get('x-agent-token') ||
    request.headers.get('authorization')?.replace('Bearer ', '')
  if (token !== AGENT_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }
  return null
}

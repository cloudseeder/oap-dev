import { NextRequest, NextResponse } from 'next/server'
import { proxyFetch } from '@/lib/proxy'
import { checkAgentAuth } from '@/lib/agentAuth'

const AGENT_PORT = 8303

export async function GET(request: NextRequest) {
  const authError = checkAgentAuth(request)
  if (authError) return authError
  try {
    const response = await proxyFetch('/v1/agent/health', {}, { port: AGENT_PORT })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    return NextResponse.json({ error: 'Agent service unavailable' }, { status: 503 })
  }
}

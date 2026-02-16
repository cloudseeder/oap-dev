import { NextRequest, NextResponse } from 'next/server'
import { proxyFetch } from '@/lib/proxy'
import { RateLimiter, getClientIP } from '@/lib/security'

const limiter = new RateLimiter(30, 60 * 1000)

const TRUST_PORT = 8301
const ALLOWED_PREFIXES = ['/v1/attest/', '/v1/attestations/', '/v1/keys', '/health']

async function handler(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const ip = getClientIP(request)
  const { allowed, retryAfterMs } = limiter.check(ip)
  if (!allowed) {
    return NextResponse.json({ error: 'Rate limit exceeded', retryAfterMs }, { status: 429 })
  }

  const { path } = await params
  const backendPath = '/' + path.join('/')

  if (!ALLOWED_PREFIXES.some(p => backendPath.startsWith(p))) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  }

  try {
    const init: RequestInit = { method: request.method }
    if (request.method === 'POST') {
      init.body = await request.text()
    }

    const response = await proxyFetch(backendPath, init, { port: TRUST_PORT })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    return NextResponse.json({ error: 'Trust service unavailable' }, { status: 503 })
  }
}

export const GET = handler
export const POST = handler

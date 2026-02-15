import { NextRequest, NextResponse } from 'next/server'
import { validateManifest } from '@/lib/manifest-v1'
import { fetchManifest } from '@/lib/dns'
import { RateLimiter, getClientIP } from '@/lib/security'

const limiter = new RateLimiter(20, 60 * 1000) // 20 per minute

export async function POST(request: NextRequest) {
  const ip = getClientIP(request)
  const { allowed, retryAfterMs } = limiter.check(ip)
  if (!allowed) {
    return NextResponse.json(
      { error: 'Rate limit exceeded', retryAfterMs },
      { status: 429 }
    )
  }

  let body: { url?: string }
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 })
  }

  if (!body.url || typeof body.url !== 'string') {
    return NextResponse.json({ error: 'url field is required' }, { status: 400 })
  }

  try {
    const { json } = await fetchManifest(body.url)
    const validation = validateManifest(json)
    return NextResponse.json({ validation, manifest: validation.valid ? json : null })
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Failed to fetch manifest'
    return NextResponse.json({ error: message }, { status: 422 })
  }
}

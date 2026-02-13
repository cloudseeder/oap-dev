import { NextRequest, NextResponse } from 'next/server'
import { getAllApps } from '@/lib/firestore'
import { searchApps, formatAppResult } from '@/lib/search'
import { searchLimiter, getClientIP } from '@/lib/security'
import type { AppDocument } from '@/lib/types'

// In-memory cache for getAllApps (5-min TTL)
let cachedApps: AppDocument[] | null = null
let cacheExpiry = 0

async function getCachedApps(): Promise<AppDocument[]> {
  const now = Date.now()
  if (cachedApps && now < cacheExpiry) {
    return cachedApps
  }
  cachedApps = await getAllApps()
  cacheExpiry = now + 5 * 60 * 1000 // 5 minutes
  return cachedApps
}

export async function GET(request: NextRequest) {
  // Rate limiting
  const ip = getClientIP(request)
  const { allowed, retryAfterMs } = searchLimiter.check(ip)
  if (!allowed) {
    return NextResponse.json(
      { status: 'error', errors: ['Too many requests'] },
      { status: 429, headers: { 'Retry-After': String(Math.ceil(retryAfterMs / 1000)) } }
    )
  }

  const q = request.nextUrl.searchParams.get('q')
  if (!q) {
    return NextResponse.json({ status: 'error', errors: ['q parameter required'] }, { status: 400 })
  }

  const allApps = await getCachedApps()
  const results = searchApps(q, allApps)

  return NextResponse.json({
    query: q,
    results: results.map(r => formatAppResult(r.app, r.score)),
    total: results.length,
    registry: 'registry.oap.dev',
    searched_at: new Date().toISOString(),
  })
}

import { NextRequest, NextResponse } from 'next/server'
import { getAllApps } from '@/lib/firestore'
import { allAppsLimiter, getClientIP } from '@/lib/security'

export async function GET(request: NextRequest) {
  // Rate limiting
  const ip = getClientIP(request)
  const { allowed, retryAfterMs } = allAppsLimiter.check(ip)
  if (!allowed) {
    return NextResponse.json(
      { status: 'error', errors: ['Too many requests'] },
      { status: 429, headers: { 'Retry-After': String(Math.ceil(retryAfterMs / 1000)) } }
    )
  }

  const rawPage = parseInt(request.nextUrl.searchParams.get('page') || '1')
  const rawLimit = parseInt(request.nextUrl.searchParams.get('limit') || '100')
  const page = Math.max(1, Number.isFinite(rawPage) ? rawPage : 1)
  const limit = Math.max(1, Math.min(Number.isFinite(rawLimit) ? rawLimit : 100, 1000))
  const offset = (page - 1) * limit

  const allApps = await getAllApps()

  // Sort by registered_at ascending for consistent pagination
  allApps.sort((a, b) => (a.registered_at || '').localeCompare(b.registered_at || ''))

  const pageApps = allApps.slice(offset, offset + limit)

  return NextResponse.json({
    apps: pageApps.map(a => ({
      domain: a.domain,
      manifest_url: a.manifest_url,
      manifest_hash: a.manifest_hash,
      last_verified: a.last_verified,
    })),
    total: allApps.length,
    page,
  })
}

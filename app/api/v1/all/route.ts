import { NextRequest, NextResponse } from 'next/server'
import { getAllApps } from '@/lib/firestore'

export async function GET(request: NextRequest) {
  const page = parseInt(request.nextUrl.searchParams.get('page') || '1')
  const limit = Math.min(parseInt(request.nextUrl.searchParams.get('limit') || '100'), 1000)
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

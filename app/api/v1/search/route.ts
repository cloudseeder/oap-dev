import { NextRequest, NextResponse } from 'next/server'
import { getAllApps } from '@/lib/firestore'
import { searchApps, formatAppResult } from '@/lib/search'

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get('q')
  if (!q) {
    return NextResponse.json({ status: 'error', errors: ['q parameter required'] }, { status: 400 })
  }

  const allApps = await getAllApps()
  const results = searchApps(q, allApps)

  return NextResponse.json({
    query: q,
    results: results.map(r => formatAppResult(r.app, r.score)),
    total: results.length,
    registry: 'registry.oap.dev',
    searched_at: new Date().toISOString(),
  })
}

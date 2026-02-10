import { NextRequest, NextResponse } from 'next/server'
import { getAppsByCategory } from '@/lib/firestore'
import { formatAppResult } from '@/lib/search'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ category: string }> }
) {
  const { category } = await params
  const page = parseInt(request.nextUrl.searchParams.get('page') || '1')
  const limit = Math.min(parseInt(request.nextUrl.searchParams.get('limit') || '20'), 100)

  const { apps, total } = await getAppsByCategory(category, page, limit)

  return NextResponse.json({
    category,
    apps: apps.map(a => formatAppResult(a)),
    total,
    page,
  })
}

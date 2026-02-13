import { NextRequest, NextResponse } from 'next/server'
import { getAppsByCategory } from '@/lib/firestore'
import { formatAppResult } from '@/lib/search'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ category: string }> }
) {
  const { category } = await params
  const rawPage = parseInt(request.nextUrl.searchParams.get('page') || '1')
  const rawLimit = parseInt(request.nextUrl.searchParams.get('limit') || '20')
  const page = Math.max(1, Number.isFinite(rawPage) ? rawPage : 1)
  const limit = Math.max(1, Math.min(Number.isFinite(rawLimit) ? rawLimit : 20, 100))

  const { apps, total } = await getAppsByCategory(category, page, limit)

  return NextResponse.json({
    category,
    apps: apps.map(a => formatAppResult(a)),
    total,
    page,
  })
}

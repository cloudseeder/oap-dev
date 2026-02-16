import { NextRequest, NextResponse } from 'next/server'
import { proxyFetch } from '@/lib/proxy'

const DASHBOARD_PORT = 8302

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const limit = Math.min(Math.max(parseInt(searchParams.get('limit') || '50', 10) || 50, 1), 100)
  const page = Math.max(parseInt(searchParams.get('page') || '1', 10) || 1, 1)

  try {
    const response = await proxyFetch(`/manifests?page=${page}&limit=${limit}`, {}, { port: DASHBOARD_PORT })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    return NextResponse.json({ error: 'Dashboard service unavailable' }, { status: 503 })
  }
}

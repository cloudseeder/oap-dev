import { NextRequest, NextResponse } from 'next/server'
import { proxyFetch } from '@/lib/proxy'

const DASHBOARD_PORT = 8302

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const history = searchParams.get('history')

  try {
    let path = '/stats'
    if (history) {
      const days = Math.min(Math.max(parseInt(history, 10) || 30, 1), 365)
      path = `/stats/history?days=${days}`
    }
    const response = await proxyFetch(path, {}, { port: DASHBOARD_PORT })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    return NextResponse.json({ error: 'Dashboard service unavailable' }, { status: 503 })
  }
}

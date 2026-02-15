import { NextResponse } from 'next/server'
import { proxyFetch } from '@/lib/proxy'

export async function GET() {
  try {
    const response = await proxyFetch('/v1/manifests')
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    return NextResponse.json({ error: 'Discovery service unavailable' }, { status: 503 })
  }
}

import { NextResponse } from 'next/server'
import { proxyFetch } from '@/lib/proxy'

export async function GET() {
  try {
    const response = await proxyFetch('/health')
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    return NextResponse.json({ status: 'unavailable', ollama: false, index_count: 0 }, { status: 503 })
  }
}

import { NextResponse } from 'next/server'
import { getStats } from '@/lib/firestore'

export async function GET() {
  const stats = await getStats()

  return NextResponse.json({
    total_apps: stats.total_apps,
    categories: stats.total_categories,
    verified_healthy: stats.verified_healthy,
    registered_today: stats.registered_today,
    registry_version: '0.1',
  })
}

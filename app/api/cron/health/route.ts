import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/firebase'
import { checkHealth } from '@/lib/dns'
import { updateStats } from '@/lib/firestore'
import type { AppDocument } from '@/lib/types'

export async function GET(request: NextRequest) {
  const authHeader = request.headers.get('authorization')
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const snapshot = await db.collection('apps').where('delisted', '==', false).get()
  const apps = snapshot.docs.map(doc => ({ id: doc.id, data: doc.data() as AppDocument }))

  let checked = 0
  let healthy = 0

  for (const { id, data } of apps) {
    const manifest: Record<string, unknown> = JSON.parse(data.manifest_json)
    const healthOk = await checkHealth(manifest)

    const update: Record<string, unknown> = {
      uptime_checks_total: (data.uptime_checks_total || 0) + 1,
      health_ok: healthOk !== false,
      last_verified: new Date().toISOString(),
    }

    if (healthOk !== false) {
      update.uptime_checks_passed = (data.uptime_checks_passed || 0) + 1
      healthy++
    }

    await db.collection('apps').doc(id).update(update)
    checked++
  }

  await updateStats()

  return NextResponse.json({
    status: 'ok',
    checked,
    healthy,
    timestamp: new Date().toISOString(),
  })
}

import { NextRequest, NextResponse } from 'next/server'
import { getApp } from '@/lib/firestore'
import { db } from '@/lib/firebase'
import type { AppDocument } from '@/lib/types'

const MAX_BUILDER_VERIFIED_DOMAINS_LOOKUP = 10

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ domain: string }> }
) {
  const { domain } = await params
  const app = await getApp(domain)

  if (!app) {
    return NextResponse.json({ status: 'error', errors: ['App not found'] }, { status: 404 })
  }

  const uptime = app.uptime_checks_total > 0
    ? parseFloat(((app.uptime_checks_passed / app.uptime_checks_total) * 100).toFixed(1))
    : undefined

  // Find other apps by same builder (capped to prevent abuse)
  const builderDomains = (app.builder_verified_domains || []).slice(0, MAX_BUILDER_VERIFIED_DOMAINS_LOOKUP)
  let otherApps: { domain: string; name: string }[] = []
  if (builderDomains.length > 0) {
    const otherDomains = builderDomains.filter(d => d !== domain)
    if (otherDomains.length > 0) {
      const refs = otherDomains.map(d => db.collection('apps').doc(d))
      const docs = await db.getAll(...refs)
      otherApps = docs
        .filter(d => d.exists)
        .map(d => {
          const data = d.data() as AppDocument
          return { domain: data.domain, name: data.name }
        })
        .filter(a => a.domain && a.name)
    }
  }

  return NextResponse.json({
    domain: app.domain,
    manifest: JSON.parse(app.manifest_json),
    registry_meta: {
      registered_at: app.registered_at,
      last_verified: app.last_verified,
      dns_verified: app.dns_verified,
      health_ok: app.health_ok,
      manifest_hash: app.manifest_hash,
      ...(uptime !== undefined && { uptime_30d: uptime }),
      builder_other_apps: otherApps,
    },
  })
}

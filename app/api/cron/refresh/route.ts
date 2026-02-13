import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/firebase'
import { fetchManifestForDomain, verifyDNS, checkHealth, hashManifest } from '@/lib/dns'
import { validateManifest } from '@/lib/manifest'
import { updateStats, updateCategoryAggregates } from '@/lib/firestore'
import { timingSafeCompare } from '@/lib/security'
import type { AppDocument, PricingModel } from '@/lib/types'

const FLAG_THRESHOLD_DAYS = 7
const DELIST_THRESHOLD_DAYS = 30
const MAX_BUILDER_VERIFIED_DOMAINS = 10

export async function GET(request: NextRequest) {
  const authHeader = request.headers.get('authorization')
  const expected = `Bearer ${process.env.CRON_SECRET}`
  if (!authHeader || !timingSafeCompare(authHeader, expected)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const snapshot = await db.collection('apps').where('delisted', '==', false).get()
  const apps = snapshot.docs.map(doc => ({ id: doc.id, data: doc.data() as AppDocument }))

  let refreshed = 0
  let flagged = 0
  let delisted = 0
  let failed = 0

  const now = new Date()
  const nowISO = now.toISOString()

  for (const { id, data } of apps) {
    try {
      // Use fetchManifestForDomain to prevent domain spoofing
      const { json: manifest } = await fetchManifestForDomain(id)
      const { errors } = validateManifest(manifest)

      if (errors.length > 0) {
        failed++
        continue
      }

      const dnsVerified = await verifyDNS(id)
      const healthOk = await checkHealth(manifest)
      const manifestHash = hashManifest(manifest)

      const identity = manifest.identity as Record<string, unknown>
      const capabilities = manifest.capabilities as Record<string, unknown>
      const pricing = manifest.pricing as Record<string, unknown>
      const builder = manifest.builder as Record<string, unknown>
      const newCategories = ((capabilities?.categories as string[]) || []).map(c => c.toLowerCase())
      const builderVerifiedDomains = ((builder?.verified_domains as string[]) || []).slice(0, MAX_BUILDER_VERIFIED_DOMAINS)

      // Handle category aggregate changes
      const oldCategories = data.categories || []
      const categoriesChanged = JSON.stringify(oldCategories.sort()) !== JSON.stringify([...newCategories].sort())
      if (categoriesChanged) {
        await updateCategoryAggregates(oldCategories, id, 'remove')
        await updateCategoryAggregates(newCategories, id, 'add')
      }

      await db.collection('apps').doc(id).update({
        manifest_json: JSON.stringify(manifest),
        manifest_hash: manifestHash,
        name: identity.name as string,
        tagline: (identity.tagline as string) || '',
        description: (identity.description as string) || '',
        app_url: identity.url as string,
        summary: (capabilities?.summary as string) || '',
        solves: (capabilities?.solves as string[]) || [],
        ideal_for: (capabilities?.ideal_for as string[]) || [],
        categories: newCategories,
        differentiators: (capabilities?.differentiators as string[]) || [],
        pricing_model: (pricing?.model as PricingModel) || 'free',
        starting_price: (pricing?.starting_price as string) || null,
        builder_name: (builder?.name as string) || '',
        builder_verified_domains: builderVerifiedDomains,
        dns_verified: dnsVerified,
        health_ok: healthOk !== false,
        manifest_valid: true,
        last_verified: nowISO,
        last_fetched: nowISO,
        flagged: false,
        flag_reason: null,
      })

      refreshed++
    } catch {
      // Manifest fetch failed — check staleness for flagging/delisting
      failed++
      const lastFetched = data.last_fetched ? new Date(data.last_fetched) : null
      if (!lastFetched) continue

      const daysSinceLastFetch = (now.getTime() - lastFetched.getTime()) / (1000 * 60 * 60 * 24)

      if (daysSinceLastFetch >= DELIST_THRESHOLD_DAYS) {
        await db.collection('apps').doc(id).update({
          delisted: true,
          flagged: true,
          flag_reason: `Manifest unreachable for ${Math.floor(daysSinceLastFetch)} days`,
          last_verified: nowISO,
        })
        // Remove from category aggregates
        if (data.categories?.length) {
          await updateCategoryAggregates(data.categories, id, 'remove')
        }
        delisted++
      } else if (daysSinceLastFetch >= FLAG_THRESHOLD_DAYS && !data.flagged) {
        await db.collection('apps').doc(id).update({
          flagged: true,
          flag_reason: `Manifest unreachable for ${Math.floor(daysSinceLastFetch)} days`,
          last_verified: nowISO,
        })
        flagged++
      }
    }
  }

  await updateStats()

  return NextResponse.json({
    status: 'ok',
    refreshed,
    flagged,
    delisted,
    failed,
    total: apps.length,
    timestamp: nowISO,
  })
}

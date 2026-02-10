import { NextRequest, NextResponse } from 'next/server'
import { getApp, updateApp } from '@/lib/firestore'
import { fetchManifest, verifyDNS, checkHealth, hashManifest } from '@/lib/dns'
import { validateManifest } from '@/lib/manifest'
import type { PricingModel } from '@/lib/types'

export async function PUT(
  _request: NextRequest,
  { params }: { params: Promise<{ domain: string }> }
) {
  const { domain } = await params
  const existing = await getApp(domain)

  if (!existing) {
    return NextResponse.json({ status: 'error', errors: ['App not found'] }, { status: 404 })
  }

  try {
    const { json: manifest } = await fetchManifest(existing.app_url)

    const { errors } = validateManifest(manifest)
    if (errors.length > 0) {
      return NextResponse.json({ status: 'error', errors }, { status: 400 })
    }

    const dnsVerified = await verifyDNS(domain)
    const healthOk = await checkHealth(manifest)
    const manifestHash = hashManifest(manifest)
    const now = new Date().toISOString()

    const identity = manifest.identity as Record<string, unknown>
    const capabilities = manifest.capabilities as Record<string, unknown>
    const pricing = manifest.pricing as Record<string, unknown>
    const builder = manifest.builder as Record<string, unknown>
    const categories = ((capabilities?.categories as string[]) || []).map(c => c.toLowerCase())

    await updateApp(domain, {
      manifest_json: JSON.stringify(manifest),
      manifest_hash: manifestHash,
      name: identity.name as string,
      tagline: (identity.tagline as string) || '',
      description: (identity.description as string) || '',
      app_url: identity.url as string,
      summary: (capabilities?.summary as string) || '',
      solves: (capabilities?.solves as string[]) || [],
      ideal_for: (capabilities?.ideal_for as string[]) || [],
      categories,
      differentiators: (capabilities?.differentiators as string[]) || [],
      pricing_model: (pricing?.model as PricingModel) || 'free',
      starting_price: (pricing?.starting_price as string) || null,
      builder_name: (builder?.name as string) || '',
      builder_verified_domains: (builder?.verified_domains as string[]) || [],
      dns_verified: dnsVerified,
      health_ok: healthOk !== false,
      manifest_valid: true,
      last_verified: now,
      last_fetched: now,
    })

    return NextResponse.json({ status: 'refreshed', domain, manifest_hash: manifestHash })
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Unknown error'
    return NextResponse.json({ status: 'error', errors: [msg] }, { status: 500 })
  }
}

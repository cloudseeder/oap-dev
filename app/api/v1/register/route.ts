import { NextRequest, NextResponse } from 'next/server'
import { extractDomain, fetchManifest, verifyDNS, checkHealth, hashManifest } from '@/lib/dns'
import { validateManifest } from '@/lib/manifest'
import { getApp, createApp } from '@/lib/firestore'
import type { AppDocument, PricingModel } from '@/lib/types'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { url } = body

    if (!url) {
      return NextResponse.json({ status: 'error', errors: ['url is required'] }, { status: 400 })
    }

    const domain = extractDomain(url)
    if (!domain) {
      return NextResponse.json({ status: 'error', errors: ['Invalid URL'] }, { status: 400 })
    }

    // Check if already registered
    const existing = await getApp(domain)
    if (existing) {
      return NextResponse.json({
        status: 'error',
        errors: [`${domain} is already registered. Use PUT /api/v1/apps/${domain}/refresh to update.`],
      }, { status: 409 })
    }

    // Fetch manifest
    let manifest: Record<string, unknown>
    let manifestUrl: string
    try {
      ({ json: manifest, manifestUrl } = await fetchManifest(url))
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Unknown error'
      return NextResponse.json({
        status: 'error',
        errors: [`Could not fetch manifest from ${url}/.well-known/oap.json: ${msg}`],
      }, { status: 400 })
    }

    // Validate manifest
    const { errors } = validateManifest(manifest)
    if (errors.length > 0) {
      return NextResponse.json({ status: 'error', errors }, { status: 400 })
    }

    // Verify DNS (non-blocking)
    const dnsVerified = await verifyDNS(domain)

    // Check health
    const healthOk = await checkHealth(manifest)

    // Build app document
    const manifestHash = hashManifest(manifest)
    const now = new Date().toISOString()
    const identity = manifest.identity as Record<string, unknown>
    const capabilities = manifest.capabilities as Record<string, unknown>
    const pricing = manifest.pricing as Record<string, unknown>
    const builder = manifest.builder as Record<string, unknown>
    const categories = (capabilities?.categories as string[]) || []

    const appDoc: AppDocument = {
      domain,
      manifest_url: manifestUrl,
      manifest_json: JSON.stringify(manifest),
      manifest_hash: manifestHash,
      name: identity.name as string,
      tagline: (identity.tagline as string) || '',
      description: (identity.description as string) || '',
      app_url: identity.url as string,
      summary: (capabilities?.summary as string) || '',
      solves: (capabilities?.solves as string[]) || [],
      ideal_for: (capabilities?.ideal_for as string[]) || [],
      categories: categories.map(c => c.toLowerCase()),
      differentiators: (capabilities?.differentiators as string[]) || [],
      pricing_model: (pricing?.model as PricingModel) || 'free',
      starting_price: (pricing?.starting_price as string) || null,
      builder_name: (builder?.name as string) || '',
      builder_verified_domains: (builder?.verified_domains as string[]) || [],
      dns_verified: dnsVerified,
      health_ok: healthOk !== false,
      manifest_valid: true,
      registered_at: now,
      last_verified: now,
      last_fetched: now,
      uptime_checks_passed: 0,
      uptime_checks_total: 0,
      flagged: false,
      flag_reason: null,
      delisted: false,
    }

    await createApp(domain, appDoc)

    return NextResponse.json({
      status: 'registered',
      domain,
      manifest_url: manifestUrl,
      dns_verified: dnsVerified,
      manifest_valid: true,
      health_ok: healthOk !== false,
      indexed_at: now,
      ...(!dnsVerified && {
        dns_hint: `Add DNS TXT record: _oap.${domain} → v=oap1; cat=${categories.slice(0, 3).join(',')}; manifest=${manifestUrl}`,
      }),
    }, { status: 201 })
  } catch (e) {
    console.error('Registration error:', e)
    return NextResponse.json({ status: 'error', errors: ['Internal server error'] }, { status: 500 })
  }
}

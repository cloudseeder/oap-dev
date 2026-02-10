import Link from 'next/link'
import { notFound } from 'next/navigation'
import TrustBadges from '@/components/TrustBadges'
import ManifestViewer from '@/components/ManifestViewer'
import { getApp } from '@/lib/firestore'
import { db } from '@/lib/firebase'
import type { OAPManifest, AppDocument } from '@/lib/types'
import type { Metadata } from 'next'

export const dynamic = 'force-dynamic'

interface PageProps {
  params: Promise<{ domain: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { domain } = await params
  const app = await getApp(domain)
  if (!app) return { title: 'App Not Found — OAP Registry' }
  return {
    title: `${app.name} — OAP Registry`,
    description: app.tagline,
  }
}

export default async function AppDetailPage({ params }: PageProps) {
  const { domain } = await params
  const app = await getApp(domain)
  if (!app) notFound()

  const manifest: OAPManifest = JSON.parse(app.manifest_json)

  const uptime = app.uptime_checks_total > 0
    ? parseFloat(((app.uptime_checks_passed / app.uptime_checks_total) * 100).toFixed(1))
    : undefined

  // Other apps by builder
  const builderDomains = (app.builder_verified_domains || []).filter(d => d !== domain)
  let otherApps: { domain: string; name: string }[] = []
  if (builderDomains.length > 0) {
    const refs = builderDomains.map(d => db.collection('apps').doc(d))
    const docs = await db.getAll(...refs)
    otherApps = docs
      .filter(d => d.exists)
      .map(d => {
        const data = d.data() as AppDocument
        return { domain: data.domain, name: data.name }
      })
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{app.name}</h1>
          <p className="mt-1 text-gray-600">{app.tagline}</p>
          <a
            href={app.app_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-block text-sm text-primary hover:underline"
          >
            {app.domain}
          </a>
        </div>
        <TrustBadges
          dnsVerified={app.dns_verified}
          healthOk={app.health_ok}
          uptime={uptime}
        />
      </div>

      {/* Categories */}
      <div className="mt-4 flex flex-wrap gap-1.5">
        {app.categories.map(cat => (
          <Link
            key={cat}
            href={`/r/categories/${cat}`}
            className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600 hover:bg-gray-200"
          >
            {cat}
          </Link>
        ))}
      </div>

      {/* Pricing Card */}
      <div className="mt-6 rounded-lg border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center gap-4">
          <span className="rounded-full bg-primary-50 px-3 py-1 text-sm font-medium capitalize text-primary">
            {app.pricing_model}
          </span>
          {app.starting_price && (
            <span className="text-sm text-gray-700">{app.starting_price}</span>
          )}
        </div>
      </div>

      {/* Manifest Viewer */}
      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Application Details</h2>
        <ManifestViewer manifest={manifest} />
      </div>

      {/* Registry Metadata */}
      <div className="mt-8 rounded-lg border border-gray-200 p-4">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500">
          Registry Metadata
        </h3>
        <div className="space-y-2 text-sm">
          <div className="flex gap-3">
            <span className="w-36 text-gray-500">Registered</span>
            <span className="text-gray-900">{app.registered_at}</span>
          </div>
          <div className="flex gap-3">
            <span className="w-36 text-gray-500">Last Verified</span>
            <span className="text-gray-900">{app.last_verified || 'Never'}</span>
          </div>
          <div className="flex gap-3">
            <span className="w-36 text-gray-500">Manifest Hash</span>
            <span className="font-mono text-gray-900">{app.manifest_hash}</span>
          </div>
        </div>
      </div>

      {/* Other Apps by Builder */}
      {otherApps.length > 0 && (
        <div className="mt-8">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500">
            Other Apps by {app.builder_name}
          </h3>
          <div className="space-y-2">
            {otherApps.map(other => (
              <Link
                key={other.domain}
                href={`/r/apps/${other.domain}`}
                className="block rounded-lg border border-gray-200 p-3 text-sm hover:shadow-sm"
              >
                <span className="font-medium text-gray-900">{other.name}</span>
                <span className="ml-2 text-gray-500">{other.domain}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Raw JSON (collapsible) */}
      <details className="mt-8">
        <summary className="cursor-pointer text-sm font-medium text-gray-600 hover:text-gray-900">
          View Raw Manifest JSON
        </summary>
        <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-900 p-4 text-sm text-gray-100">
          <code>{JSON.stringify(manifest, null, 2)}</code>
        </pre>
      </details>
    </div>
  )
}

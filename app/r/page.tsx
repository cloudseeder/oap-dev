import Link from 'next/link'
import SearchBar from '@/components/SearchBar'
import AppCard from '@/components/AppCard'
import CodeBlock from '@/components/CodeBlock'
import { getAllApps, getCategories, getStats } from '@/lib/firestore'
import { searchApps, formatAppResult } from '@/lib/search'
import type { Metadata } from 'next'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'OAP Registry — Discover Apps for AI Agents',
  description: 'Search and discover web applications through the Open Application Protocol registry.',
}

export default async function RegistryHome({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>
}) {
  const { q } = await searchParams
  const stats = await getStats()
  const categories = await getCategories()

  let searchResults = null
  if (q) {
    const allApps = await getAllApps()
    const results = searchApps(q, allApps)
    searchResults = results.map(r => formatAppResult(r.app, r.score))
  }

  return (
    <div>
      {/* Search Hero */}
      <section className="bg-gradient-to-b from-primary-50 to-white px-4 py-12 text-center">
        <h1 className="text-3xl font-bold text-gray-900">Discover Apps</h1>
        <p className="mt-2 text-gray-600">
          Search the OAP registry for applications, rated by trust signals.
        </p>
        <div className="mt-6 flex justify-center">
          <SearchBar defaultValue={q} />
        </div>
        <div className="mt-3 flex justify-center gap-2">
          {['CRM', 'transcription', 'HOA management', 'civic tech'].map(example => (
            <Link
              key={example}
              href={`/r?q=${encodeURIComponent(example)}`}
              className="rounded-full border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
            >
              {example}
            </Link>
          ))}
        </div>
      </section>

      {/* Stats Bar */}
      <section className="border-b border-gray-200 bg-white px-4 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-center gap-8 text-center text-sm">
          <Stat label="Apps" value={stats.total_apps} />
          <Stat label="Categories" value={stats.total_categories} />
          <Stat label="Healthy" value={stats.verified_healthy} />
        </div>
      </section>

      <div className="mx-auto max-w-4xl px-4 py-8">
        {/* Search Results */}
        {searchResults !== null && (
          <div className="mb-8">
            <h2 className="mb-4 text-lg font-semibold text-gray-900">
              {searchResults.length > 0
                ? `${searchResults.length} result${searchResults.length !== 1 ? 's' : ''} for "${q}"`
                : `No results for "${q}"`}
            </h2>
            <div className="space-y-4">
              {searchResults.map(app => (
                <AppCard key={app.domain} app={app} />
              ))}
            </div>
          </div>
        )}

        {/* Category Browse */}
        {!q && (
          <div className="mb-12">
            <h2 className="mb-4 text-lg font-semibold text-gray-900">Browse by Category</h2>
            <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
              {categories.map(cat => (
                <Link
                  key={cat.category}
                  href={`/r/categories/${cat.category}`}
                  className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3 hover:shadow-sm"
                >
                  <span className="text-sm font-medium text-gray-900">{cat.category}</span>
                  <span className="text-xs text-gray-500">{cat.count} app{cat.count !== 1 ? 's' : ''}</span>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Register CTA */}
        <div id="register" className="rounded-lg border border-gray-200 bg-gray-50 p-6">
          <h2 className="text-lg font-semibold text-gray-900">Register Your App</h2>
          <p className="mt-2 text-sm text-gray-600">
            Add your app to the registry with a single API call. No approval needed.
          </p>
          <div className="mt-4">
            <CodeBlock
              code={`curl -X POST https://registry.oap.dev/api/v1/register \\
  -H "Content-Type: application/json" \\
  -d '{"url": "https://yourapp.com"}'`}
            />
          </div>
          <p className="mt-3 text-xs text-gray-500">
            Your app must have a valid manifest at <code className="rounded bg-gray-200 px-1 py-0.5 text-xs">/.well-known/oap.json</code>.{' '}
            <Link href="/docs/quickstart" className="text-primary hover:underline">
              Quick start guide
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-xl font-bold text-gray-900">{value}</div>
      <div className="text-gray-500">{label}</div>
    </div>
  )
}

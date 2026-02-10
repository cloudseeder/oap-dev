import Link from 'next/link'
import TrustBadges from './TrustBadges'
import type { AppResult } from '@/lib/types'

export default function AppCard({ app }: { app: AppResult }) {
  return (
    <Link
      href={`/r/apps/${app.domain}`}
      className="block rounded-lg border border-gray-200 p-5 transition-shadow hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold text-gray-900">{app.name}</h3>
          <p className="mt-1 text-sm text-gray-500">{app.domain}</p>
          <p className="mt-2 text-sm text-gray-700">{app.tagline}</p>
        </div>
        {app.match_score !== undefined && (
          <span className="shrink-0 rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary">
            {Math.round(app.match_score * 100)}% match
          </span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {app.categories.slice(0, 4).map(cat => (
          <span
            key={cat}
            className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-600"
          >
            {cat}
          </span>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="capitalize">{app.pricing.model}</span>
          {app.pricing.starting_price && (
            <span>&middot; {app.pricing.starting_price}</span>
          )}
        </div>
        <TrustBadges
          dnsVerified={app.trust_signals.dns_verified}
          healthOk={app.trust_signals.health_ok}
          uptime={app.trust_signals.uptime_30d}
        />
      </div>
    </Link>
  )
}

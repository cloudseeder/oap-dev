import DashboardStats from '@/components/DashboardStats'
import DashboardManifestList from '@/components/DashboardManifestList'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Dashboard — OAP',
  description: 'OAP adoption dashboard — track manifest growth and health across the ecosystem.',
}

export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
      <h1 className="text-3xl font-bold text-gray-900">Adoption Dashboard</h1>
      <p className="mt-2 text-gray-600">
        Live stats on OAP manifest adoption. The crawler checks known domains every 6 hours
        and tracks growth, health status, and manifest changes over time.
      </p>

      <div className="mt-8">
        <DashboardStats />
      </div>

      <div className="mt-10">
        <h2 className="text-xl font-semibold text-gray-900">Tracked Manifests</h2>
        <p className="mt-1 text-sm text-gray-500">
          All manifests the crawler has discovered and is actively monitoring.
        </p>
        <div className="mt-4">
          <DashboardManifestList />
        </div>
      </div>
    </div>
  )
}

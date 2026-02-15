import DiscoverSearch from '@/components/DiscoverSearch'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Discovery — OAP',
  description: 'Find capabilities by describing your task in natural language.',
}

export default function DiscoverPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
      <h1 className="text-3xl font-bold text-gray-900">Discovery</h1>
      <p className="mt-2 text-gray-600">
        Describe a task in natural language. The discovery engine searches a local vector index
        of OAP manifests and uses a small LLM to pick the best match.
      </p>
      <p className="mt-1 text-sm text-gray-500">
        Reference implementation of the architecture described in{' '}
        <a href="/docs/architecture" className="text-primary hover:underline">ARCHITECTURE.md</a>.
      </p>
      <div className="mt-8">
        <DiscoverSearch />
      </div>
    </div>
  )
}

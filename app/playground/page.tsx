import PlaygroundEditor from '@/components/PlaygroundEditor'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Manifest Playground — OAP',
  description: 'Validate and preview OAP v1.0 manifests.',
}

export default function PlaygroundPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
      <h1 className="text-3xl font-bold text-gray-900">Manifest Playground</h1>
      <p className="mt-2 text-gray-600">
        Validate an OAP v1.0 manifest by pasting JSON or fetching from a live URL.
      </p>
      <div className="mt-8">
        <PlaygroundEditor />
      </div>
    </div>
  )
}

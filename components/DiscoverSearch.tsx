'use client'

import { useState, useCallback } from 'react'
import DiscoverResult from '@/components/DiscoverResult'

interface DiscoverMatch {
  domain: string
  name: string
  description: string
  invoke: { method: string; url: string }
  score: number
  reason?: string
}

interface LLMCallMeta {
  model: string
  prompt_tokens: number
  generated_tokens: number
  total_ms: number
  prompt?: string | null
  system_prompt?: string | null
}

interface DiscoverMeta {
  embed: LLMCallMeta
  reason?: LLMCallMeta | null
  search_results: number
  total_ms: number
}

interface DiscoverResponse {
  task: string
  match: DiscoverMatch | null
  candidates: DiscoverMatch[]
  meta?: DiscoverMeta | null
}

export default function DiscoverSearch() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<DiscoverResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [serviceHealth, setServiceHealth] = useState<{ status: string; index_count: number } | null>(null)

  const discover = useCallback(async () => {
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const resp = await fetch('/api/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: query.trim(), top_k: 5 }),
      })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        setError(data.error || `Service returned ${resp.status}`)
        return
      }
      const data: DiscoverResponse = await resp.json()
      setResult(data)
    } catch {
      setError('Could not reach discovery service')
    } finally {
      setLoading(false)
    }
  }, [query])

  const checkHealth = useCallback(async () => {
    try {
      const resp = await fetch('/api/discover/health')
      const data = await resp.json()
      setServiceHealth(data)
    } catch {
      setServiceHealth({ status: 'unavailable', index_count: 0 })
    }
  }, [])

  return (
    <div className="space-y-6">
      {/* Search Input */}
      <div>
        <label htmlFor="discover-input" className="mb-2 block text-sm font-medium text-gray-700">
          Describe your task in natural language
        </label>
        <div className="flex gap-3">
          <input
            id="discover-input"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && discover()}
            placeholder="e.g., search text files for a regex pattern"
            className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <button
            onClick={discover}
            disabled={loading || !query.trim()}
            className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
          >
            {loading ? 'Searching...' : 'Discover'}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <DiscoverResult match={result.match} candidates={result.candidates} task={result.task} meta={result.meta} />
      )}

      {/* Service Health */}
      <div className="border-t border-gray-200 pt-4">
        <button
          onClick={checkHealth}
          className="text-xs text-gray-400 hover:text-gray-600"
        >
          Check service health
        </button>
        {serviceHealth && (
          <div className="mt-2 flex items-center gap-3 text-xs text-gray-500">
            <span className={`inline-block h-2 w-2 rounded-full ${serviceHealth.status === 'ok' ? 'bg-green-500' : 'bg-red-500'}`} />
            <span>Status: {serviceHealth.status}</span>
            <span>Indexed manifests: {serviceHealth.index_count}</span>
          </div>
        )}
      </div>
    </div>
  )
}

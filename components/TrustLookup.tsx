'use client'

import { useState, useCallback } from 'react'
import TrustBadges from '@/components/TrustBadges'

interface Attestation {
  domain: string
  layer: number
  jws: string
  manifest_hash: string
  issued_at: string
  expires_at: string
  verification_method?: string
}

export default function TrustLookup() {
  const [domain, setDomain] = useState('')
  const [attestations, setAttestations] = useState<Attestation[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const lookup = useCallback(async () => {
    if (!domain.trim()) return
    setLoading(true)
    setError(null)
    setAttestations(null)
    try {
      const resp = await fetch(`/api/trust/v1/attestations/${encodeURIComponent(domain.trim())}`)
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        setError(data.error || data.detail || `Status ${resp.status}`)
        return
      }
      const data = await resp.json()
      setAttestations(data.attestations || [])
    } catch {
      setError('Could not reach trust service')
    } finally {
      setLoading(false)
    }
  }, [domain])

  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="lookup-domain" className="mb-2 block text-sm font-medium text-gray-700">
          Look up attestations for a domain
        </label>
        <div className="flex gap-3">
          <input
            id="lookup-domain"
            type="text"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && lookup()}
            placeholder="example.com"
            className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <button
            onClick={lookup}
            disabled={loading || !domain.trim()}
            className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
          >
            {loading ? 'Looking up...' : 'Look Up'}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
      )}

      {attestations !== null && (
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          {attestations.length === 0 ? (
            <p className="text-sm text-gray-500">No attestations found for {domain}.</p>
          ) : (
            <div className="space-y-4">
              <TrustBadges attestations={attestations} />
              <div className="space-y-3">
                {attestations.map((a, i) => (
                  <div key={i} className="rounded border border-gray-100 bg-gray-50 p-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">Layer {a.layer}</span>
                      <span className="text-xs text-gray-500">
                        Expires {new Date(a.expires_at).toLocaleDateString()}
                      </span>
                    </div>
                    {a.verification_method && (
                      <p className="mt-1 text-xs text-gray-500">Method: {a.verification_method}</p>
                    )}
                    <p className="mt-1 truncate font-mono text-xs text-gray-400">Hash: {a.manifest_hash}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

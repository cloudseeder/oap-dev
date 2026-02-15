'use client'

import { useState, useCallback } from 'react'

interface Layer0Result {
  domain: string
  https: boolean
  valid_json: boolean
  has_required_fields: boolean
  valid_version: boolean
  manifest_hash: string | null
  passed: boolean
  errors: string[]
}

interface ChallengeResponse {
  domain: string
  method: string
  token: string
  instructions: string
  expires_at: string
  layer0: Layer0Result
}

interface StatusResponse {
  domain: string
  challenge_verified: boolean
  attestation: {
    domain: string
    layer: number
    jws: string
    manifest_hash: string
    issued_at: string
    expires_at: string
  } | null
  error: string | null
}

type Step = 'input' | 'challenge' | 'verified'

export default function TrustFlow() {
  const [domain, setDomain] = useState('')
  const [method, setMethod] = useState('dns')
  const [step, setStep] = useState<Step>('input')
  const [challenge, setChallenge] = useState<ChallengeResponse | null>(null)
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const initiate = useCallback(async () => {
    if (!domain.trim()) return
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch('/api/trust/v1/attest/domain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: domain.trim(), method }),
      })
      const data = await resp.json()
      if (!resp.ok) {
        setError(data.detail || data.error || `Status ${resp.status}`)
        return
      }
      setChallenge(data)
      setStep('challenge')
    } catch {
      setError('Could not reach trust service')
    } finally {
      setLoading(false)
    }
  }, [domain, method])

  const verify = useCallback(async () => {
    if (!challenge) return
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch(`/api/trust/v1/attest/domain/${encodeURIComponent(challenge.domain)}/status`)
      const data = await resp.json()
      if (!resp.ok) {
        setError(data.detail || data.error || `Status ${resp.status}`)
        return
      }
      setStatus(data)
      if (data.challenge_verified) {
        setStep('verified')
      } else {
        setError(data.error || 'Challenge not yet verified. Make sure you\'ve added the DNS record or HTTP file.')
      }
    } catch {
      setError('Could not reach trust service')
    } finally {
      setLoading(false)
    }
  }, [challenge])

  const reset = () => {
    setStep('input')
    setChallenge(null)
    setStatus(null)
    setError(null)
  }

  return (
    <div className="space-y-6">
      {/* Step 1: Enter domain */}
      {step === 'input' && (
        <div className="space-y-4">
          <div>
            <label htmlFor="trust-domain" className="mb-2 block text-sm font-medium text-gray-700">
              Domain to attest
            </label>
            <input
              id="trust-domain"
              type="text"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && initiate()}
              placeholder="example.com"
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">Challenge method</label>
            <div className="flex gap-3">
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="radio"
                  name="method"
                  value="dns"
                  checked={method === 'dns'}
                  onChange={(e) => setMethod(e.target.value)}
                  className="text-primary"
                />
                DNS TXT record
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="radio"
                  name="method"
                  value="http"
                  checked={method === 'http'}
                  onChange={(e) => setMethod(e.target.value)}
                  className="text-primary"
                />
                HTTP file
              </label>
            </div>
          </div>
          <button
            onClick={initiate}
            disabled={loading || !domain.trim()}
            className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
          >
            {loading ? 'Checking...' : 'Start Attestation'}
          </button>
        </div>
      )}

      {/* Step 2: Layer 0 results + challenge instructions */}
      {step === 'challenge' && challenge && (
        <div className="space-y-4">
          {/* Layer 0 Results */}
          <div className={`rounded-lg border p-4 ${challenge.layer0.passed ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
            <h3 className="font-medium text-gray-900">Layer 0 — Baseline Checks</h3>
            <div className="mt-2 space-y-1 text-sm">
              <Check label="HTTPS" ok={challenge.layer0.https} />
              <Check label="Valid JSON" ok={challenge.layer0.valid_json} />
              <Check label="Required fields" ok={challenge.layer0.has_required_fields} />
              <Check label="Valid version" ok={challenge.layer0.valid_version} />
            </div>
            {challenge.layer0.errors.length > 0 && (
              <ul className="mt-2 text-sm text-red-700">
                {challenge.layer0.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            )}
          </div>

          {/* Challenge Instructions */}
          {challenge.layer0.passed && (
            <div className="rounded-lg border border-primary-200 bg-primary-50 p-4">
              <h3 className="font-medium text-primary-900">Layer 1 — Domain Challenge</h3>
              <p className="mt-2 whitespace-pre-wrap text-sm text-primary-800">{challenge.instructions}</p>
              <div className="mt-3">
                <span className="text-xs text-primary-600">Token:</span>
                <pre className="mt-1 overflow-x-auto rounded bg-primary-100 p-2 font-mono text-xs text-primary-900">
                  {challenge.token}
                </pre>
              </div>
              <p className="mt-2 text-xs text-primary-600">
                Expires: {new Date(challenge.expires_at).toLocaleString()}
              </p>
              <div className="mt-4 flex gap-3">
                <button
                  onClick={verify}
                  disabled={loading}
                  className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
                >
                  {loading ? 'Verifying...' : 'Verify Challenge'}
                </button>
                <button
                  onClick={reset}
                  className="rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50"
                >
                  Start Over
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Step 3: Verified */}
      {step === 'verified' && status?.attestation && (
        <div className="space-y-4">
          <div className="rounded-lg border-2 border-green-200 bg-green-50 p-5">
            <div className="flex items-center gap-2">
              <span className="text-xl text-green-600">{'\u2713'}</span>
              <h3 className="font-semibold text-green-800">Domain Attested — Layer 1</h3>
            </div>
            <div className="mt-3 space-y-1 text-sm text-green-700">
              <p>Domain: {status.attestation.domain}</p>
              <p>Issued: {new Date(status.attestation.issued_at).toLocaleString()}</p>
              <p>Expires: {new Date(status.attestation.expires_at).toLocaleString()}</p>
              <p className="truncate font-mono text-xs">Hash: {status.attestation.manifest_hash}</p>
            </div>
          </div>
          <button
            onClick={reset}
            className="rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50"
          >
            Attest Another Domain
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
      )}
    </div>
  )
}

function Check({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className={ok ? 'text-green-600' : 'text-red-600'}>{ok ? '\u2713' : '\u2717'}</span>
      <span className={ok ? 'text-green-800' : 'text-red-800'}>{label}</span>
    </div>
  )
}

import TrustFlow from '@/components/TrustFlow'
import TrustLookup from '@/components/TrustLookup'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Trust — OAP',
  description: 'Attest domain ownership and verify capability claims for OAP manifests.',
}

export default function TrustPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
      <h1 className="text-3xl font-bold text-gray-900">Trust</h1>
      <p className="mt-2 text-gray-600">
        The trust overlay is a companion protocol for OAP — like TLS is to HTTP.
        Graduated layers let agents set their own trust thresholds based on task sensitivity.
      </p>
      <p className="mt-1 text-sm text-gray-500">
        Reference implementation of the protocol described in{' '}
        <a href="/docs/trust" className="text-primary hover:underline">TRUST.md</a>.
      </p>

      {/* Attestation Flow */}
      <div className="mt-10">
        <h2 className="text-xl font-semibold text-gray-900">Domain Attestation</h2>
        <p className="mt-1 text-sm text-gray-600">
          Start the Layer 1 attestation flow: Layer 0 baseline checks run automatically,
          then you complete a DNS or HTTP challenge to prove domain ownership.
        </p>
        <div className="mt-4">
          <TrustFlow />
        </div>
      </div>

      {/* Lookup */}
      <div className="mt-12 border-t border-gray-200 pt-10">
        <h2 className="text-xl font-semibold text-gray-900">Attestation Lookup</h2>
        <p className="mt-1 text-sm text-gray-600">
          Look up existing attestations for any domain. This is what agents query at runtime
          to evaluate trust before invoking a capability.
        </p>
        <div className="mt-4">
          <TrustLookup />
        </div>
      </div>
    </div>
  )
}

interface Attestation {
  layer: number
  domain: string
  issued_at: string
  expires_at: string
  verification_method?: string
}

export default function TrustBadges({ attestations }: { attestations: Attestation[] }) {
  const layers = [0, 1, 2]
  const attestedLayers = new Set(attestations.map((a) => a.layer))

  return (
    <div className="flex items-center gap-2">
      {layers.map((layer) => {
        const active = attestedLayers.has(layer)
        return (
          <span
            key={layer}
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
              active
                ? 'bg-green-100 text-green-800'
                : 'bg-gray-100 text-gray-500'
            }`}
          >
            {active ? '\u2713' : '\u2022'} Layer {layer}
            <span className="font-normal">
              {layer === 0 && '(Baseline)'}
              {layer === 1 && '(Domain)'}
              {layer === 2 && '(Capability)'}
            </span>
          </span>
        )
      })}
    </div>
  )
}

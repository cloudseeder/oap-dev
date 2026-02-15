interface DiscoverMatch {
  domain: string
  name: string
  description: string
  invoke: { method: string; url: string }
  score: number
  reason?: string
}

interface DiscoverResultProps {
  match: DiscoverMatch | null
  candidates: DiscoverMatch[]
  task: string
}

export default function DiscoverResult({ match, candidates, task }: DiscoverResultProps) {
  if (!match && candidates.length === 0) {
    return (
      <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800">
        No manifests found for: &ldquo;{task}&rdquo;
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Best Match */}
      {match && (
        <div className="rounded-lg border-2 border-primary-200 bg-primary-50 p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-gray-900">{match.name}</h3>
                <span className="rounded bg-primary-100 px-2 py-0.5 text-xs font-medium text-primary-700">
                  Best Match
                </span>
              </div>
              <p className="mt-0.5 text-xs text-gray-500">{match.domain}</p>
              <p className="mt-2 text-sm text-gray-700">{match.description}</p>
              {match.reason && (
                <p className="mt-2 text-sm italic text-primary-700">{match.reason}</p>
              )}
            </div>
            <div className="shrink-0 text-right">
              <span className="text-xs text-gray-500">Score</span>
              <p className="font-mono text-sm font-medium text-gray-900">{match.score.toFixed(3)}</p>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs text-gray-600">
            <span className="rounded bg-gray-100 px-2 py-0.5 font-mono">{match.invoke.method}</span>
            <span className="truncate font-mono">{match.invoke.url}</span>
          </div>
        </div>
      )}

      {/* Other Candidates */}
      {candidates.length > 1 && (
        <div>
          <h3 className="mb-3 text-sm font-semibold text-gray-500">Other Candidates</h3>
          <div className="space-y-2">
            {candidates
              .filter((c) => !match || c.domain !== match.domain)
              .map((c, i) => (
                <div key={i} className="rounded-lg border border-gray-200 p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <h4 className="font-medium text-gray-900">{c.name}</h4>
                      <p className="text-xs text-gray-500">{c.domain}</p>
                      <p className="mt-1 text-sm text-gray-600">{c.description}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <span className="font-mono text-xs text-gray-500">{c.score.toFixed(3)}</span>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
                    <span className="rounded bg-gray-100 px-2 py-0.5 font-mono">{c.invoke.method}</span>
                    <span className="truncate font-mono">{c.invoke.url}</span>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}

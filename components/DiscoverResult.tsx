'use client'

import { useState } from 'react'

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

interface DiscoverResultProps {
  match: DiscoverMatch | null
  candidates: DiscoverMatch[]
  task: string
  meta?: DiscoverMeta | null
}

export default function DiscoverResult({ match, candidates, task, meta }: DiscoverResultProps) {
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

      {/* LLM Details */}
      {meta && <LLMDetails meta={meta} />}
    </div>
  )
}

function LLMDetails({ meta }: { meta: DiscoverMeta }) {
  const [open, setOpen] = useState(false)
  const [promptOpen, setPromptOpen] = useState(false)

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-gray-600 hover:text-gray-900"
      >
        <span>LLM Details</span>
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-gray-400">
            {meta.total_ms.toFixed(0)}ms total
          </span>
          <svg
            className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {open && (
        <div className="space-y-3 border-t border-gray-200 px-4 py-3">
          {/* Embed call */}
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="rounded bg-blue-100 px-1.5 py-0.5 font-medium text-blue-700">Embed</span>
              <span className="font-mono text-gray-500">{meta.embed.model}</span>
            </div>
            <div className="flex items-center gap-3 font-mono text-gray-500">
              <span>{meta.embed.prompt_tokens} tokens in</span>
              <span>{meta.embed.total_ms.toFixed(0)}ms</span>
            </div>
          </div>

          {/* Reason call */}
          {meta.reason && (
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="rounded bg-purple-100 px-1.5 py-0.5 font-medium text-purple-700">Reason</span>
                <span className="font-mono text-gray-500">{meta.reason.model}</span>
              </div>
              <div className="flex items-center gap-3 font-mono text-gray-500">
                <span>{meta.reason.prompt_tokens} in / {meta.reason.generated_tokens} out</span>
                <span>{meta.reason.total_ms.toFixed(0)}ms</span>
              </div>
            </div>
          )}

          {/* Search results count */}
          <div className="text-xs text-gray-500">
            Vector search returned {meta.search_results} candidates
          </div>

          {/* Prompts */}
          {meta.reason && (meta.reason.system_prompt || meta.reason.prompt) && (
            <div>
              <button
                onClick={() => setPromptOpen(!promptOpen)}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600"
              >
                <svg
                  className={`h-3 w-3 transition-transform ${promptOpen ? 'rotate-90' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                Prompts
              </button>

              {promptOpen && (
                <div className="mt-2 space-y-2">
                  {meta.reason.system_prompt && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-gray-500">System prompt</p>
                      <pre className="max-h-40 overflow-auto rounded bg-gray-100 p-2 font-mono text-xs text-gray-700">
                        {meta.reason.system_prompt}
                      </pre>
                    </div>
                  )}
                  {meta.reason.prompt && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-gray-500">User prompt</p>
                      <pre className="max-h-40 overflow-auto rounded bg-gray-100 p-2 font-mono text-xs text-gray-700">
                        {meta.reason.prompt}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

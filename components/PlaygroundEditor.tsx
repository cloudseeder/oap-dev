'use client'

import { useState, useCallback } from 'react'
import { validateManifest } from '@/lib/manifest-v1'
import type { ValidationResult } from '@/lib/manifest-v1'
import type { OAPManifest } from '@/lib/types-v1'
import PlaygroundResult from '@/components/PlaygroundResult'

const SAMPLE_MANIFEST = `{
  "oap": "1.0",
  "name": "Text Summarizer",
  "description": "Accepts plain text (max 10,000 words) and returns a concise summary. Preserves key facts, strips filler. Input: raw text via POST body. Output: JSON with summary field.",
  "input": { "format": "text/plain", "description": "Raw text to summarize (max 10,000 words)" },
  "output": { "format": "application/json", "description": "JSON object with a summary field" },
  "invoke": { "method": "POST", "url": "https://example.com/api/summarize" },
  "tags": ["nlp", "summarization"],
  "publisher": { "name": "Example Corp" }
}`

type Mode = 'json' | 'url'

export default function PlaygroundEditor() {
  const [mode, setMode] = useState<Mode>('json')
  const [jsonInput, setJsonInput] = useState(SAMPLE_MANIFEST)
  const [urlInput, setUrlInput] = useState('')
  const [result, setResult] = useState<ValidationResult | null>(null)
  const [manifest, setManifest] = useState<OAPManifest | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  const validateJson = useCallback(() => {
    setFetchError(null)
    let parsed: unknown
    try {
      parsed = JSON.parse(jsonInput)
    } catch (e) {
      setResult({ valid: false, errors: [`JSON parse error: ${(e as Error).message}`], warnings: [] })
      setManifest(null)
      return
    }
    const res = validateManifest(parsed)
    setResult(res)
    setManifest(res.valid ? (parsed as OAPManifest) : null)
  }, [jsonInput])

  const validateUrl = useCallback(async () => {
    if (!urlInput.trim()) return
    setLoading(true)
    setFetchError(null)
    setResult(null)
    setManifest(null)
    try {
      const resp = await fetch('/api/playground/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: urlInput.trim() }),
      })
      const data = await resp.json()
      if (!resp.ok) {
        setFetchError(data.error || 'Failed to fetch manifest')
        return
      }
      setResult(data.validation)
      if (data.validation.valid && data.manifest) {
        setManifest(data.manifest)
      }
    } catch {
      setFetchError('Network error — could not reach validation API')
    } finally {
      setLoading(false)
    }
  }, [urlInput])

  return (
    <div className="space-y-6">
      {/* Mode Toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => { setMode('json'); setResult(null); setManifest(null); setFetchError(null) }}
          className={`rounded-lg px-4 py-2 text-sm font-medium ${
            mode === 'json'
              ? 'bg-primary text-white'
              : 'border border-gray-300 text-gray-700 hover:bg-gray-50'
          }`}
        >
          Paste JSON
        </button>
        <button
          onClick={() => { setMode('url'); setResult(null); setManifest(null); setFetchError(null) }}
          className={`rounded-lg px-4 py-2 text-sm font-medium ${
            mode === 'url'
              ? 'bg-primary text-white'
              : 'border border-gray-300 text-gray-700 hover:bg-gray-50'
          }`}
        >
          Fetch from URL
        </button>
      </div>

      {/* Input */}
      {mode === 'json' ? (
        <div>
          <textarea
            value={jsonInput}
            onChange={(e) => setJsonInput(e.target.value)}
            rows={16}
            className="w-full rounded-lg border border-gray-300 bg-slate-900 p-4 font-mono text-sm leading-relaxed text-gray-100 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            placeholder="Paste your OAP v1.0 manifest JSON here..."
            spellCheck={false}
          />
          <button
            onClick={validateJson}
            className="mt-3 rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-600"
          >
            Validate
          </button>
        </div>
      ) : (
        <div>
          <div className="flex gap-3">
            <input
              type="text"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && validateUrl()}
              placeholder="https://example.com (fetches /.well-known/oap.json)"
              className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <button
              onClick={validateUrl}
              disabled={loading}
              className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
            >
              {loading ? 'Fetching...' : 'Fetch & Validate'}
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            Fetches <code className="rounded bg-gray-100 px-1 py-0.5">/.well-known/oap.json</code> from the domain and validates it.
          </p>
        </div>
      )}

      {/* Fetch Error */}
      {fetchError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {fetchError}
        </div>
      )}

      {/* Results */}
      {result && <PlaygroundResult result={result} manifest={manifest} />}
    </div>
  )
}

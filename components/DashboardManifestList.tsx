'use client'

import { useState, useEffect, useCallback } from 'react'

interface ManifestRow {
  domain: string
  name: string
  description: string
  oap_version: string
  invoke_method: string | null
  invoke_url: string | null
  health_ok: boolean | null
  last_seen: string
  first_seen: string
  tags: string[] | null
  publisher_name: string | null
}

export default function DashboardManifestList() {
  const [manifests, setManifests] = useState<ManifestRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const limit = 20

  const fetchPage = useCallback(async (p: number) => {
    setLoading(true)
    try {
      const resp = await fetch(`/api/dashboard/manifests?page=${p}&limit=${limit}`)
      const data = await resp.json()
      if (data.error) {
        setError(data.error)
      } else {
        setManifests(data.manifests || [])
        setTotal(data.total || 0)
        setError(null)
      }
    } catch {
      setError('Dashboard service unavailable')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPage(page)
  }, [page, fetchPage])

  if (error) {
    return (
      <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800">
        {error}
      </div>
    )
  }

  const totalPages = Math.ceil(total / limit)

  return (
    <div className="space-y-4">
      {loading ? (
        <div className="text-sm text-gray-500">Loading manifests...</div>
      ) : manifests.length === 0 ? (
        <div className="text-sm text-gray-500">No manifests tracked yet.</div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-4 py-2.5 text-left font-medium text-gray-500">Domain</th>
                  <th className="px-4 py-2.5 text-left font-medium text-gray-500">Name</th>
                  <th className="px-4 py-2.5 text-left font-medium text-gray-500">Method</th>
                  <th className="px-4 py-2.5 text-left font-medium text-gray-500">Health</th>
                  <th className="px-4 py-2.5 text-left font-medium text-gray-500">Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {manifests.map((m) => (
                  <tr key={m.domain} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-900">{m.domain}</td>
                    <td className="px-4 py-2.5 text-gray-700">{m.name}</td>
                    <td className="px-4 py-2.5">
                      <span className="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">
                        {m.invoke_method || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      {m.health_ok === true && (
                        <span className="inline-flex items-center gap-1 text-green-600">
                          <span className="inline-block h-2 w-2 rounded-full bg-green-500" /> OK
                        </span>
                      )}
                      {m.health_ok === false && (
                        <span className="inline-flex items-center gap-1 text-red-600">
                          <span className="inline-block h-2 w-2 rounded-full bg-red-500" /> Down
                        </span>
                      )}
                      {m.health_ok === null && (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-500">
                      {new Date(m.last_seen).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-xs text-gray-500">
                {total} manifests total
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="rounded border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  Previous
                </button>
                <span className="px-2 py-1 text-xs text-gray-500">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="rounded border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

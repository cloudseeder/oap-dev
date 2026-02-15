'use client'

import { useState, useEffect } from 'react'

interface Stats {
  date: string
  total: number
  new: number
  healthy: number
}

export default function DashboardStats() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [history, setHistory] = useState<Stats[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/dashboard/stats')
      .then((r) => r.json())
      .then((data) => {
        if (data.error) setError(data.error)
        else setStats(data)
      })
      .catch(() => setError('Dashboard service unavailable'))

    fetch('/api/dashboard/stats?history=30')
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setHistory(data)
      })
      .catch(() => {})
  }, [])

  if (error) {
    return (
      <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800">
        {error}
      </div>
    )
  }

  if (!stats) {
    return <div className="text-sm text-gray-500">Loading stats...</div>
  }

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Total Manifests" value={stats.total} />
        <StatCard label="Healthy" value={stats.healthy} accent="green" />
        <StatCard label="New Today" value={stats.new} accent="blue" />
      </div>

      {/* Inline SVG Chart */}
      {history.length > 1 && <GrowthChart data={history} />}
    </div>
  )
}

function StatCard({ label, value, accent }: { label: string; value: number; accent?: string }) {
  const colors = {
    green: 'text-green-600',
    blue: 'text-primary',
    default: 'text-gray-900',
  }
  const color = colors[accent as keyof typeof colors] || colors.default

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${color}`}>{value}</p>
    </div>
  )
}

function GrowthChart({ data }: { data: Stats[] }) {
  const maxTotal = Math.max(...data.map((d) => d.total), 1)
  const w = 600
  const h = 120
  const padX = 0
  const padY = 10

  const points = data.map((d, i) => {
    const x = padX + (i / (data.length - 1)) * (w - 2 * padX)
    const y = h - padY - ((d.total / maxTotal) * (h - 2 * padY))
    return `${x},${y}`
  })

  const areaPoints = [
    `${padX},${h - padY}`,
    ...points,
    `${w - padX},${h - padY}`,
  ]

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-gray-500">
        Growth (last {data.length} days)
      </h3>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" preserveAspectRatio="none">
        <polygon
          points={areaPoints.join(' ')}
          fill="rgba(45, 95, 138, 0.1)"
        />
        <polyline
          points={points.join(' ')}
          fill="none"
          stroke="#2D5F8A"
          strokeWidth="2"
        />
      </svg>
      <div className="mt-1 flex justify-between text-xs text-gray-400">
        <span>{data[0]?.date}</span>
        <span>{data[data.length - 1]?.date}</span>
      </div>
    </div>
  )
}

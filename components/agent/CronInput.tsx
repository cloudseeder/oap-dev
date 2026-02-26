'use client'

import { useState } from 'react'

const PRESETS = [
  { label: 'Every 5 minutes', value: '*/5 * * * *' },
  { label: 'Every 15 minutes', value: '*/15 * * * *' },
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Every day at midnight', value: '0 0 * * *' },
  { label: 'Every Monday 9am', value: '0 9 * * 1' },
  { label: 'Every weekday 9am', value: '0 9 * * 1-5' },
]

function describeCron(expr: string): string {
  if (!expr.trim()) return ''
  const preset = PRESETS.find((p) => p.value === expr.trim())
  if (preset) return preset.label
  return expr.trim()
}

interface CronInputProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}

export default function CronInput({ value, onChange, disabled }: CronInputProps) {
  const [showPresets, setShowPresets] = useState(false)

  return (
    <div className="space-y-1">
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="e.g. 0 9 * * 1 (optional)"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm font-mono focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:bg-gray-50 disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => setShowPresets(!showPresets)}
          disabled={disabled}
          className="rounded-md border border-gray-300 px-3 py-2 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
        >
          Presets
        </button>
      </div>

      {showPresets && (
        <div className="rounded-md border border-gray-200 bg-white py-1 shadow-sm">
          {PRESETS.map((preset) => (
            <button
              key={preset.value}
              type="button"
              onClick={() => {
                onChange(preset.value)
                setShowPresets(false)
              }}
              className="flex w-full items-center justify-between px-3 py-1.5 text-sm hover:bg-gray-50"
            >
              <span className="text-gray-700">{preset.label}</span>
              <span className="font-mono text-xs text-gray-400">{preset.value}</span>
            </button>
          ))}
        </div>
      )}

      {value && (
        <p className="text-xs text-gray-500">{describeCron(value)}</p>
      )}
    </div>
  )
}

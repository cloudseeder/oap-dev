import { useState } from 'react'
import type { TaskRun } from '@/lib/types'
import ToolCallCard from './ToolCallCard'

interface TaskRunDetailProps {
  run: TaskRun
}

export default function TaskRunDetail({ run }: TaskRunDetailProps) {
  const [expanded, setExpanded] = useState(false)

  const statusColors = {
    success: 'text-green-700 bg-green-50 border-green-200',
    error: 'text-red-700 bg-red-50 border-red-200',
    running: 'text-blue-700 bg-blue-50 border-blue-200',
  }

  const statusColor = statusColors[run.status] || statusColors.running

  return (
    <div className="rounded-lg border border-gray-200">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-gray-50"
      >
        <div className="flex items-center gap-3">
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium border ${statusColor}`}>
            {run.status}
          </span>
          <span className="text-sm text-gray-700">
            {new Date(run.started_at).toLocaleString()}
          </span>
          {run.duration_ms !== undefined && (
            <span className="text-xs text-gray-400">{(run.duration_ms / 1000).toFixed(1)}s</span>
          )}
        </div>
        <svg
          className={`h-4 w-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-gray-200 px-4 py-3 space-y-3">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Prompt</div>
            <p className="text-sm text-gray-700 whitespace-pre-wrap">{run.prompt}</p>
          </div>

          {run.response && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Response</div>
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{run.response}</p>
            </div>
          )}

          {run.error && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-red-400 mb-1">Error</div>
              <p className="text-sm text-red-700 font-mono">{run.error}</p>
            </div>
          )}

          {run.tool_calls && run.tool_calls.length > 0 && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Tool Calls</div>
              <div className="space-y-1">
                {run.tool_calls.map((tc, i) => (
                  <ToolCallCard key={i} toolCall={tc} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

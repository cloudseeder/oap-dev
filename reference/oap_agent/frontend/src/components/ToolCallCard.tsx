import { useState } from 'react'
import type { ToolCall } from '@/lib/types'

interface ToolCallCardProps {
  toolCall: ToolCall
}

export default function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(true)
  const hasError = toolCall.result?.startsWith('Error')

  return (
    <div
      className={`rounded-md border text-xs font-mono ${
        hasError ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50'
      }`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <div className="flex items-center gap-2">
          <span className={`font-semibold ${hasError ? 'text-red-700' : 'text-green-700'}`}>
            {toolCall.tool}
          </span>
          {toolCall.duration_ms !== undefined && (
            <span className="text-gray-400">{toolCall.duration_ms}ms</span>
          )}
        </div>
        <svg
          className={`h-3 w-3 text-gray-500 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-gray-200 px-3 py-2 space-y-2">
          <div>
            <div className="text-gray-500 mb-1">args</div>
            <pre className="overflow-x-auto whitespace-pre-wrap break-all text-gray-800">
              {JSON.stringify(toolCall.args, null, 2)}
            </pre>
          </div>
          {toolCall.result !== undefined && (
            <div>
              <div className={`mb-1 ${hasError ? 'text-red-500' : 'text-gray-500'}`}>
                {hasError ? 'error' : 'result'}
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap break-all text-gray-800">
                {toolCall.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

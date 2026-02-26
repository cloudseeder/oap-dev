'use client'

import { useRef, useState } from 'react'

const MODELS = ['qwen3:8b', 'qwen3:4b', 'llama3.2:3b', 'mistral:7b']

interface ChatInputProps {
  onSend: (message: string, model: string) => void
  disabled?: boolean
  defaultModel?: string
}

export default function ChatInput({ onSend, disabled, defaultModel = 'qwen3:8b' }: ChatInputProps) {
  const [value, setValue] = useState('')
  const [model, setModel] = useState(defaultModel)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleSend() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed, model)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setValue(e.target.value)
    const ta = textareaRef.current
    if (ta) {
      ta.style.height = 'auto'
      ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`
    }
  }

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2 rounded-xl border border-gray-300 bg-white px-3 py-2 focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Send a message..."
            rows={1}
            disabled={disabled}
            className="flex-1 resize-none bg-transparent text-sm text-gray-900 placeholder-gray-400 focus:outline-none disabled:opacity-50"
            style={{ minHeight: '24px', maxHeight: '200px' }}
          />
          <div className="flex items-center gap-2 shrink-0">
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={disabled}
              className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-600 focus:outline-none focus:border-primary disabled:opacity-50"
            >
              {MODELS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <button
              onClick={handleSend}
              disabled={disabled || !value.trim()}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-white transition-colors hover:bg-primary-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>
        <p className="mt-1.5 text-center text-xs text-gray-400">
          Enter to send, Shift+Enter for newline
        </p>
      </div>
    </div>
  )
}

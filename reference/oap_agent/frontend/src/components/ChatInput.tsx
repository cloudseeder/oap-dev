import { useRef, useState, useEffect, type MutableRefObject } from 'react'

const MODELS = ['qwen3:14b', 'qwen3:8b', 'qwen3:4b', 'llama3.2:3b', 'mistral:7b']

interface ChatInputProps {
  onSend: (message: string, model: string) => void
  disabled?: boolean
  defaultModel?: string
  voiceEnabled?: boolean
  autoSend?: boolean
  recording?: boolean
  listening?: boolean
  transcribing?: boolean
  micSupported?: boolean
  wakeWord?: string
  onMicClick?: () => void
  onModelChange?: (model: string) => void
  onTranscriptionRef?: MutableRefObject<((text: string) => void) | null>
}

export default function ChatInput({
  onSend,
  disabled,
  defaultModel = 'qwen3:14b',
  voiceEnabled = false,
  autoSend = false,
  recording = false,
  listening = false,
  transcribing = false,
  micSupported = false,
  wakeWord = '',
  onMicClick,
  onModelChange,
  onTranscriptionRef,
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const [model, setModel] = useState(defaultModel)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Notify parent of model changes
  useEffect(() => {
    onModelChange?.(model)
  }, [model, onModelChange])

  // Register transcription handler so parent can push text into the input
  useEffect(() => {
    if (onTranscriptionRef) {
      onTranscriptionRef.current = (text: string) => {
        setValue((prev) => (prev ? prev + ' ' + text : text))
        setTimeout(() => {
          const ta = textareaRef.current
          if (ta) {
            ta.style.height = 'auto'
            ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`
            ta.focus()
          }
        }, 0)
      }
    }
    return () => {
      if (onTranscriptionRef) onTranscriptionRef.current = null
    }
  }, [onTranscriptionRef])

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

  const showMic = voiceEnabled && micSupported

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2 rounded-xl border border-gray-300 bg-white px-3 py-2 focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={transcribing ? 'Transcribing...' : recording ? 'Listening...' : listening ? `Say '${wakeWord}' to start...` : 'Send a message...'}
            rows={1}
            disabled={disabled || transcribing}
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
            {showMic && (
              <button
                onClick={onMicClick}
                disabled={disabled || transcribing}
                title={recording ? 'Stop recording' : listening ? 'Stop listening' : 'Voice input'}
                className={`relative flex h-8 w-8 items-center justify-center rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                  recording
                    ? 'bg-red-500 text-white animate-pulse'
                    : listening
                      ? 'bg-gray-200 text-gray-600'
                      : 'bg-gray-100 text-gray-500 hover:bg-gray-200 hover:text-gray-700'
                }`}
              >
                {transcribing ? (
                  <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
                  </svg>
                )}
                {listening && !transcribing && (
                  <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-green-500" />
                )}
              </button>
            )}
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
          Enter to send, Shift+Enter for newline{showMic && (recording ? ' — Recording...' : listening ? ' — Listening...' : '')}
        </p>
      </div>
    </div>
  )
}

import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import type { Message, ToolCall } from '@/lib/types'
import { parseSSE } from '@/lib/types'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'

export default function ChatView() {
  const navigate = useNavigate()
  const { id: initialConvId } = useParams<{ id: string }>()
  const [searchParams] = useSearchParams()
  const [conversationId, setConversationId] = useState<string | undefined>(initialConvId)
  const primerSent = useRef(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (initialConvId) {
      setConversationId(initialConvId)
      fetchConversation(initialConvId)
    } else {
      setMessages([])
      setConversationId(undefined)
    }
  }, [initialConvId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-send primer message when navigated with ?primer=true
  useEffect(() => {
    if (searchParams.get('primer') === 'true' && !primerSent.current && !initialConvId) {
      primerSent.current = true
      handleSend(
        "Hey! I'd like you to get to know me. Ask me a few questions about myself — things like where I live, what I do for work, my hobbies and interests.",
        'qwen3:8b',
      )
    }
  }, [searchParams, initialConvId])

  async function fetchConversation(id: string) {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/v1/agent/conversations/${id}`)
      if (!res.ok) {
        setError('Failed to load conversation')
        return
      }
      const data = await res.json()
      setMessages(data.messages || [])
    } catch {
      setError('Failed to load conversation')
    } finally {
      setLoading(false)
    }
  }

  const handleSend = useCallback(async (message: string, model: string) => {
    if (streaming) return

    setError(null)
    setStreaming(true)

    let convId = conversationId

    // Create conversation if needed
    if (!convId) {
      try {
        const res = await fetch('/v1/agent/conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: message.slice(0, 60), model }),
        })
        if (!res.ok) {
          setError('Failed to create conversation')
          setStreaming(false)
          return
        }
        const data = await res.json()
        convId = data.conversation?.id || data.id
        setConversationId(convId)
        navigate(`/chat/${convId}`, { replace: true })
      } catch {
        setError('Failed to create conversation')
        setStreaming(false)
        return
      }
    }

    // Optimistically add user message
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      conversation_id: convId!,
      role: 'user',
      content: message,
      created_at: new Date().toISOString(),
      seq: messages.length,
    }
    setMessages((prev) => [...prev, tempUserMsg])

    // Stream the chat
    abortRef.current = new AbortController()
    let assistantMsgId: string | null = null
    let currentContent = ''
    let currentToolCalls: ToolCall[] = []
    let currentMetadata: Record<string, any> = {}

    try {
      const res = await fetch('/v1/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: convId, message, model }),
        signal: abortRef.current.signal,
      })

      if (!res.ok || !res.body) {
        setError('Service unavailable')
        setStreaming(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        // Re-assemble SSE events from lines
        let chunk = ''
        for (const line of lines) {
          chunk += line + '\n'
          if (line === '') {
            const events = parseSSE(chunk)
            for (const ev of events) {
              if (ev.event === 'tool_call') {
                currentToolCalls = [...currentToolCalls, ev.data]
              } else if (ev.event === 'assistant_message') {
                const msg = ev.data.message || ev.data
                currentContent = msg.content || ''
                currentMetadata = msg.metadata || {}
                assistantMsgId = msg.id || `assistant-${Date.now()}`
              } else if (ev.event === 'message_saved') {
                // User message confirmed saved — update temp id if provided
              } else if (ev.event === 'done') {
                // Stream complete
              }
            }
            chunk = ''

            // Update assistant message in UI
            if (currentContent || currentToolCalls.length > 0) {
              const assistantMsg: Message = {
                id: assistantMsgId || `assistant-${Date.now()}`,
                conversation_id: convId!,
                role: 'assistant',
                content: currentContent,
                tool_calls: currentToolCalls.length > 0 ? currentToolCalls : undefined,
                metadata: currentMetadata,
                created_at: new Date().toISOString(),
                seq: messages.length + 1,
              }
              setMessages((prev) => {
                const withoutAssistant = prev.filter((m) => m.id !== assistantMsg.id)
                return [...withoutAssistant, assistantMsg]
              })
            }
          }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setError('Connection error')
      }
    } finally {
      setStreaming(false)
    }
  }, [conversationId, messages.length, navigate, streaming])

  return (
    <div className="flex h-full flex-col">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {loading && (
            <div className="text-center text-sm text-gray-400">Loading conversation...</div>
          )}

          {!loading && messages.length === 0 && (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="mb-4 rounded-full bg-primary-50 p-4">
                <svg className="h-8 w-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-gray-700">Start a new conversation</h2>
              <p className="mt-1 text-sm text-gray-400">Ask anything or describe a task to get started.</p>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}

          {streaming && (
            <div className="flex justify-start">
              <div className="rounded-2xl bg-gray-100 px-4 py-2.5 text-sm text-gray-500 rounded-bl-sm">
                <span className="inline-flex gap-1">
                  <span className="animate-bounce" style={{ animationDelay: '0ms' }}>.</span>
                  <span className="animate-bounce" style={{ animationDelay: '150ms' }}>.</span>
                  <span className="animate-bounce" style={{ animationDelay: '300ms' }}>.</span>
                </span>
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input area */}
      <ChatInput
        onSend={handleSend}
        disabled={streaming || loading}
        defaultModel="qwen3:8b"
      />
    </div>
  )
}

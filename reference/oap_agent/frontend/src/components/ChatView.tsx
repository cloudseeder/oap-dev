import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import type { Message, ToolCall, AgentSettings } from '@/lib/types'
import { parseSSE } from '@/lib/types'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'
import { useTTS, useAnySpeaking } from '@/hooks/useTTS'
import { useVoiceRecorder } from '@/hooks/useVoiceRecorder'
import { useAvatarState } from '@/hooks/useAvatarState'

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

  // Voice settings
  const [settings, setSettings] = useState<AgentSettings | null>(null)

  useEffect(() => {
    fetch('/v1/agent/settings')
      .then((r) => r.ok ? r.json() : null)
      .then((s) => { if (s) setSettings(s) })
      .catch(() => {})
  }, [])

  const voiceEnabled = settings?.voice_input_enabled === 'true'
  const autoSend = settings?.voice_auto_send === 'true'
  const autoSpeak = settings?.voice_auto_speak === 'true'
  const personaName = settings?.persona_name?.toLowerCase() || ''
  const ttsVoice = (personaName && settings?.[`persona_voice_${personaName}`]) || settings?.voice_tts_voice || undefined
  const autoSpeakTTS = useTTS(ttsVoice)
  // Global TTS detection — catches per-message speaker clicks too
  const anySpeaking = useAnySpeaking()
  // Backend TTS availability
  const [ttsAvailable, setTtsAvailable] = useState(false)

  useEffect(() => {
    fetch('/v1/agent/voice/status')
      .then((r) => r.ok ? r.json() : null)
      .then((data) => { if (data) setTtsAvailable(!!data.tts_enabled) })
      .catch(() => {})
  }, [])

  // Push avatar-relevant state up to shared context for sidebar
  const { update: updateAvatar } = useAvatarState()

  // Voice recorder — lifted from ChatInput so ChatView owns recording state
  const modelRef = useRef('qwen3:14b')
  const pendingTranscriptionRef = useRef<((text: string) => void) | null>(null)
  const handleTranscription = useCallback((text: string) => {
    if (autoSend) {
      handleSendRef.current(text, modelRef.current)
    } else {
      pendingTranscriptionRef.current?.(text)
    }
  }, [autoSend])
  const { recording, transcribing, start: recorderStart, stop: recorderStop, supported: micSupported, audioLevelRef } = useVoiceRecorder(handleTranscription)

  // Sync avatar state to shared context so sidebar can render the avatar
  useEffect(() => {
    updateAvatar({ recording, streaming, persona: settings?.persona_name || '', audioLevelRef })
  }, [recording, streaming, settings?.persona_name, audioLevelRef, updateAvatar])

  // Stable ref to handleSend so transcription callback doesn't go stale
  const handleSendRef = useRef<(message: string, model: string) => void>(() => {})

  const waitingForTTS = useRef(false)

  // Refs for values used inside the async SSE loop (avoids stale closures)
  const autoSpeakRef = useRef(autoSpeak)
  autoSpeakRef.current = autoSpeak
  const autoSendRef = useRef(autoSend)
  autoSendRef.current = autoSend
  const speakRef = useRef(autoSpeakTTS.speak)
  speakRef.current = autoSpeakTTS.speak
  const micSupportedRef = useRef(micSupported)
  micSupportedRef.current = micSupported
  const voiceEnabledRef = useRef(voiceEnabled)
  voiceEnabledRef.current = voiceEnabled
  const recorderStartRef = useRef(recorderStart)
  recorderStartRef.current = recorderStart

  // When TTS finishes speaking and we were waiting, auto-record
  useEffect(() => {
    if (!autoSpeakTTS.speaking && waitingForTTS.current) {
      waitingForTTS.current = false
      const timer = setTimeout(() => {
        if (!recording && !transcribing && micSupported && voiceEnabled) {
          recorderStart()
        }
      }, 600)
      return () => clearTimeout(timer)
    }
  }, [autoSpeakTTS.speaking, recording, transcribing, micSupported, voiceEnabled, recorderStart])

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
        "Let's do a quick get-to-know-me. Ask me exactly 5 questions, one at a time — wait for my answer before asking the next. Ask about: (1) my name, (2) where I live, (3) what I do for work, (4) my hobbies and interests, (5) any preferences you should remember. After all 5, briefly summarize what you learned and end the conversation.",
        'qwen3:14b',
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
                // User message confirmed saved
              } else if (ev.event === 'done') {
                // Stream complete — use refs to avoid stale closure values
                if (autoSpeakRef.current && currentContent) {
                  speakRef.current(currentContent)
                  // If STT is also on, wait for TTS to finish then auto-record
                  if (autoSendRef.current) {
                    waitingForTTS.current = true
                  }
                } else if (autoSendRef.current) {
                  // No TTS — trigger auto-record after a short delay
                  setTimeout(() => {
                    if (micSupportedRef.current && voiceEnabledRef.current) recorderStartRef.current()
                  }, 500)
                }
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

  // Keep handleSendRef current
  useEffect(() => {
    handleSendRef.current = handleSend
  }, [handleSend])

  const handleMicClick = useCallback(() => {
    if (recording) {
      recorderStop()
    } else {
      recorderStart()
    }
  }, [recording, recorderStart, recorderStop])

  return (
    <div className="flex h-full flex-col">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {loading && (
            <div className="text-center text-sm text-gray-400">Loading conversation...</div>
          )}

          {!loading && messages.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <h2 className="text-lg font-semibold text-gray-700">Start a new conversation</h2>
              <p className="mt-1 text-sm text-gray-400">Ask anything or describe a task to get started.</p>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} ttsEnabled={voiceEnabled} ttsAvailable={ttsAvailable} ttsVoice={ttsVoice} />
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
        defaultModel="qwen3:14b"
        voiceEnabled={voiceEnabled}
        autoSend={autoSend}
        recording={recording}
        transcribing={transcribing}
        micSupported={micSupported}
        onMicClick={handleMicClick}
        onModelChange={(m) => { modelRef.current = m }}
        onTranscriptionRef={pendingTranscriptionRef}
      />
    </div>
  )
}

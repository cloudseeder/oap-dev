import type { Message } from '@/lib/types'
import Markdown from './Markdown'
import ToolCallCard from './ToolCallCard'
import ExperienceBadge from './ExperienceBadge'
import { useTTS } from '@/hooks/useTTS'

interface ChatMessageProps {
  message: Message
  ttsAvailable?: boolean
  ttsVoice?: string
}

export default function ChatMessage({ message, ttsAvailable = false, ttsVoice }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const experienceCache = message.metadata?.experience_cache
  const { speaking, speak, stop } = useTTS(ttsVoice)

  const showSpeaker = !isUser && ttsAvailable && message.content

  function handleSpeak() {
    if (speaking) {
      stop()
    } else {
      speak(message.content)
    }
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[80%] space-y-2 ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? 'bg-primary text-white rounded-br-sm'
              : 'bg-gray-100 text-gray-900 rounded-bl-sm'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : (
            <Markdown>{message.content}</Markdown>
          )}
        </div>

        <div className="flex items-center gap-2">
          {showSpeaker && (
            <button
              onClick={handleSpeak}
              title={speaking ? 'Stop speaking' : 'Speak message'}
              className={`flex h-6 w-6 items-center justify-center rounded-md transition-colors ${
                speaking
                  ? 'bg-primary-50 text-primary'
                  : 'text-gray-300 hover:text-gray-500 hover:bg-gray-100'
              }`}
            >
              {speaking ? (
                /* Stop icon */
                <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
                  <rect x="6" y="6" width="12" height="12" rx="1" />
                </svg>
              ) : (
                /* Speaker icon */
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                </svg>
              )}
            </button>
          )}

          {experienceCache && (
            <ExperienceBadge status={experienceCache} />
          )}
        </div>

        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="w-full space-y-1">
            {message.tool_calls.map((tc, i) => (
              <ToolCallCard key={i} toolCall={tc} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

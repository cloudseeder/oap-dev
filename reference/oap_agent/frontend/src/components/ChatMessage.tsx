import type { Message } from '@/lib/types'
import Markdown from './Markdown'
import ToolCallCard from './ToolCallCard'
import ExperienceBadge from './ExperienceBadge'

interface ChatMessageProps {
  message: Message
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const experienceCache = message.metadata?.experience_cache

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

        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="w-full space-y-1">
            {message.tool_calls.map((tc, i) => (
              <ToolCallCard key={i} toolCall={tc} />
            ))}
          </div>
        )}

        {experienceCache && (
          <div>
            <ExperienceBadge status={experienceCache} />
          </div>
        )}
      </div>
    </div>
  )
}

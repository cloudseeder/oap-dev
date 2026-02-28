import { Link, useLocation, useNavigate } from 'react-router'
import { useEffect, useState } from 'react'
import type { Conversation } from '@/lib/types'

export default function AgentSidebar() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [conversations, setConversations] = useState<Conversation[]>([])

  useEffect(() => {
    fetch('/v1/agent/conversations')
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data.conversations)) {
          setConversations(data.conversations)
        }
      })
      .catch(() => {})
  }, [pathname])

  async function handleNewChat() {
    navigate('/chat')
  }

  return (
    <aside className="flex h-full w-64 flex-col bg-gray-900 text-white">
      <div className="flex h-16 items-center px-4 border-b border-gray-700">
        <Link to="/" className="text-lg font-bold text-white">
          Manifest
        </Link>
      </div>

      <div className="p-3">
        <button
          onClick={handleNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white hover:bg-primary-600 transition-colors"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Chat
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-4">
        <div className="mb-1 px-2 py-1 text-xs font-semibold uppercase tracking-wider text-gray-400">
          Conversations
        </div>
        {conversations.length === 0 && (
          <p className="px-2 py-1 text-xs text-gray-500">No conversations yet</p>
        )}
        {conversations.map((conv) => {
          const isActive = pathname === `/chat/${conv.id}`
          return (
            <Link
              key={conv.id}
              to={`/chat/${conv.id}`}
              className={`block truncate rounded-md px-2 py-1.5 text-sm transition-colors ${
                isActive
                  ? 'bg-primary text-white'
                  : 'text-gray-300 hover:bg-gray-700 hover:text-white'
              }`}
            >
              {conv.title || 'Untitled'}
            </Link>
          )
        })}
      </nav>

      <div className="border-t border-gray-700 p-2">
        <Link
          to="/tasks"
          className={`flex items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors ${
            pathname.startsWith('/tasks')
              ? 'bg-primary text-white'
              : 'text-gray-300 hover:bg-gray-700 hover:text-white'
          }`}
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          Tasks
        </Link>
        <Link
          to="/settings"
          className={`flex items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors ${
            pathname === '/settings'
              ? 'bg-primary text-white'
              : 'text-gray-300 hover:bg-gray-700 hover:text-white'
          }`}
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Settings
        </Link>
      </div>
    </aside>
  )
}

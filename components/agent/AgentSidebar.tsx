'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import type { Conversation } from '@/lib/agent'

export default function AgentSidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const [conversations, setConversations] = useState<Conversation[]>([])

  useEffect(() => {
    fetch('/api/agent/conversations')
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data.conversations)) {
          setConversations(data.conversations)
        }
      })
      .catch(() => {})
  }, [pathname])

  async function handleNewChat() {
    router.push('/agent/chat')
  }

  return (
    <aside className="flex h-full w-64 flex-col bg-gray-900 text-white">
      <div className="flex h-16 items-center px-4 border-b border-gray-700">
        <Link href="/agent" className="text-lg font-bold text-white">
          OAP Agent
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
          const isActive = pathname === `/agent/chat/${conv.id}`
          return (
            <Link
              key={conv.id}
              href={`/agent/chat/${conv.id}`}
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
          href="/agent/tasks"
          className={`flex items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors ${
            pathname.startsWith('/agent/tasks')
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
          href="/"
          className="flex items-center gap-2 rounded-md px-2 py-2 text-sm text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
          </svg>
          Back to OAP
        </Link>
      </div>
    </aside>
  )
}

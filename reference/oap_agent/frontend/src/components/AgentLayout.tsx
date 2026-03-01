import { useCallback, useRef, useState } from 'react'
import { Outlet } from 'react-router'
import AgentSidebar from './AgentSidebar'
import AgentEventProvider from './AgentEventProvider'
import { AvatarStateContext, type AvatarState } from '@/hooks/useAvatarState'

export default function AgentLayout() {
  const [avatarState, setAvatarState] = useState<AvatarState>({
    recording: false,
    streaming: false,
    persona: '',
  })
  const stateRef = useRef(avatarState)
  stateRef.current = avatarState

  const update = useCallback((patch: Partial<AvatarState>) => {
    setAvatarState((prev) => ({ ...prev, ...patch }))
  }, [])

  return (
    <AgentEventProvider>
      <AvatarStateContext.Provider value={{ state: avatarState, update }}>
        <div className="flex h-screen overflow-hidden bg-white">
          <AgentSidebar />
          <main className="flex flex-1 flex-col overflow-hidden">
            <Outlet />
          </main>
        </div>
      </AvatarStateContext.Provider>
    </AgentEventProvider>
  )
}

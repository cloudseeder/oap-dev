import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet } from 'react-router'
import AgentSidebar from './AgentSidebar'
import AgentEventProvider from './AgentEventProvider'
import { AvatarStateContext, type AvatarState } from '@/hooks/useAvatarState'
import { useAnySpeaking } from '@/hooks/useTTS'

export default function AgentLayout() {
  const [avatarState, setAvatarState] = useState<AvatarState>({
    recording: false,
    streaming: false,
    speaking: false,
    persona: '',
  })
  const stateRef = useRef(avatarState)
  stateRef.current = avatarState
  const anySpeaking = useAnySpeaking()

  // Keep speaking in avatar state in sync with TTS
  useEffect(() => {
    setAvatarState((prev) => prev.speaking === anySpeaking ? prev : { ...prev, speaking: anySpeaking })
  }, [anySpeaking])

  const update = useCallback((patch: Partial<AvatarState>) => {
    setAvatarState((prev) => ({ ...prev, ...patch }))
  }, [])

  // Persistent broadcast channel for external display windows
  const channelRef = useRef<BroadcastChannel | null>(null)
  useEffect(() => {
    channelRef.current = new BroadcastChannel('oap-avatar')
    return () => { channelRef.current?.close(); channelRef.current = null }
  }, [])

  // Post state changes to the channel
  useEffect(() => {
    channelRef.current?.postMessage({
      recording: avatarState.recording,
      streaming: avatarState.streaming,
      speaking: avatarState.speaking,
      persona: avatarState.persona,
    })
  }, [avatarState.recording, avatarState.streaming, avatarState.speaking, avatarState.persona])

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

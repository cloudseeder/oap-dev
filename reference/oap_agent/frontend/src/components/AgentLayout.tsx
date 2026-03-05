import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet } from 'react-router'
import AgentSidebar from './AgentSidebar'
import AgentEventProvider from './AgentEventProvider'
import { AvatarStateContext, type AvatarState } from '@/hooks/useAvatarState'
import { subscribeSpeaking } from '@/hooks/useTTS'

export default function AgentLayout() {
  const [avatarState, setAvatarState] = useState<AvatarState>({
    recording: false,
    streaming: false,
    attentive: false,
    persona: '',
  })
  const stateRef = useRef(avatarState)
  stateRef.current = avatarState

  const update = useCallback((patch: Partial<AvatarState>) => {
    setAvatarState((prev) => ({ ...prev, ...patch }))
  }, [])

  // Broadcast avatar state to external display windows via BroadcastChannel.
  // Uses a raw TTS subscription instead of useAnySpeaking() so that speaking
  // changes never trigger React re-renders in this component or its children.
  const speakingRef = useRef(false)
  const channelRef = useRef<BroadcastChannel | null>(null)

  const broadcast = useCallback(() => {
    const s = stateRef.current
    channelRef.current?.postMessage({
      recording: s.recording,
      streaming: s.streaming,
      speaking: speakingRef.current,
      persona: s.persona,
    })
  }, [])

  useEffect(() => {
    channelRef.current = new BroadcastChannel('oap-avatar')
    const unsub = subscribeSpeaking((v) => {
      speakingRef.current = v
      broadcast()
    })
    return () => { unsub(); channelRef.current?.close(); channelRef.current = null }
  }, [broadcast])

  // Re-broadcast when avatar state changes (recording/streaming/persona)
  useEffect(() => {
    broadcast()
  }, [avatarState.recording, avatarState.streaming, avatarState.persona, broadcast])

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

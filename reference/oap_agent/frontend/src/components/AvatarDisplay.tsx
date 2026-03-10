import { useEffect, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router'
import PersonaAvatar from './PersonaAvatar'

interface DisplayState {
  recording: boolean
  streaming: boolean
  speaking: boolean
  persona: string
  hasNotifications: boolean
}

export default function AvatarDisplay() {
  const [params] = useSearchParams()
  const mirror = params.get('mirror') === 'true'
  const personaOverride = params.get('persona')

  const [state, setState] = useState<DisplayState>({
    recording: false,
    streaming: false,
    speaking: false,
    persona: '',
    hasNotifications: false,
  })
  const [size, setSize] = useState(() => Math.min(window.innerWidth, window.innerHeight))

  // Fetch default persona from settings
  useEffect(() => {
    if (personaOverride) {
      setState((prev) => ({ ...prev, persona: personaOverride }))
      return
    }
    fetch('/v1/agent/settings')
      .then((r) => r.json())
      .then((data) => {
        if (data?.persona_name) {
          setState((prev) => ({ ...prev, persona: data.persona_name }))
        }
      })
      .catch(() => {})
  }, [personaOverride])

  // Listen for state broadcasts from the main app
  useEffect(() => {
    const ch = new BroadcastChannel('oap-avatar')
    ch.onmessage = (e: MessageEvent) => {
      const d = e.data as Partial<DisplayState>
      setState((prev) => ({
        recording: d.recording ?? prev.recording,
        streaming: d.streaming ?? prev.streaming,
        speaking: d.speaking ?? prev.speaking,
        persona: personaOverride ?? d.persona ?? prev.persona,
        hasNotifications: d.hasNotifications ?? prev.hasNotifications,
      }))
    }
    return () => ch.close()
  }, [personaOverride])

  // Own SSE + fetch for notification count (works standalone without main app)
  useEffect(() => {
    // Initial fetch
    fetch('/v1/agent/notifications/count')
      .then((r) => r.json())
      .then((data) => setState((prev) => ({ ...prev, hasNotifications: (data.count ?? 0) > 0 })))
      .catch(() => {})

    // SSE listener for real-time updates
    const es = new EventSource('/v1/agent/events')
    es.addEventListener('notification_new', (e) => {
      try {
        const data = JSON.parse(e.data)
        setState((prev) => ({ ...prev, hasNotifications: (data.count ?? 0) > 0 }))
      } catch {}
    })
    es.onerror = () => {
      es.close()
      // Reconnect after delay
      setTimeout(() => {
        fetch('/v1/agent/notifications/count')
          .then((r) => r.json())
          .then((data) => setState((prev) => ({ ...prev, hasNotifications: (data.count ?? 0) > 0 })))
          .catch(() => {})
      }, 5000)
    }
    return () => es.close()
  }, [])

  // Track viewport size
  const handleResize = useCallback(() => {
    setSize(Math.min(window.innerWidth, window.innerHeight))
  }, [])

  useEffect(() => {
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [handleResize])

  // Hide cursor after inactivity
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    const hide = () => { document.body.style.cursor = 'none' }
    const show = () => {
      document.body.style.cursor = ''
      clearTimeout(timer)
      timer = setTimeout(hide, 2000)
    }
    show()
    window.addEventListener('mousemove', show)
    return () => {
      window.removeEventListener('mousemove', show)
      clearTimeout(timer)
      document.body.style.cursor = ''
    }
  }, [])

  return (
    <div
      className="flex h-screen w-screen items-center justify-center bg-black"
      style={mirror ? { transform: 'scaleX(-1)' } : undefined}
    >
      <PersonaAvatar
        persona={state.persona}
        speaking={state.speaking}
        recording={state.recording}
        streaming={state.streaming}
        hasNotifications={state.hasNotifications}
        size={size}
      />
    </div>
  )
}

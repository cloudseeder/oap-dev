import { useEffect, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router'
import PersonaAvatar from './PersonaAvatar'

interface DisplayState {
  recording: boolean
  streaming: boolean
  speaking: boolean
  persona: string
  hasNotifications: boolean
  notificationCount: number
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
    notificationCount: 0,
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
        // Notification state owned by our own SSE + fetch — don't accept from broadcast
        hasNotifications: prev.hasNotifications,
        notificationCount: prev.notificationCount,
      }))
    }
    return () => ch.close()
  }, [personaOverride])

  // Own SSE + fetch for notification count (works standalone without main app)
  useEffect(() => {
    function applyCount(count: number) {
      setState((prev) => ({ ...prev, hasNotifications: count > 0, notificationCount: count }))
    }

    // Initial fetch
    fetch('/v1/agent/notifications/count')
      .then((r) => r.json())
      .then((data) => applyCount(data.count ?? 0))
      .catch(() => {})

    // SSE listener for real-time updates
    const es = new EventSource('/v1/agent/events')
    es.addEventListener('notification_new', (e) => {
      try {
        const data = JSON.parse(e.data)
        applyCount(data.count ?? 0)
      } catch {}
    })
    es.onerror = () => {
      es.close()
      setTimeout(() => {
        fetch('/v1/agent/notifications/count')
          .then((r) => r.json())
          .then((data) => applyCount(data.count ?? 0))
          .catch(() => {})
      }, 5000)
    }

    // Poll every 30s to catch dismissals (greeting clears notifications without SSE)
    const poll = setInterval(() => {
      fetch('/v1/agent/notifications/count')
        .then((r) => r.json())
        .then((data) => applyCount(data.count ?? 0))
        .catch(() => {})
    }, 30_000)

    return () => { es.close(); clearInterval(poll) }
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

  const badgeSize = Math.max(24, size * 0.1)
  const badgeFontSize = Math.max(12, badgeSize * 0.55)

  return (
    <div
      className="relative flex h-screen w-screen items-center justify-center bg-black"
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
      {state.notificationCount > 0 && (
        <span
          className="absolute flex items-center justify-center rounded-full bg-red-500 font-bold text-white shadow-lg"
          style={{
            top: '8%',
            right: '18%',
            width: badgeSize,
            height: badgeSize,
            fontSize: badgeFontSize,
          }}
        >
          {state.notificationCount > 99 ? '99+' : state.notificationCount}
        </span>
      )}
    </div>
  )
}

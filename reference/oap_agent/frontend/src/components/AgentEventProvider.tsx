import { createContext, useContext, useEffect, useRef, useState } from 'react'

interface AgentEvent {
  type: string
  data: any
}

interface TaskNotification {
  id: string
  task_name: string
  status: 'success' | 'error'
  message: string
}

interface AgentEventContextValue {
  lastEvent: AgentEvent | null
  taskNotifications: TaskNotification[]
  dismissNotification: (id: string) => void
  notificationCount: number
  refreshNotificationCount: () => void
}

const AgentEventContext = createContext<AgentEventContextValue>({
  lastEvent: null,
  taskNotifications: [],
  dismissNotification: () => {},
  notificationCount: 0,
  refreshNotificationCount: () => {},
})

export function useAgentEvents() {
  return useContext(AgentEventContext)
}

export default function AgentEventProvider({ children }: { children: React.ReactNode }) {
  const [lastEvent, setLastEvent] = useState<AgentEvent | null>(null)
  const [taskNotifications, setTaskNotifications] = useState<TaskNotification[]>([])
  const [notificationCount, setNotificationCount] = useState(0)
  const esRef = useRef<EventSource | null>(null)

  // Fetch initial notification count
  useEffect(() => {
    fetch('/v1/agent/notifications/count')
      .then((r) => r.json())
      .then((data) => setNotificationCount(data.count ?? 0))
      .catch(() => {})
  }, [])

  useEffect(() => {
    function connect() {
      if (esRef.current) {
        esRef.current.close()
      }
      const es = new EventSource('/v1/agent/events')
      esRef.current = es

      es.addEventListener('task_run_finished', (e) => {
        try {
          const data = JSON.parse(e.data)
          setLastEvent({ type: 'task_run_finished', data })
          const notif: TaskNotification = {
            id: `${Date.now()}`,
            task_name: data.task_name || 'Task',
            status: data.status === 'error' ? 'error' : 'success',
            message: data.status === 'error'
              ? `Task "${data.task_name}" failed`
              : `Task "${data.task_name}" completed`,
          }
          setTaskNotifications((prev) => [...prev, notif])
          setTimeout(() => {
            setTaskNotifications((prev) => prev.filter((n) => n.id !== notif.id))
          }, 5000)
        } catch {}
      })

      es.addEventListener('task_run_started', (e) => {
        try {
          const data = JSON.parse(e.data)
          setLastEvent({ type: 'task_run_started', data })
        } catch {}
      })

      es.addEventListener('notification_new', (e) => {
        try {
          const data = JSON.parse(e.data)
          setNotificationCount(data.count ?? 0)
        } catch {}
      })

      es.onerror = () => {
        es.close()
        setTimeout(connect, 5000)
      }
    }

    connect()
    return () => {
      esRef.current?.close()
    }
  }, [])

  function dismissNotification(id: string) {
    setTaskNotifications((prev) => prev.filter((n) => n.id !== id))
  }

  function refreshNotificationCount() {
    fetch('/v1/agent/notifications/count')
      .then((r) => r.json())
      .then((data) => setNotificationCount(data.count ?? 0))
      .catch(() => {})
  }

  return (
    <AgentEventContext.Provider value={{ lastEvent, taskNotifications, dismissNotification, notificationCount, refreshNotificationCount }}>
      {children}
      {taskNotifications.length > 0 && (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
          {taskNotifications.map((notif) => (
            <div
              key={notif.id}
              className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm text-white shadow-lg ${
                notif.status === 'error' ? 'bg-red-600' : 'bg-green-600'
              }`}
            >
              <span>{notif.message}</span>
              <button
                onClick={() => dismissNotification(notif.id)}
                className="ml-2 text-white/80 hover:text-white"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      )}
    </AgentEventContext.Provider>
  )
}

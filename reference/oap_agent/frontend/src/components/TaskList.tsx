import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import type { AgentTask } from '@/lib/types'
import { useAgentEvents } from './AgentEventProvider'
import TaskForm from './TaskForm'

export default function TaskList() {
  const navigate = useNavigate()
  const { lastEvent } = useAgentEvents()
  const [tasks, setTasks] = useState<AgentTask[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTasks()
  }, [])

  // Auto-refresh when any task run finishes
  useEffect(() => {
    if (lastEvent?.type === 'task_run_finished') {
      fetchTasks()
    }
  }, [lastEvent])

  async function fetchTasks() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/v1/agent/tasks')
      if (!res.ok) {
        setError('Failed to load tasks')
        return
      }
      const data = await res.json()
      setTasks(data.tasks || [])
    } catch {
      setError('Agent service unavailable')
    } finally {
      setLoading(false)
    }
  }

  async function handleToggle(task: AgentTask) {
    try {
      const res = await fetch(`/v1/agent/tasks/${task.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !task.enabled }),
      })
      if (res.ok) {
        const data = await res.json()
        const updated = data.task || data
        setTasks((prev) => prev.map((t) => (t.id === task.id ? updated : t)))
      }
    } catch {}
  }

  if (showForm) {
    return (
      <div className="overflow-y-auto p-6">
        <div className="mx-auto max-w-2xl">
          <div className="mb-6 flex items-center gap-3">
            <button
              onClick={() => setShowForm(false)}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              &larr; Back
            </button>
            <h1 className="text-xl font-semibold text-gray-900">Create Task</h1>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-6">
            <TaskForm
              onSave={(task) => {
                setTasks((prev) => [task, ...prev])
                setShowForm(false)
              }}
              onCancel={() => setShowForm(false)}
            />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-gray-900">Tasks</h1>
          <button
            onClick={() => setShowForm(true)}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-600"
          >
            Create Task
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {loading ? (
          <p className="text-sm text-gray-400">Loading tasks...</p>
        ) : tasks.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-300 p-12 text-center">
            <p className="text-gray-500">No tasks yet.</p>
            <p className="mt-1 text-sm text-gray-400">
              Create a task to run prompts on a schedule.
            </p>
            <button
              onClick={() => setShowForm(true)}
              className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-600"
            >
              Create your first task
            </button>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Name</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Schedule</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Last Run</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-600">Enabled</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task, i) => (
                  <tr
                    key={task.id}
                    onClick={() => navigate(`/tasks/${task.id}`)}
                    className={`cursor-pointer hover:bg-gray-50 transition-colors ${
                      i !== 0 ? 'border-t border-gray-100' : ''
                    }`}
                  >
                    <td className="px-4 py-3 font-medium text-gray-900">{task.name}</td>
                    <td className="px-4 py-3 font-mono text-sm text-gray-500">
                      {task.schedule || <span className="text-gray-300">&mdash;</span>}
                    </td>
                    <td className="px-4 py-3">
                      <LastRunBadge task={task} />
                    </td>
                    <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => handleToggle(task)}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                          task.enabled ? 'bg-primary' : 'bg-gray-300'
                        }`}
                      >
                        <span
                          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                            task.enabled ? 'translate-x-5' : 'translate-x-0.5'
                          }`}
                        />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function LastRunBadge({ task }: { task: AgentTask }) {
  if (!task.last_run_status) {
    return <span className="text-sm text-gray-300">&mdash;</span>
  }

  const colors = {
    success: 'text-green-700 bg-green-50 border-green-200',
    error: 'text-red-700 bg-red-50 border-red-200',
    running: 'text-blue-700 bg-blue-50 border-blue-200',
  }
  const color = colors[task.last_run_status] || colors.running

  return (
    <div className="flex items-center gap-2">
      <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${color}`}>
        {task.last_run_status}
      </span>
      {task.last_run_at && (
        <span className="text-xs text-gray-400">{timeAgo(task.last_run_at)}</span>
      )}
    </div>
  )
}

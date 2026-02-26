import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import type { AgentTask, TaskRun } from '@/lib/types'
import { useAgentEvents } from './AgentEventProvider'
import TaskForm from './TaskForm'
import TaskRunDetail from './TaskRunDetail'

export default function TaskDetail() {
  const navigate = useNavigate()
  const { id: taskId } = useParams<{ id: string }>()
  const { lastEvent } = useAgentEvents()
  const [task, setTask] = useState<AgentTask | null>(null)
  const [runs, setRuns] = useState<TaskRun[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  useEffect(() => {
    if (taskId) fetchTask()
  }, [taskId])

  // Auto-refresh when SSE reports a run finished for this task
  useEffect(() => {
    if (
      lastEvent?.type === 'task_run_finished' &&
      lastEvent.data?.task_id === taskId
    ) {
      setRunning(false)
      fetchTask()
    }
  }, [lastEvent])

  async function fetchTask() {
    setLoading(true)
    setError(null)
    try {
      const [taskRes, runsRes] = await Promise.all([
        fetch(`/v1/agent/tasks/${taskId}`),
        fetch(`/v1/agent/tasks/${taskId}/runs`),
      ])
      if (!taskRes.ok) {
        setError('Task not found')
        return
      }
      const taskData = await taskRes.json()
      setTask(taskData.task || taskData)
      if (runsRes.ok) {
        const runsData = await runsRes.json()
        setRuns(runsData.runs || [])
      }
    } catch {
      setError('Failed to load task')
    } finally {
      setLoading(false)
    }
  }

  async function handleRunNow() {
    setRunning(true)
    setRunError(null)
    try {
      const res = await fetch(`/v1/agent/tasks/${taskId}/run`, { method: 'POST' })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setRunError(data.error || 'Failed to trigger run')
        setRunning(false)
        return
      }
      // running stays true until SSE task_run_finished arrives
    } catch {
      setRunError('Failed to trigger run')
      setRunning(false)
    }
  }

  async function handleToggleEnabled() {
    if (!task) return
    try {
      const res = await fetch(`/v1/agent/tasks/${taskId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !task.enabled }),
      })
      if (res.ok) {
        const data = await res.json()
        setTask(data.task || data)
      }
    } catch {}
  }

  async function handleDelete() {
    if (!confirm('Delete this task?')) return
    try {
      await fetch(`/v1/agent/tasks/${taskId}`, { method: 'DELETE' })
      navigate('/tasks')
    } catch {}
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-gray-400">Loading task...</p>
      </div>
    )
  }

  if (error || !task) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error || 'Task not found'}
        </div>
      </div>
    )
  }

  if (editing) {
    return (
      <div className="overflow-y-auto p-6">
        <div className="mx-auto max-w-2xl">
          <div className="mb-6 flex items-center gap-3">
            <button
              onClick={() => setEditing(false)}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              &larr; Back
            </button>
            <h1 className="text-xl font-semibold text-gray-900">Edit Task</h1>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-6">
            <TaskForm
              task={task}
              onSave={(updated) => {
                setTask(updated)
                setEditing(false)
              }}
              onCancel={() => setEditing(false)}
            />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="overflow-y-auto p-6">
      <div className="mx-auto max-w-2xl space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <button
              onClick={() => navigate('/tasks')}
              className="mb-1 text-sm text-gray-500 hover:text-gray-700"
            >
              &larr; All Tasks
            </button>
            <h1 className="text-xl font-semibold text-gray-900">{task.name}</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRunNow}
              disabled={running}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
            >
              {running ? 'Running...' : 'Run Now'}
            </button>
            <button
              onClick={() => setEditing(true)}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              Edit
            </button>
            <button
              onClick={handleDelete}
              className="rounded-md border border-red-200 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
            >
              Delete
            </button>
          </div>
        </div>

        {runError && (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {runError}
          </div>
        )}

        {/* Task info */}
        <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-700">Enabled</span>
            <button
              onClick={handleToggleEnabled}
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
          </div>
          <div>
            <span className="text-sm font-medium text-gray-700">Model</span>
            <p className="mt-0.5 font-mono text-sm text-gray-600">{task.model}</p>
          </div>
          {task.schedule && (
            <div>
              <span className="text-sm font-medium text-gray-700">Schedule</span>
              <p className="mt-0.5 font-mono text-sm text-gray-600">{task.schedule}</p>
            </div>
          )}
          <div>
            <span className="text-sm font-medium text-gray-700">Prompt</span>
            <p className="mt-0.5 text-sm text-gray-600 whitespace-pre-wrap">{task.prompt}</p>
          </div>
        </div>

        {/* Run history */}
        <div>
          <h2 className="mb-3 text-sm font-semibold text-gray-700">Run History</h2>
          {runs.length === 0 ? (
            <p className="text-sm text-gray-400">No runs yet.</p>
          ) : (
            <div className="space-y-2">
              {runs.map((run) => (
                <TaskRunDetail key={run.id} run={run} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

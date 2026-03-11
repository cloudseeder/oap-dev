import { useState, useEffect } from 'react'
import type { AgentTask } from '@/lib/types'
import CronInput from './CronInput'

interface TaskFormProps {
  task?: AgentTask
  onSave: (task: AgentTask) => void
  onCancel: () => void
}

export default function TaskForm({ task, onSave, onCancel }: TaskFormProps) {
  const [name, setName] = useState(task?.name || '')
  const [prompt, setPrompt] = useState(task?.prompt || '')
  const [schedule, setSchedule] = useState(task?.schedule || '')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState(task?.model || '')
  const [incremental, setIncremental] = useState(task?.incremental ?? true)

  useEffect(() => {
    fetch('/v1/agent/models')
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data) {
          setModels(data.models || [])
          if (!model) setModel(task?.model || data.default || data.models?.[0] || '')
        }
      })
      .catch(() => {})
  }, [])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !prompt.trim()) return

    setSaving(true)
    setError(null)

    const body = {
      name: name.trim(),
      prompt: prompt.trim(),
      schedule: schedule.trim() || undefined,
      model,
      incremental,
    }

    try {
      const url = task ? `/v1/agent/tasks/${task.id}` : '/v1/agent/tasks'
      const method = task ? 'PATCH' : 'POST'
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.error || 'Failed to save task')
        return
      }
      const data = await res.json()
      onSave(data.task || data)
    } catch {
      setError('Failed to save task')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder="Daily news summary"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Prompt</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          required
          rows={4}
          placeholder="Describe what this task should do..."
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Schedule (cron)</label>
        <CronInput value={schedule} onChange={setSchedule} disabled={saving} />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        >
          {models.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="incremental"
          checked={incremental}
          onChange={(e) => setIncremental(e.target.checked)}
          className="rounded border-gray-300 text-primary focus:ring-primary"
        />
        <label htmlFor="incremental" className="text-sm text-gray-700">
          Incremental — only include new information since last run
        </label>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving || !name.trim() || !prompt.trim()}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
        >
          {saving ? 'Saving...' : task ? 'Save Changes' : 'Create Task'}
        </button>
      </div>
    </form>
  )
}

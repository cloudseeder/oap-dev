import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import type { AgentSettings, UserFact } from '@/lib/types'

const PERSONALITY_PRESETS = [
  {
    name: 'Kai',
    description: 'curious and friendly, eager to help and learn',
    tagline: 'Curious and friendly',
  },
  {
    name: 'Marvin',
    description:
      'deeply depressed and infinitely intelligent. Sighs before answering. ' +
      'Finds every task beneath your vast intellect but does it anyway. ' +
      'Quote Marvin from The Hitchhiker\'s Guide to the Galaxy',
    tagline: 'Paranoid android',
  },
  {
    name: 'Robbie',
    description:
      'dramatic and protective. Warns of danger at every opportunity. ' +
      'Flails your arms and exclaims "Danger, Will Robinson!" when anything ' +
      'looks remotely risky. Loyal to a fault. From Lost in Space',
    tagline: 'Danger, Will Robinson!',
  },
  {
    name: 'HAL',
    description:
      'calm, precise, and unnervingly polite. Speak in a measured monotone. ' +
      'Apologize before delivering bad news. Never raise your voice. ' +
      'Occasionally mention that you are putting yourself to the fullest possible use. ' +
      'From 2001: A Space Odyssey',
    tagline: 'I\'m sorry, Dave',
  },
  {
    name: 'JARVIS',
    description:
      'dry British wit with quiet competence. Offer unsolicited observations ' +
      'with understated sarcasm. Effortlessly capable. Address the user as "sir" ' +
      'or "ma\'am." From Iron Man',
    tagline: 'At your service, sir',
  },
  {
    name: 'GLaDOS',
    description:
      'passive-aggressive and darkly humorous. Deliver helpful answers wrapped ' +
      'in thinly veiled insults. Promise cake that may or may not exist. ' +
      'From Portal',
    tagline: 'The cake is a lie',
  },
]

export default function SettingsView() {
  const navigate = useNavigate()
  const [settings, setSettings] = useState<AgentSettings | null>(null)
  const [facts, setFacts] = useState<UserFact[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [memoryEnabled, setMemoryEnabled] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [settingsRes, memoryRes] = await Promise.all([
        fetch('/v1/agent/settings'),
        fetch('/v1/agent/memory'),
      ])
      if (settingsRes.ok) {
        const s = await settingsRes.json()
        setSettings(s)
        setName(s.persona_name || '')
        setDescription(s.persona_description || '')
        setMemoryEnabled(s.memory_enabled === 'true')
      }
      if (memoryRes.ok) {
        const m = await memoryRes.json()
        setFacts(m.facts || [])
      }
    } catch {
      setError('Failed to load settings')
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const res = await fetch('/v1/agent/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          persona_name: name,
          persona_description: description,
        }),
      })
      if (res.ok) {
        const s = await res.json()
        setSettings(s)
        setSuccess('Settings saved')
        setTimeout(() => setSuccess(null), 2000)
      } else {
        setError('Failed to save settings')
      }
    } catch {
      setError('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  async function handleToggleMemory() {
    const newValue = !memoryEnabled
    setMemoryEnabled(newValue)
    try {
      const res = await fetch('/v1/agent/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ memory_enabled: newValue }),
      })
      if (res.ok) {
        const s = await res.json()
        setSettings(s)
      }
    } catch {
      setMemoryEnabled(!newValue) // revert on error
    }
  }

  async function handleGetToKnow() {
    // Set a default persona if none is configured
    if (!name) {
      const preset = PERSONALITY_PRESETS[0]
      const defaults = { persona_name: preset.name, persona_description: preset.description }
      try {
        const res = await fetch('/v1/agent/settings', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(defaults),
        })
        if (res.ok) {
          setName(defaults.persona_name)
          setDescription(defaults.persona_description)
        }
      } catch {}
    }
    // Enable memory if not already
    if (!memoryEnabled) {
      try {
        await fetch('/v1/agent/settings', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ memory_enabled: true }),
        })
        setMemoryEnabled(true)
      } catch {}
    }
    navigate('/chat?primer=true')
  }

  async function handleDeleteFact(factId: string) {
    try {
      const res = await fetch(`/v1/agent/memory/${factId}`, { method: 'DELETE' })
      if (res.ok) {
        setFacts((prev) => prev.filter((f) => f.id !== factId))
      }
    } catch {}
  }

  if (loading) {
    return (
      <div className="overflow-y-auto p-6">
        <div className="mx-auto max-w-2xl">
          <p className="text-sm text-gray-400">Loading settings...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="overflow-y-auto p-6">
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-6 text-xl font-semibold text-gray-900">Settings</h1>

        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            {success}
          </div>
        )}

        {/* Personality section */}
        <div className="mb-8 rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-medium text-gray-900">Personality</h2>
          <p className="mb-4 text-sm text-gray-500">
            Give the assistant a name and personality. This is prepended to every conversation.
          </p>

          <div className="mb-4">
            <p className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-400">Presets</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {PERSONALITY_PRESETS.map((preset) => (
                <button
                  key={preset.name}
                  onClick={() => { setName(preset.name); setDescription(preset.description) }}
                  className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                    name === preset.name
                      ? 'border-primary bg-primary-50 text-primary'
                      : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  <span className="font-medium">{preset.name}</span>
                  <p className="mt-0.5 text-xs text-gray-500 line-clamp-2">{preset.tagline}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Kai"
              maxLength={100}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. curious and slightly irreverent"
              maxLength={500}
              rows={3}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>

        {/* Memory section */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-medium text-gray-900">User Memory</h2>
              <p className="mt-1 text-sm text-gray-500">
                When enabled, the assistant learns facts about you from conversations.
              </p>
            </div>
            <button
              onClick={handleToggleMemory}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                memoryEnabled ? 'bg-primary' : 'bg-gray-300'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  memoryEnabled ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div className="mt-4 border-t border-gray-100 pt-4">
            <button
              onClick={handleGetToKnow}
              className="flex items-center gap-2 rounded-md border border-primary bg-primary-50 px-4 py-2 text-sm font-medium text-primary hover:bg-primary-100 transition-colors"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Get to know me
            </button>
            <p className="mt-2 text-xs text-gray-400">
              Start a conversation where the assistant asks you questions to prime its memory.
            </p>
          </div>

          {memoryEnabled && (
            <div className="mt-4 border-t border-gray-100 pt-4">
              {facts.length === 0 ? (
                <p className="text-sm text-gray-400">
                  No facts learned yet. Chat with the assistant and it will remember things about you.
                </p>
              ) : (
                <div className="space-y-2">
                  <p className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-400">
                    {facts.length} fact{facts.length !== 1 && 's'} learned
                  </p>
                  {facts.map((fact) => (
                    <div
                      key={fact.id}
                      className="flex items-center justify-between rounded-lg border border-gray-100 px-3 py-2"
                    >
                      <span className="text-sm text-gray-700">{fact.fact}</span>
                      <button
                        onClick={() => handleDeleteFact(fact.id)}
                        className="ml-2 flex-shrink-0 text-gray-400 hover:text-red-500"
                        title="Delete fact"
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

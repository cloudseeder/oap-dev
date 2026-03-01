export interface Conversation {
  id: string
  title: string
  model: string
  created_at: string
  updated_at: string
}

export interface ToolCall {
  tool: string
  args: Record<string, any>
  result?: string
  duration_ms?: number
}

export interface Message {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  tool_calls?: ToolCall[]
  metadata?: Record<string, any>
  created_at: string
  seq: number
}

export interface AgentTask {
  id: string
  name: string
  prompt: string
  schedule?: string
  model: string
  enabled: boolean
  created_at: string
  updated_at: string
  last_run_status?: 'running' | 'success' | 'error' | null
  last_run_at?: string | null
  last_run_error?: string | null
}

export interface TaskRun {
  id: string
  task_id: string
  started_at: string
  finished_at?: string
  status: 'running' | 'success' | 'error'
  prompt: string
  response?: string
  tool_calls?: ToolCall[]
  error?: string
  duration_ms?: number
}

export interface AgentSettings {
  persona_name: string
  persona_description: string
  memory_enabled: string
  voice_input_enabled: string
  voice_auto_send: string
  voice_auto_speak: string
}

export interface UserFact {
  id: string
  fact: string
  source_message: string
  created_at: string
  last_referenced: string
  reference_count: number
}

export function parseSSE(text: string): Array<{ event: string; data: any }> {
  const results: Array<{ event: string; data: any }> = []
  const lines = text.split('\n')
  let currentEvent = 'message'
  let currentData = ''

  for (const line of lines) {
    if (line.startsWith('event:')) {
      currentEvent = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      currentData = line.slice(5).trim()
    } else if (line === '') {
      if (currentData) {
        try {
          results.push({ event: currentEvent, data: JSON.parse(currentData) })
        } catch {
          results.push({ event: currentEvent, data: currentData })
        }
        currentEvent = 'message'
        currentData = ''
      }
    }
  }

  return results
}

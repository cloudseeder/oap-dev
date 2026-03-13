import { useState, useEffect, useCallback } from 'react'

// ── Types ──────────────────────────────────────────────────────────────

type Frequency = 'none' | 'minutes' | 'hourly' | 'daily' | 'weekly' | 'monthly'

interface BuilderState {
  frequency: Frequency
  minuteInterval: number   // 5 | 10 | 15 | 30
  minute: number           // 0-59
  hour: number             // 0-23
  daysOfWeek: number[]     // 0=Sun, 1=Mon ... 6=Sat
  dayOfMonth: number       // 1-28
}

interface CronInputProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}

// ── Defaults ───────────────────────────────────────────────────────────

const DEFAULT_STATE: BuilderState = {
  frequency: 'none',
  minuteInterval: 15,
  minute: 0,
  hour: 9,
  daysOfWeek: [1, 2, 3, 4, 5],
  dayOfMonth: 1,
}

const MINUTE_INTERVALS = [5, 10, 15, 30]
const MINUTE_OPTIONS = Array.from({ length: 60 }, (_, i) => i)
const HOURS = Array.from({ length: 24 }, (_, i) => i)
const MINUTES = Array.from({ length: 60 }, (_, i) => i)
const DAYS_OF_MONTH = Array.from({ length: 28 }, (_, i) => i + 1)
const WEEKDAYS = [
  { value: 1, label: 'Mon' },
  { value: 2, label: 'Tue' },
  { value: 3, label: 'Wed' },
  { value: 4, label: 'Thu' },
  { value: 5, label: 'Fri' },
  { value: 6, label: 'Sat' },
  { value: 0, label: 'Sun' },
]

// ── Cron generation ────────────────────────────────────────────────────

function stateToCron(s: BuilderState): string {
  switch (s.frequency) {
    case 'none':
      return ''
    case 'minutes':
      return `*/${s.minuteInterval} * * * *`
    case 'hourly':
      return `${s.minute} * * * *`
    case 'daily':
      return `${s.minute} ${s.hour} * * *`
    case 'weekly': {
      const days = s.daysOfWeek.length > 0 ? s.daysOfWeek.sort((a, b) => a - b).join(',') : '*'
      return `${s.minute} ${s.hour} * * ${days}`
    }
    case 'monthly':
      return `${s.minute} ${s.hour} ${s.dayOfMonth} * *`
  }
}

// ── Cron parsing ───────────────────────────────────────────────────────

function parseCron(expr: string): BuilderState | null {
  const trimmed = expr.trim()
  if (!trimmed) return null

  const parts = trimmed.split(/\s+/)
  if (parts.length !== 5) return null

  const [minPart, hourPart, domPart, monPart, dowPart] = parts

  // */N * * * * → every N minutes
  const intervalMatch = minPart.match(/^\*\/(\d+)$/)
  if (intervalMatch && hourPart === '*' && domPart === '*' && monPart === '*' && dowPart === '*') {
    const interval = parseInt(intervalMatch[1])
    if (MINUTE_INTERVALS.includes(interval)) {
      return { ...DEFAULT_STATE, frequency: 'minutes', minuteInterval: interval }
    }
  }

  const min = parseInt(minPart)
  if (isNaN(min) || min < 0 || min > 59) return null

  // N * * * * → hourly at :N
  if (hourPart === '*' && domPart === '*' && monPart === '*' && dowPart === '*') {
    return { ...DEFAULT_STATE, frequency: 'hourly', minute: min }
  }

  const hour = parseInt(hourPart)
  if (isNaN(hour) || hour < 0 || hour > 23) return null

  // N H * * * → daily
  if (domPart === '*' && monPart === '*' && dowPart === '*') {
    return { ...DEFAULT_STATE, frequency: 'daily', minute: min, hour }
  }

  // N H * * DOW → weekly
  if (domPart === '*' && monPart === '*' && dowPart !== '*') {
    const days = parseDow(dowPart)
    if (days) {
      return { ...DEFAULT_STATE, frequency: 'weekly', minute: min, hour, daysOfWeek: days }
    }
  }

  // N H DOM * * → monthly
  if (monPart === '*' && dowPart === '*') {
    const dom = parseInt(domPart)
    if (!isNaN(dom) && dom >= 1 && dom <= 28) {
      return { ...DEFAULT_STATE, frequency: 'monthly', minute: min, hour, dayOfMonth: dom }
    }
  }

  return null
}

function parseDow(s: string): number[] | null {
  const result: number[] = []
  for (const part of s.split(',')) {
    const rangeMatch = part.match(/^(\d)-(\d)$/)
    if (rangeMatch) {
      const start = parseInt(rangeMatch[1])
      const end = parseInt(rangeMatch[2])
      if (start > 6 || end > 6) return null
      for (let i = start; i <= end; i++) result.push(i)
    } else {
      const n = parseInt(part)
      if (isNaN(n) || n < 0 || n > 6) return null
      result.push(n)
    }
  }
  return result.length > 0 ? [...new Set(result)] : null
}

// ── Client-side cron validation ────────────────────────────────────────

function validateCron(expr: string): string | null {
  const trimmed = expr.trim()
  if (!trimmed) return null // empty is ok (no schedule)

  const parts = trimmed.split(/\s+/)
  if (parts.length !== 5) return `Expected 5 fields, got ${parts.length}`

  const [minPart, hourPart, domPart, monPart, dowPart] = parts

  const checkField = (val: string, min: number, max: number, name: string): string | null => {
    if (val === '*') return null
    // */N
    const step = val.match(/^\*\/(\d+)$/)
    if (step) {
      const n = parseInt(step[1])
      if (n < 1 || n > max) return `${name}: step /${n} out of range (1-${max})`
      return null
    }
    // comma-separated values and ranges
    for (const segment of val.split(',')) {
      const range = segment.match(/^(\d+)-(\d+)$/)
      if (range) {
        const a = parseInt(range[1]), b = parseInt(range[2])
        if (a < min || a > max || b < min || b > max) return `${name}: ${segment} out of range (${min}-${max})`
        continue
      }
      const n = parseInt(segment)
      if (isNaN(n) || n < min || n > max) return `${name}: ${segment} out of range (${min}-${max})`
    }
    return null
  }

  return (
    checkField(minPart, 0, 59, 'Minute') ||
    checkField(hourPart, 0, 23, 'Hour') ||
    checkField(domPart, 1, 31, 'Day of month') ||
    checkField(monPart, 1, 12, 'Month') ||
    checkField(dowPart, 0, 7, 'Day of week')
  )
}

// ── Human-readable description ─────────────────────────────────────────

function formatTime(hour: number, minute: number): string {
  const period = hour >= 12 ? 'PM' : 'AM'
  const h = hour % 12 || 12
  const m = minute.toString().padStart(2, '0')
  return `${h}:${m} ${period}`
}

function describeCron(expr: string): string {
  if (!expr.trim()) return ''
  const state = parseCron(expr)
  if (!state) return expr.trim()

  switch (state.frequency) {
    case 'none':
      return ''
    case 'minutes':
      return `Every ${state.minuteInterval} minutes`
    case 'hourly':
      return `Hourly at :${state.minute.toString().padStart(2, '0')}`
    case 'daily':
      return `Daily at ${formatTime(state.hour, state.minute)}`
    case 'weekly': {
      const dayNames = state.daysOfWeek
        .sort((a, b) => a - b)
        .map((d) => WEEKDAYS.find((w) => w.value === d)?.label)
        .filter(Boolean)
      return `Every ${dayNames.join(', ')} at ${formatTime(state.hour, state.minute)}`
    }
    case 'monthly': {
      const suffix = ordinalSuffix(state.dayOfMonth)
      return `Monthly on the ${state.dayOfMonth}${suffix} at ${formatTime(state.hour, state.minute)}`
    }
  }
}

function ordinalSuffix(n: number): string {
  if (n >= 11 && n <= 13) return 'th'
  switch (n % 10) {
    case 1: return 'st'
    case 2: return 'nd'
    case 3: return 'rd'
    default: return 'th'
  }
}

// ── Select component ───────────────────────────────────────────────────

function Select({
  value,
  onChange,
  options,
  disabled,
  className = '',
}: {
  value: string | number
  onChange: (val: string) => void
  options: { value: string | number; label: string }[]
  disabled?: boolean
  className?: string
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={`rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:bg-gray-50 disabled:opacity-50 ${className}`}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

// ── Main component ─────────────────────────────────────────────────────

export default function CronInput({ value, onChange, disabled }: CronInputProps) {
  const [rawMode, setRawMode] = useState(false)
  const [state, setState] = useState<BuilderState>(DEFAULT_STATE)

  // On mount, parse existing value into builder state
  useEffect(() => {
    if (!value) return
    const parsed = parseCron(value)
    if (parsed) {
      setState(parsed)
      setRawMode(false)
    } else if (value.trim()) {
      setRawMode(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const emitCron = useCallback((newState: BuilderState) => {
    setState(newState)
    onChange(stateToCron(newState))
  }, [onChange])

  const updateField = useCallback(<K extends keyof BuilderState>(field: K, val: BuilderState[K]) => {
    emitCron({ ...state, [field]: val })
  }, [state, emitCron])

  const toggleDay = useCallback((day: number) => {
    const days = state.daysOfWeek.includes(day)
      ? state.daysOfWeek.filter((d) => d !== day)
      : [...state.daysOfWeek, day]
    emitCron({ ...state, daysOfWeek: days })
  }, [state, emitCron])

  // ── Raw mode ──

  if (rawMode) {
    const rawError = validateCron(value)
    const description = !rawError ? describeCron(value) : null

    return (
      <div className="space-y-1.5">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="e.g. 0 9 * * 1-5"
          className={`w-full rounded-md border px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 disabled:bg-gray-50 disabled:opacity-50 ${
            rawError
              ? 'border-red-300 focus:border-red-400 focus:ring-red-200'
              : 'border-gray-300 focus:border-primary focus:ring-primary'
          }`}
        />
        {rawError && (
          <p className="text-xs text-red-600">{rawError}</p>
        )}
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              const parsed = parseCron(value)
              if (parsed) {
                setState(parsed)
                setRawMode(false)
              } else {
                setState(DEFAULT_STATE)
                onChange('')
                setRawMode(false)
              }
            }}
            disabled={disabled}
            className="text-xs text-primary hover:underline disabled:opacity-50"
          >
            Use schedule builder
          </button>
          {description && (
            <p className="text-xs text-gray-500">{description}</p>
          )}
        </div>
      </div>
    )
  }

  // ── Builder mode ──

  const frequencyOptions = [
    { value: 'none', label: 'No schedule' },
    { value: 'minutes', label: 'Every X minutes' },
    { value: 'hourly', label: 'Hourly' },
    { value: 'daily', label: 'Daily' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'monthly', label: 'Monthly' },
  ]

  const hourOptions = HOURS.map((h) => ({
    value: h,
    label: formatTime(h, 0).replace(':00 ', ' ').replace(':00', ''),
  }))

  const minuteOptions = MINUTES.map((m) => ({
    value: m,
    label: `:${m.toString().padStart(2, '0')}`,
  }))

  const hourlyMinuteOptions = MINUTE_OPTIONS.map((m) => ({
    value: m,
    label: `:${m.toString().padStart(2, '0')}`,
  }))

  const hasSchedule = state.frequency !== 'none'
  const cronStr = stateToCron(state)

  return (
    <div className="space-y-2">
      {/* Frequency + contextual fields */}
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={state.frequency}
          onChange={(v) => emitCron({ ...state, frequency: v as Frequency })}
          options={frequencyOptions}
          disabled={disabled}
        />

        {state.frequency === 'minutes' && (
          <Select
            value={state.minuteInterval}
            onChange={(v) => updateField('minuteInterval', parseInt(v))}
            options={MINUTE_INTERVALS.map((n) => ({ value: n, label: `${n} min` }))}
            disabled={disabled}
          />
        )}

        {state.frequency === 'hourly' && (
          <>
            <span className="text-sm text-gray-500">at</span>
            <Select
              value={state.minute}
              onChange={(v) => updateField('minute', parseInt(v))}
              options={hourlyMinuteOptions}
              disabled={disabled}
            />
          </>
        )}

        {(state.frequency === 'daily' || state.frequency === 'weekly' || state.frequency === 'monthly') && (
          <>
            <span className="text-sm text-gray-500">at</span>
            <Select
              value={state.hour}
              onChange={(v) => updateField('hour', parseInt(v))}
              options={hourOptions}
              disabled={disabled}
            />
            <Select
              value={state.minute}
              onChange={(v) => updateField('minute', parseInt(v))}
              options={minuteOptions}
              disabled={disabled}
            />
          </>
        )}

        {state.frequency === 'monthly' && (
          <>
            <span className="text-sm text-gray-500">on day</span>
            <Select
              value={state.dayOfMonth}
              onChange={(v) => updateField('dayOfMonth', parseInt(v))}
              options={DAYS_OF_MONTH.map((d) => ({ value: d, label: `${d}` }))}
              disabled={disabled}
            />
          </>
        )}
      </div>

      {/* Day-of-week checkboxes for weekly */}
      {state.frequency === 'weekly' && (
        <div className="flex flex-wrap gap-1">
          {WEEKDAYS.map((day) => {
            const active = state.daysOfWeek.includes(day.value)
            return (
              <button
                key={day.value}
                type="button"
                onClick={() => toggleDay(day.value)}
                disabled={disabled}
                className={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
                  active
                    ? 'border-primary bg-primary text-white'
                    : 'border-gray-300 bg-white text-gray-600 hover:bg-gray-50'
                }`}
              >
                {day.label}
              </button>
            )
          })}
        </div>
      )}

      {/* Summary + raw toggle */}
      <div className="flex items-center justify-between">
        {hasSchedule ? (
          <p className="text-xs text-gray-500">
            {describeCron(cronStr)}
            <span className="ml-2 font-mono text-gray-400">{cronStr}</span>
          </p>
        ) : (
          <p className="text-xs text-gray-400">Task will be manual-run only</p>
        )}
        <button
          type="button"
          onClick={() => setRawMode(true)}
          disabled={disabled}
          className="text-xs text-primary hover:underline disabled:opacity-50"
        >
          Edit as cron
        </button>
      </div>
    </div>
  )
}

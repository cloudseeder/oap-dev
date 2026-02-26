interface ExperienceBadgeProps {
  status: string
}

export default function ExperienceBadge({ status }: ExperienceBadgeProps) {
  const config = {
    hit: { label: 'cache hit', classes: 'bg-green-100 text-green-700' },
    miss: { label: 'cache miss', classes: 'bg-gray-100 text-gray-600' },
    degraded: { label: 'degraded', classes: 'bg-yellow-100 text-yellow-700' },
  }

  const entry = config[status as keyof typeof config]
  if (!entry) return null

  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${entry.classes}`}>
      {entry.label}
    </span>
  )
}

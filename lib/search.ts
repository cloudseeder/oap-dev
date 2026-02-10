// Ported from registry/server.js:160-232
import type { AppDocument, AppResult } from './types'

export function searchApps(
  query: string,
  apps: AppDocument[]
): { app: AppDocument; score: number; matchedKeywords: string[] }[] {
  const keywords = query.toLowerCase().split(/\s+/).filter(w => w.length > 2)

  const scored = apps.map(app => {
    const searchText = [
      app.name,
      app.tagline,
      app.description,
      app.summary,
      JSON.stringify(app.solves),
      JSON.stringify(app.ideal_for),
      JSON.stringify(app.categories),
      JSON.stringify(app.differentiators),
      app.pricing_model,
      app.starting_price,
    ].filter(Boolean).join(' ').toLowerCase()

    let score = 0
    const matchedKeywords: string[] = []

    for (const keyword of keywords) {
      if (searchText.includes(keyword)) {
        score += 1
        matchedKeywords.push(keyword)
      }
    }

    // Bonus for name/tagline matches
    const nameTagline = `${app.name} ${app.tagline}`.toLowerCase()
    for (const keyword of keywords) {
      if (nameTagline.includes(keyword)) score += 0.5
    }

    // Normalize
    const normalizedScore = keywords.length > 0 ? score / (keywords.length * 1.5) : 0

    return { app, score: Math.min(normalizedScore, 1.0), matchedKeywords }
  })

  return scored
    .filter(s => s.score > 0.1)
    .sort((a, b) => b.score - a.score)
    .slice(0, 20)
}

export function formatAppResult(app: AppDocument, score?: number): AppResult {
  const uptime = app.uptime_checks_total > 0
    ? parseFloat(((app.uptime_checks_passed / app.uptime_checks_total) * 100).toFixed(1))
    : undefined

  const result: AppResult = {
    domain: app.domain,
    name: app.name,
    tagline: app.tagline,
    manifest_url: app.manifest_url,
    trust_signals: {
      dns_verified: app.dns_verified,
      health_ok: app.health_ok,
      last_checked: app.last_verified,
      ...(uptime !== undefined && { uptime_30d: uptime }),
    },
    pricing: {
      model: app.pricing_model,
      ...(app.starting_price && { starting_price: app.starting_price }),
    },
    categories: app.categories,
  }

  if (score !== undefined) {
    result.match_score = parseFloat(score.toFixed(2))
  }

  return result
}

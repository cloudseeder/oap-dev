// Ported from registry/server.js:88-158
import { createHash } from 'crypto'
import { resolve } from 'dns/promises'

export async function fetchManifest(url: string): Promise<{ json: Record<string, unknown>; manifestUrl: string }> {
  const manifestUrl = url.replace(/\/$/, '') + '/.well-known/oap.json'
  const response = await fetch(manifestUrl, {
    signal: AbortSignal.timeout(10000),
    headers: { 'User-Agent': 'OAP-Registry/0.1' },
  })
  if (!response.ok) throw new Error(`HTTP ${response.status} from ${manifestUrl}`)
  const json = await response.json()
  return { json, manifestUrl }
}

export async function verifyDNS(domain: string): Promise<boolean> {
  try {
    const records = await resolve(`_oap.${domain}`, 'TXT')
    const flat = records.map(r => r.join('')).join(' ')
    return flat.includes('v=oap1')
  } catch {
    return false
  }
}

export async function checkHealth(manifest: Record<string, unknown>): Promise<boolean | null> {
  const verification = manifest.verification as Record<string, unknown> | undefined
  const identity = manifest.identity as Record<string, unknown> | undefined

  // Use declared health_endpoint for deep health check, otherwise fall back
  // to the manifest URL as a basic liveness check
  const endpoint = (verification?.health_endpoint as string | undefined)
    || (identity?.url ? (identity.url as string).replace(/\/$/, '') + '/.well-known/oap.json' : null)

  if (!endpoint) return null
  try {
    const response = await fetch(endpoint, {
      signal: AbortSignal.timeout(5000),
      headers: { 'User-Agent': 'OAP-Registry/0.1' },
    })
    return response.ok
  } catch {
    return false
  }
}

export function hashManifest(json: Record<string, unknown>): string {
  return 'sha256:' + createHash('sha256').update(JSON.stringify(json)).digest('hex').slice(0, 16)
}

export function extractDomain(url: string): string | null {
  try {
    return new URL(url).hostname
  } catch {
    return null
  }
}

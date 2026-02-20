/** Reusable proxy helper for forwarding requests to the backend services via Cloudflare Tunnel. */

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8300'
const TRUST_URL = process.env.TRUST_URL
const DASHBOARD_URL = process.env.DASHBOARD_URL
const BACKEND_SECRET = process.env.BACKEND_SECRET

/** Port-to-env-var mapping for tunnel deployments */
const SERVICE_URLS: Record<number, string | undefined> = {
  8301: TRUST_URL,
  8302: DASHBOARD_URL,
}

export interface ProxyOptions {
  /** Backend service port override (default: uses BACKEND_URL as-is) */
  port?: number
  /** Request timeout in ms (default: 30000) */
  timeout?: number
}

/**
 * Proxy a request to a backend service.
 * When port is specified, uses the matching service URL env var if set (tunnel mode),
 * otherwise falls back to port-swapping on BACKEND_URL (local dev mode).
 */
export async function proxyFetch(
  path: string,
  init: RequestInit = {},
  options: ProxyOptions = {}
): Promise<Response> {
  const { port, timeout = 30000 } = options
  let base = BACKEND_URL.replace(/\/$/, '')

  if (port) {
    const serviceUrl = SERVICE_URLS[port]
    if (serviceUrl) {
      base = serviceUrl.replace(/\/$/, '')
    } else {
      try {
        const url = new URL(base)
        url.port = String(port)
        base = url.toString().replace(/\/$/, '')
      } catch {
        // If BACKEND_URL isn't a full URL, just use it with port
        base = `http://localhost:${port}`
      }
    }
  }

  const url = `${base}${path}`
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...init.headers as Record<string, string>,
  }

  // Add backend secret if configured
  if (BACKEND_SECRET) {
    headers['X-Backend-Token'] = BACKEND_SECRET
  }

  const response = await fetch(url, {
    ...init,
    signal: AbortSignal.timeout(timeout),
    headers,
  })

  return response
}

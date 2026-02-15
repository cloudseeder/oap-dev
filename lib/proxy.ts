/** Reusable proxy helper for forwarding requests to the backend services via Cloudflare Tunnel. */

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8300'

export interface ProxyOptions {
  /** Backend service port override (default: uses BACKEND_URL as-is) */
  port?: number
  /** Request timeout in ms (default: 30000) */
  timeout?: number
}

/**
 * Proxy a request to a backend service.
 * When port is specified, replaces the port in BACKEND_URL.
 * When BACKEND_URL uses a tunnel (no port), appends a path prefix instead.
 */
export async function proxyFetch(
  path: string,
  init: RequestInit = {},
  options: ProxyOptions = {}
): Promise<Response> {
  const { port, timeout = 30000 } = options
  let base = BACKEND_URL.replace(/\/$/, '')

  if (port) {
    try {
      const url = new URL(base)
      url.port = String(port)
      base = url.toString().replace(/\/$/, '')
    } catch {
      // If BACKEND_URL isn't a full URL, just use it with port
      base = `http://localhost:${port}`
    }
  }

  const url = `${base}${path}`
  const response = await fetch(url, {
    ...init,
    signal: AbortSignal.timeout(timeout),
    headers: {
      'Content-Type': 'application/json',
      ...init.headers,
    },
  })

  return response
}

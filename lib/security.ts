import { timingSafeEqual } from 'crypto'
import dns from 'dns/promises'
import { NextRequest } from 'next/server'

// === SSRF URL Validation (C1) ===

const PRIVATE_IPV4_RANGES = [
  /^127\./, // loopback
  /^10\./, // Class A private
  /^172\.(1[6-9]|2\d|3[01])\./, // Class B private
  /^192\.168\./, // Class C private
  /^169\.254\./, // link-local
  /^0\./, // current network
]

function isPrivateIPv4(ip: string): boolean {
  return PRIVATE_IPV4_RANGES.some(re => re.test(ip))
}

function isPrivateIPv6(ip: string): boolean {
  const lower = ip.toLowerCase()
  return (
    lower === '::1' ||
    lower.startsWith('fc') ||
    lower.startsWith('fd') ||
    lower.startsWith('fe80')
  )
}

export async function validateUrl(url: string): Promise<void> {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    throw new Error('Invalid URL')
  }

  // Enforce HTTPS in production
  if (process.env.NODE_ENV === 'production' && parsed.protocol !== 'https:') {
    throw new Error('Only HTTPS URLs are allowed')
  }

  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    throw new Error('Only HTTP(S) URLs are allowed')
  }

  // Resolve DNS and check for private IPs
  const hostname = parsed.hostname

  // Block IPs used directly in URL
  if (/^\d+\.\d+\.\d+\.\d+$/.test(hostname)) {
    if (isPrivateIPv4(hostname)) {
      throw new Error('Private IP addresses are not allowed')
    }
    return
  }

  try {
    const ipv4Addresses = await dns.resolve4(hostname).catch(() => [] as string[])
    const ipv6Addresses = await dns.resolve6(hostname).catch(() => [] as string[])
    const allAddresses = [...ipv4Addresses, ...ipv6Addresses]

    if (allAddresses.length === 0) {
      throw new Error('Could not resolve hostname')
    }

    for (const ip of allAddresses) {
      if (isPrivateIPv4(ip) || isPrivateIPv6(ip)) {
        throw new Error('Private IP addresses are not allowed')
      }
    }
  } catch (e) {
    if (e instanceof Error && e.message === 'Private IP addresses are not allowed') {
      throw e
    }
    if (e instanceof Error && e.message === 'Could not resolve hostname') {
      throw e
    }
    throw new Error('DNS resolution failed')
  }
}

// === Rate Limiter (H1) ===

interface RateLimitEntry {
  count: number
  resetAt: number
}

export class RateLimiter {
  private store = new Map<string, RateLimitEntry>()
  private maxRequests: number
  private windowMs: number

  constructor(maxRequests: number, windowMs: number) {
    this.maxRequests = maxRequests
    this.windowMs = windowMs
  }

  check(ip: string): { allowed: boolean; retryAfterMs: number } {
    const now = Date.now()

    // Auto-cleanup at 10k entries
    if (this.store.size > 10000) {
      for (const [key, entry] of this.store) {
        if (now > entry.resetAt) this.store.delete(key)
      }
    }

    const entry = this.store.get(ip)

    if (!entry || now > entry.resetAt) {
      this.store.set(ip, { count: 1, resetAt: now + this.windowMs })
      return { allowed: true, retryAfterMs: 0 }
    }

    if (entry.count >= this.maxRequests) {
      return { allowed: false, retryAfterMs: entry.resetAt - now }
    }

    entry.count++
    return { allowed: true, retryAfterMs: 0 }
  }
}

// Pre-configured rate limiters
export const registerLimiter = new RateLimiter(5, 15 * 60 * 1000) // 5 per 15 min
export const refreshLimiter = new RateLimiter(10, 15 * 60 * 1000) // 10 per 15 min
export const searchLimiter = new RateLimiter(30, 60 * 1000) // 30 per min
export const allAppsLimiter = new RateLimiter(10, 60 * 1000) // 10 per min

export function getClientIP(request: NextRequest): string {
  const forwarded = request.headers.get('x-forwarded-for')
  if (forwarded) {
    return forwarded.split(',')[0].trim()
  }
  return '127.0.0.1'
}

// === Timing-Safe Comparison (L3) ===

export function timingSafeCompare(a: string, b: string): boolean {
  if (typeof a !== 'string' || typeof b !== 'string') return false
  const bufA = Buffer.from(a)
  const bufB = Buffer.from(b)
  if (bufA.length !== bufB.length) {
    // Compare against self to maintain constant time
    timingSafeEqual(bufA, bufA)
    return false
  }
  return timingSafeEqual(bufA, bufB)
}

import { NextRequest, NextResponse } from 'next/server'

const ALLOWED_ORIGINS = new Set([
  'https://oap.dev',
  'https://www.oap.dev',
  ...(process.env.NODE_ENV !== 'production' ? ['http://localhost:3000'] : []),
])

function addCorsHeaders(response: NextResponse, origin: string | null): NextResponse {
  if (origin && ALLOWED_ORIGINS.has(origin)) {
    response.headers.set('Access-Control-Allow-Origin', origin)
    response.headers.set('Vary', 'Origin')
  }
  response.headers.set('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
  response.headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization')
  return response
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const origin = request.headers.get('Origin')

  // Handle CORS preflight for API routes
  if (pathname.startsWith('/api/') && request.method === 'OPTIONS') {
    const response = new NextResponse(null, { status: 204 })
    return addCorsHeaders(response, origin)
  }

  // API routes pass through with CORS headers
  if (pathname.startsWith('/api/')) {
    const response = NextResponse.next()
    return addCorsHeaders(response, origin)
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|public/).*)',
  ],
}

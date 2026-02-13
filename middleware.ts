import { NextRequest, NextResponse } from 'next/server'

function addCorsHeaders(response: NextResponse): NextResponse {
  response.headers.set('Access-Control-Allow-Origin', '*')
  response.headers.set('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
  response.headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization')
  return response
}

export function middleware(request: NextRequest) {
  const hostname = request.headers.get('host') || ''
  const { pathname } = request.nextUrl

  // Handle CORS preflight for API routes
  if (pathname.startsWith('/api/') && request.method === 'OPTIONS') {
    const response = new NextResponse(null, { status: 204 })
    return addCorsHeaders(response)
  }

  // API routes pass through from any domain with CORS headers
  if (pathname.startsWith('/api/')) {
    const response = NextResponse.next()
    return addCorsHeaders(response)
  }

  // Registry subdomain detection
  const isRegistry =
    hostname.startsWith('registry.') ||
    hostname.startsWith('registry.localhost')

  // Rewrite registry subdomain to /r/* routes
  if (isRegistry && !pathname.startsWith('/r')) {
    const url = request.nextUrl.clone()
    url.pathname = `/r${pathname}`
    return NextResponse.rewrite(url)
  }

  // Don't serve /r/* routes on the main domain (except via direct URL in dev)
  return NextResponse.next()
}

export const config = {
  matcher: [
    // Match all paths except static files and Next internals
    '/((?!_next/static|_next/image|favicon.ico|public/).*)',
  ],
}

import { NextRequest, NextResponse } from 'next/server'

export function middleware(request: NextRequest) {
  const hostname = request.headers.get('host') || ''
  const { pathname } = request.nextUrl

  // API routes pass through from any domain
  if (pathname.startsWith('/api/')) {
    return NextResponse.next()
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

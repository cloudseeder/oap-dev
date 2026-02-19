'use client'

import Link from 'next/link'
import { useState, useEffect, useRef } from 'react'

export default function Header() {
  const [docsOpen, setDocsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDocsOpen(false)
      }
    }
    if (docsOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [docsOpen])

  return (
    <header className="border-b border-gray-200 bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <Link href="/" className="text-xl font-bold text-primary">
            OAP
          </Link>
          <nav className="flex items-center gap-6 text-sm">
            <Link href="/spec" className="text-gray-600 hover:text-gray-900">
              Spec
            </Link>
            <Link href="/playground" className="text-gray-600 hover:text-gray-900">
              Playground
            </Link>
            <Link href="/discover" className="text-gray-600 hover:text-gray-900">
              Discover
            </Link>
            <Link href="/dashboard" className="text-gray-600 hover:text-gray-900">
              Dashboard
            </Link>
            <div className="relative" ref={dropdownRef}>
              <button
                onClick={() => setDocsOpen(!docsOpen)}
                className="flex items-center gap-1 text-gray-600 hover:text-gray-900"
              >
                Docs
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {docsOpen && (
                <div className="absolute right-0 top-full z-50 mt-2 w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                  <Link href="/docs/quickstart" onClick={() => setDocsOpen(false)} className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                    Quick Start
                  </Link>
                  <Link href="/docs/architecture" onClick={() => setDocsOpen(false)} className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                    Architecture
                  </Link>
                  <Link href="/docs/trust" onClick={() => setDocsOpen(false)} className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                    Trust Overlay
                  </Link>
                  <Link href="/docs/a2a" onClick={() => setDocsOpen(false)} className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                    OAP + A2A
                  </Link>
                  <Link href="/docs/manifesto" onClick={() => setDocsOpen(false)} className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                    Manifesto
                  </Link>
                  <div className="my-1 border-t border-gray-100" />
                  <span className="block px-4 py-1 text-xs font-semibold uppercase tracking-wider text-gray-400">Experimental</span>
                  <Link href="/docs/robotics" onClick={() => setDocsOpen(false)} className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                    Robotics
                  </Link>
                  <Link href="/docs/procedural-memory" onClick={() => setDocsOpen(false)} className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                    Procedural Memory
                  </Link>
                </div>
              )}
            </div>
            <a
              href="https://github.com/cloudseeder/oap"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-600 hover:text-gray-900"
            >
              GitHub
            </a>
          </nav>
        </div>
      </div>
    </header>
  )
}

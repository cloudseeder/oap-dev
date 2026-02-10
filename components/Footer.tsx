import Link from 'next/link'

export default function Footer() {
  return (
    <footer className="border-t border-gray-200 bg-white">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <div className="flex items-center gap-6 text-sm text-gray-500">
            <Link href="/spec" className="hover:text-gray-700">Spec</Link>
            <Link href="/registry" className="hover:text-gray-700">Registry Spec</Link>
            <Link href="/docs/quickstart" className="hover:text-gray-700">Quick Start</Link>
            <a
              href="https://github.com/OpenApplicationProtocol/oap"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-700"
            >
              GitHub
            </a>
          </div>
          <p className="text-sm text-gray-400">
            CC0 1.0 Universal &mdash; Public Domain
          </p>
        </div>
      </div>
    </footer>
  )
}

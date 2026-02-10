import Link from 'next/link'

export default function Header() {
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
            <Link href="/registry" className="text-gray-600 hover:text-gray-900">
              Registry Spec
            </Link>
            <Link href="/docs/quickstart" className="text-gray-600 hover:text-gray-900">
              Quick Start
            </Link>
            <a
              href="https://registry.oap.dev"
              className="text-gray-600 hover:text-gray-900"
            >
              Registry
            </a>
            <a
              href="https://github.com/cloudseeder/opa-dev"
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

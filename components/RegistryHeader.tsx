import Link from 'next/link'

export default function RegistryHeader() {
  return (
    <header className="border-b border-gray-200 bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <Link href="/r" className="text-xl font-bold text-primary">
            OAP Registry
          </Link>
          <nav className="flex items-center gap-6 text-sm">
            <Link href="/r" className="text-gray-600 hover:text-gray-900">
              Search
            </Link>
            <Link href="/r/categories" className="text-gray-600 hover:text-gray-900">
              Categories
            </Link>
            <Link href="/r/docs" className="text-gray-600 hover:text-gray-900">
              API Docs
            </Link>
            <a
              href="https://oap.dev"
              className="text-gray-600 hover:text-gray-900"
            >
              oap.dev
            </a>
            <Link
              href="/r#register"
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-600"
            >
              Register Your App
            </Link>
          </nav>
        </div>
      </div>
    </header>
  )
}

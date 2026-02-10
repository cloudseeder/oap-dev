import Link from 'next/link'
import AppCard from '@/components/AppCard'
import { getAppsByCategory } from '@/lib/firestore'
import { formatAppResult } from '@/lib/search'
import type { Metadata } from 'next'

export const dynamic = 'force-dynamic'

interface PageProps {
  params: Promise<{ category: string }>
  searchParams: Promise<{ page?: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { category } = await params
  return {
    title: `${category} — OAP Registry`,
    description: `Browse ${category} apps in the OAP registry.`,
  }
}

export default async function CategoryDetailPage({ params, searchParams }: PageProps) {
  const { category } = await params
  const { page: pageParam } = await searchParams
  const page = parseInt(pageParam || '1')
  const limit = 20

  const { apps, total } = await getAppsByCategory(category, page, limit)
  const results = apps.map(a => formatAppResult(a))
  const totalPages = Math.ceil(total / limit)

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="flex items-center gap-2">
        <Link href="/r/categories" className="text-sm text-gray-500 hover:text-gray-700">
          Categories
        </Link>
        <span className="text-gray-300">/</span>
        <h1 className="text-2xl font-bold text-gray-900">{category}</h1>
      </div>
      <p className="mt-2 text-sm text-gray-600">{total} app{total !== 1 ? 's' : ''} in this category</p>

      <div className="mt-6 space-y-4">
        {results.map(app => (
          <AppCard key={app.domain} app={app} />
        ))}
      </div>

      {results.length === 0 && (
        <p className="mt-8 text-center text-gray-500">No apps in this category yet.</p>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-8 flex items-center justify-center gap-2">
          {page > 1 && (
            <Link
              href={`/r/categories/${category}?page=${page - 1}`}
              className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50"
            >
              Previous
            </Link>
          )}
          <span className="text-sm text-gray-600">
            Page {page} of {totalPages}
          </span>
          {page < totalPages && (
            <Link
              href={`/r/categories/${category}?page=${page + 1}`}
              className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50"
            >
              Next
            </Link>
          )}
        </div>
      )}
    </div>
  )
}

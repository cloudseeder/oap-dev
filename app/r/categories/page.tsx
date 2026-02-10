import Link from 'next/link'
import { getCategories } from '@/lib/firestore'
import type { Metadata } from 'next'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Categories — OAP Registry',
  description: 'Browse OAP registered apps by category.',
}

export default async function CategoriesPage() {
  const categories = await getCategories()

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900">Categories</h1>
      <p className="mt-2 text-gray-600">Browse registered apps by category.</p>

      <div className="mt-8 grid gap-3 sm:grid-cols-2 md:grid-cols-3">
        {categories.map(cat => (
          <Link
            key={cat.category}
            href={`/r/categories/${cat.category}`}
            className="flex items-center justify-between rounded-lg border border-gray-200 px-5 py-4 hover:shadow-md"
          >
            <span className="font-medium text-gray-900">{cat.category}</span>
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
              {cat.count}
            </span>
          </Link>
        ))}
      </div>

      {categories.length === 0 && (
        <p className="mt-8 text-center text-gray-500">
          No categories yet. <Link href="/r#register" className="text-primary hover:underline">Register the first app.</Link>
        </p>
      )}
    </div>
  )
}

import { NextResponse } from 'next/server'
import { getCategories } from '@/lib/firestore'

export async function GET() {
  const categories = await getCategories()

  return NextResponse.json({
    categories: categories.map(c => ({ category: c.category, count: c.count })),
    total: categories.length,
  })
}

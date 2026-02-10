import { db } from './firebase'
import { FieldValue } from 'firebase-admin/firestore'
import type { AppDocument, CategoryDocument, StatsDocument } from './types'

// === App Operations ===

export async function getApp(domain: string): Promise<AppDocument | null> {
  const doc = await db.collection('apps').doc(domain).get()
  if (!doc.exists) return null
  const data = doc.data() as AppDocument
  if (data.delisted) return null
  return data
}

export async function getAllApps(): Promise<AppDocument[]> {
  const snapshot = await db.collection('apps').where('delisted', '==', false).get()
  return snapshot.docs.map(doc => doc.data() as AppDocument)
}

export async function createApp(domain: string, data: AppDocument): Promise<void> {
  await db.collection('apps').doc(domain).set(data)
  await updateCategoryAggregates(data.categories, domain, 'add')
  await updateStats()
}

export async function updateApp(domain: string, data: Partial<AppDocument>): Promise<void> {
  // If categories changed, rebuild category aggregates
  if (data.categories) {
    const existing = await getApp(domain)
    if (existing) {
      await updateCategoryAggregates(existing.categories, domain, 'remove')
      await updateCategoryAggregates(data.categories, domain, 'add')
    }
  }
  await db.collection('apps').doc(domain).update(data)
  await updateStats()
}

// === Category Operations ===

export async function getAppsByCategory(
  category: string,
  page: number = 1,
  limit: number = 20
): Promise<{ apps: AppDocument[]; total: number }> {
  const catDoc = await db.collection('categories').doc(category.toLowerCase()).get()
  if (!catDoc.exists) return { apps: [], total: 0 }

  const catData = catDoc.data() as CategoryDocument
  const domains = catData.domains || []
  const total = domains.length

  // Paginate the domain list
  const start = (page - 1) * limit
  const pageDomains = domains.slice(start, start + limit)

  if (pageDomains.length === 0) return { apps: [], total }

  // Batch fetch apps
  const refs = pageDomains.map(d => db.collection('apps').doc(d))
  const docs = await db.getAll(...refs)
  const apps = docs
    .filter(d => d.exists)
    .map(d => d.data() as AppDocument)
    .filter(a => !a.delisted)

  return { apps, total }
}

export async function getCategories(): Promise<CategoryDocument[]> {
  const snapshot = await db.collection('categories').orderBy('count', 'desc').get()
  return snapshot.docs.map(doc => doc.data() as CategoryDocument)
}

// === Stats Operations ===

export async function getStats(): Promise<StatsDocument> {
  const doc = await db.collection('stats').doc('global').get()
  if (!doc.exists) {
    return {
      total_apps: 0,
      total_categories: 0,
      verified_healthy: 0,
      registered_today: 0,
      last_updated: new Date().toISOString(),
    }
  }
  return doc.data() as StatsDocument
}

export async function updateStats(): Promise<void> {
  const allApps = await getAllApps()
  const categories = await getCategories()

  const today = new Date().toISOString().split('T')[0]
  const registeredToday = allApps.filter(a => a.registered_at?.startsWith(today)).length

  const stats: StatsDocument = {
    total_apps: allApps.length,
    total_categories: categories.length,
    verified_healthy: allApps.filter(a => a.health_ok).length,
    registered_today: registeredToday,
    last_updated: new Date().toISOString(),
  }

  await db.collection('stats').doc('global').set(stats)
}

// === Category Aggregates ===

export async function updateCategoryAggregates(
  categories: string[],
  domain: string,
  action: 'add' | 'remove'
): Promise<void> {
  const batch = db.batch()

  for (const cat of categories) {
    const catKey = cat.toLowerCase()
    const ref = db.collection('categories').doc(catKey)

    if (action === 'add') {
      batch.set(ref, {
        category: catKey,
        count: FieldValue.increment(1),
        domains: FieldValue.arrayUnion(domain),
      }, { merge: true })
    } else {
      batch.set(ref, {
        count: FieldValue.increment(-1),
        domains: FieldValue.arrayRemove(domain),
      }, { merge: true })
    }
  }

  await batch.commit()
}

/**
 * Seed script — loads example manifests into Firestore.
 * Run: npm run seed
 *
 * Requires FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, FIREBASE_PRIVATE_KEY
 * in .env.local (loaded by tsx via dotenv or manually).
 */

import { readFileSync } from 'fs'
import { join } from 'path'
import { createHash } from 'crypto'

// Load .env.local manually since we're running outside Next.js
import { config } from 'dotenv'
config({ path: join(process.cwd(), '.env.local') })

import { initializeApp, cert } from 'firebase-admin/app'
import { getFirestore, FieldValue } from 'firebase-admin/firestore'
import type { AppDocument, PricingModel } from '../lib/types'

const app = initializeApp({
  credential: cert({
    projectId: process.env.FIREBASE_PROJECT_ID,
    clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
    privateKey: process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n'),
  }),
})

const db = getFirestore(app)

const EXAMPLES = ['xuru.ai', 'provexa.ai', 'mynewscast.com']

function hashManifest(json: Record<string, unknown>): string {
  return 'sha256:' + createHash('sha256').update(JSON.stringify(json)).digest('hex').slice(0, 16)
}

async function seed() {
  console.log('Seeding Firestore with example apps...\n')

  for (const domain of EXAMPLES) {
    const filePath = join(process.cwd(), 'examples', domain, 'oap.json')
    const raw = readFileSync(filePath, 'utf-8')
    const manifest = JSON.parse(raw)

    const now = new Date().toISOString()
    const categories = (manifest.capabilities?.categories || []).map((c: string) => c.toLowerCase())

    const appDoc: AppDocument = {
      domain,
      manifest_url: `https://${domain}/.well-known/oap.json`,
      manifest_json: raw,
      manifest_hash: hashManifest(manifest),
      name: manifest.identity.name,
      tagline: manifest.identity.tagline || '',
      description: manifest.identity.description || '',
      app_url: manifest.identity.url,
      summary: manifest.capabilities?.summary || '',
      solves: manifest.capabilities?.solves || [],
      ideal_for: manifest.capabilities?.ideal_for || [],
      categories,
      differentiators: manifest.capabilities?.differentiators || [],
      pricing_model: (manifest.pricing?.model as PricingModel) || 'free',
      starting_price: manifest.pricing?.starting_price || null,
      builder_name: manifest.builder?.name || '',
      builder_verified_domains: manifest.builder?.verified_domains || [],
      dns_verified: false,
      health_ok: true,
      manifest_valid: true,
      registered_at: now,
      last_verified: now,
      last_fetched: now,
      uptime_checks_passed: 0,
      uptime_checks_total: 0,
      flagged: false,
      flag_reason: null,
      delisted: false,
    }

    // Write app doc (idempotent)
    await db.collection('apps').doc(domain).set(appDoc, { merge: true })
    console.log(`  Written: apps/${domain}`)

    // Update category aggregates
    for (const cat of categories) {
      await db.collection('categories').doc(cat).set({
        category: cat,
        count: FieldValue.increment(0), // Will be recalculated
        domains: FieldValue.arrayUnion(domain),
      }, { merge: true })
    }
  }

  // Recalculate category counts
  console.log('\nRecalculating category counts...')
  const catSnapshot = await db.collection('categories').get()
  for (const doc of catSnapshot.docs) {
    const data = doc.data()
    const domains = data.domains || []
    await doc.ref.update({ count: domains.length })
  }

  // Update stats
  console.log('Updating stats...')
  const allApps = await db.collection('apps').where('delisted', '==', false).get()
  const categories = await db.collection('categories').get()
  const today = new Date().toISOString().split('T')[0]

  await db.collection('stats').doc('global').set({
    total_apps: allApps.size,
    total_categories: categories.size,
    verified_healthy: allApps.docs.filter(d => d.data().health_ok).length,
    registered_today: allApps.docs.filter(d => (d.data().registered_at || '').startsWith(today)).length,
    last_updated: new Date().toISOString(),
  })

  console.log(`\nDone! Seeded ${EXAMPLES.length} apps.`)
  process.exit(0)
}

seed().catch(err => {
  console.error('Seed failed:', err)
  process.exit(1)
})

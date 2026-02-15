import { config } from 'dotenv'
import { join } from 'path'
config({ path: join(process.cwd(), '.env.local') })

import { initializeApp, cert } from 'firebase-admin/app'
import { getFirestore } from 'firebase-admin/firestore'

const domain = process.argv[2]
if (!domain) {
  console.error('Usage: npx tsx scripts/delete-app.ts <domain>')
  process.exit(1)
}

const app = initializeApp({
  credential: cert({
    projectId: process.env.FIREBASE_PROJECT_ID,
    clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
    privateKey: process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n'),
  }),
})
const db = getFirestore(app)

async function run() {
  // Get the app to find its categories
  const appDoc = await db.collection('apps').doc(domain).get()
  if (!appDoc.exists) {
    console.log(`${domain} not found in Firestore`)
    process.exit(0)
  }

  const data = appDoc.data()
  const categories: string[] = data?.categories || []

  // Delete app doc
  await db.collection('apps').doc(domain).delete()
  console.log(`Deleted apps/${domain}`)

  // Update category aggregates
  for (const cat of categories) {
    const ref = db.collection('categories').doc(cat)
    const doc = await ref.get()
    if (doc.exists) {
      const catData = doc.data()
      const domains = (catData?.domains || []).filter((d: string) => d !== domain)
      await ref.update({ domains, count: domains.length })
      console.log(`  Updated category: ${cat}`)
    }
  }

  console.log('Done')
  process.exit(0)
}

run()

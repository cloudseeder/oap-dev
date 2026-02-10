import { initializeApp, getApps, cert, type ServiceAccount } from 'firebase-admin/app'
import { getFirestore, type Firestore } from 'firebase-admin/firestore'

let _db: Firestore | null = null

function getFirebaseApp() {
  const existing = getApps()
  if (existing.length > 0) {
    return existing[0]
  }

  const serviceAccount: ServiceAccount = {
    projectId: process.env.FIREBASE_PROJECT_ID,
    clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
    privateKey: process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n'),
  }

  return initializeApp({
    credential: cert(serviceAccount),
  })
}

export const db: Firestore = new Proxy({} as Firestore, {
  get(_target, prop, receiver) {
    if (!_db) {
      const app = getFirebaseApp()
      _db = getFirestore(app)
    }
    return Reflect.get(_db, prop, receiver)
  },
})

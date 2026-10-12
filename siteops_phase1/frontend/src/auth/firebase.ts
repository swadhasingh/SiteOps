import { initializeApp } from "firebase/app"
import { getAuth } from "firebase/auth"

const required = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

for (const [key, value] of Object.entries(required)) {
  if (!value) throw new Error(`Missing ${key} in frontend .env`)
}

const app = initializeApp({
  ...required,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
})

export const firebaseAuth = getAuth(app)

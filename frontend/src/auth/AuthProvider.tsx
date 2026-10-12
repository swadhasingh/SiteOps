import { onAuthStateChanged, signInWithEmailAndPassword, signOut, type User } from "firebase/auth"
import { createContext, useContext, useEffect, useMemo, useState } from "react"
import { firebaseAuth } from "./firebase"

export type Role = "worker" | "manager" | "admin"

export type SiteOpsProfile = {
  uid: string
  employee_id: string
  role: Role
  site_ids: string[]
  email?: string | null
}

type AuthContextValue = {
  user: User | null
  profile: SiteOpsProfile | null
  loading: boolean
  error: string
  signIn: (email: string, password: string) => Promise<void>
  signOutUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8080"

async function loadProfile(user: User): Promise<SiteOpsProfile> {
  const token = await user.getIdToken()
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const body = await response.json()
  if (!response.ok) throw new Error(body.detail || "Unable to load SiteOps profile")
  return body
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [profile, setProfile] = useState<SiteOpsProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    return onAuthStateChanged(firebaseAuth, async (nextUser) => {
      setUser(nextUser)
      setProfile(null)
      setError("")
      if (!nextUser) {
        setLoading(false)
        return
      }
      try {
        setProfile(await loadProfile(nextUser))
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load SiteOps profile")
        await signOut(firebaseAuth)
      } finally {
        setLoading(false)
      }
    })
  }, [])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    profile,
    loading,
    error,
    signIn: async (email, password) => {
      setError("")
      await signInWithEmailAndPassword(firebaseAuth, email.trim(), password)
    },
    signOutUser: async () => {
      await signOut(firebaseAuth)
      setProfile(null)
    },
  }), [user, profile, loading, error])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error("useAuth must be used inside AuthProvider")
  return value
}

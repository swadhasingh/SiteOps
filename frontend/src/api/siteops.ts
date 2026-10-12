import { getAuth } from "firebase/auth"

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8080"

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const user = getAuth().currentUser
  const token = user ? await user.getIdToken() : null
  const headers = new Headers(init.headers)
  headers.set("Content-Type", "application/json")
  if (token) headers.set("Authorization", `Bearer ${token}`)

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `SiteOps API error (${response.status})`)
  return body as T
}

export type IncidentResponse = {
  incident_id: string
  status: string
  fields: Record<string, unknown>
  routing: Record<string, unknown> | null
  escalation: Record<string, unknown> | null
  is_paused: boolean
  pending_interrupt: Record<string, unknown> | null
  reporter_employee_id: string
  site_id: string
  original_transcript: string
  english_transcript: string
}

export const siteOpsApi = {
  me: () => request<{ uid: string; employee_id: string; role: string; site_ids: string[]; email?: string }>("/auth/me"),
  processIncident: (payload: { incident_id: string; transcript: string; site_id?: string }) =>
    request<IncidentResponse>("/process-incident", { method: "POST", body: JSON.stringify(payload) }),
  clarify: (incident_id: string, answers: Record<string, unknown>) =>
    request<IncidentResponse>("/clarify", { method: "POST", body: JSON.stringify({ incident_id, answers }) }),
  getIncident: (incidentId: string) => request<IncidentResponse>(`/incident/${encodeURIComponent(incidentId)}`),
  getIncidents: (limit = 20) => request<{ incidents: Record<string, unknown>[] }>(`/incidents?limit=${limit}`),
  getPendingReviews: () => request<{ pending: Record<string, unknown>[] }>("/pending-reviews"),
  getDashboardSummary: () => request<Record<string, unknown>>("/dashboard-summary"),
  review: (payload: { incident_id: string; decision: "approve" | "edit" | "reject"; edits?: Record<string, unknown> }) =>
    request<IncidentResponse>("/review", { method: "POST", body: JSON.stringify(payload) }),
  transcribe: async (audio: Blob): Promise<{ transcript: string }> => {
    const user = getAuth().currentUser
    if (!user) throw new Error("You must be signed in")
    const token = await user.getIdToken()
    const form = new FormData()
    form.append("file", audio, "incident.webm")
    const response = await fetch(`${API_BASE_URL}/transcribe`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || `Transcription failed (${response.status})`)
    return body
  },
}

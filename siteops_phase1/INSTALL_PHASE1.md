# SiteOps Phase 1 — Auth + API integration

This bundle adds:

- Firebase Authentication email/password login in the React app.
- FastAPI Firebase ID-token verification.
- Firestore `users/{firebase_uid}` authorization profiles.
- Worker / manager / admin RBAC.
- Server-derived employee IDs; the browser cannot choose the reporter/reviewer identity.
- Site-level authorization for managers.
- Worker `/incidents` access restricted to their own employee ID.
- Manager `/pending-reviews`, `/review`, and `/dashboard-summary` access.
- Separate React API client with bearer tokens.
- Real text incident submission.
- Browser voice recording -> FastAPI `/transcribe` -> transcript -> English translation -> existing extraction/verification workflow.
- Original transcript + English transcript storage.
- Worker names excluded from final incident Firestore documents.
- API-only FastAPI server; the old `static/` mount is removed from the new `main.py`.

## Copy the files

From the SiteOps project root:

```bash
cp /path/to/bundle/backend/src/auth.py backend/src/auth.py
cp /path/to/bundle/backend/src/main.py backend/src/main.py
cp /path/to/bundle/backend/src/langgraph_orchestrator.py backend/src/langgraph_orchestrator.py
cp /path/to/bundle/backend/src/translate.py backend/src/translate.py
cp /path/to/bundle/backend/src/db/firestore_store.py backend/src/db/firestore_store.py
cp /path/to/bundle/backend/requirements.txt backend/requirements.txt
cp /path/to/bundle/backend/.env.example backend/.env.example

cp /path/to/bundle/frontend/src/auth/firebase.ts frontend/src/auth/firebase.ts
cp /path/to/bundle/frontend/src/auth/AuthProvider.tsx frontend/src/auth/AuthProvider.tsx
cp /path/to/bundle/frontend/src/api/siteops.ts frontend/src/api/siteops.ts
cp /path/to/bundle/frontend/src/App.tsx frontend/src/App.tsx
cp /path/to/bundle/frontend/src/main.tsx frontend/src/main.tsx
cp /path/to/bundle/frontend/package.json frontend/package.json
cp /path/to/bundle/frontend/.env.example frontend/.env.example
cp /path/to/bundle/scripts/provision_user.py scripts/provision_user.py
```

Then:

```bash
cd backend
source ../venv/bin/activate
pip install -r requirements.txt
cd ../frontend
pnpm install
```

## Firebase setup

1. Create/select the Firebase project.
2. Enable Authentication -> Email/Password.
3. Create a Web App in Firebase and copy its web config into `frontend/.env`.
4. Create a Firestore collection named `users`.
5. Each document ID must be the Firebase Auth UID and contain:

```json
{
  "employee_id": "EMP-1001",
  "role": "worker",
  "site_ids": ["SITE-MUM-01"],
  "active": true
}
```

Roles are exactly: `worker`, `manager`, `admin`.

## Provision users

With backend credentials configured:

```bash
python scripts/provision_user.py \
  --email worker@example.com \
  --role worker \
  --employee-id EMP-1001 \
  --site SITE-MUM-01
```

A manager can be provisioned similarly with `--role manager`.

## Local env

Frontend:

```bash
VITE_API_BASE_URL=http://localhost:8080
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=...
VITE_FIREBASE_PROJECT_ID=...
VITE_FIREBASE_APP_ID=...
VITE_FIREBASE_MESSAGING_SENDER_ID=...
VITE_FIREBASE_STORAGE_BUCKET=...
```

Backend:

```bash
FIREBASE_PROJECT_ID=...
FIRESTORE_PROJECT_ID=...
FRONTEND_ORIGIN=http://localhost:8443
GROQ_API_KEY=...
```

For local Firebase Admin credentials, set `GOOGLE_APPLICATION_CREDENTIALS` to a service-account JSON path. Do not commit that JSON file.

## Current limitation intentionally left for Phase 2

The existing LangGraph checkpointer is still `MemorySaver`, so an in-progress incident can be lost if the backend process restarts. Before production deployment, replace it with persistent checkpoint storage and move pending-review discovery out of process memory.

"""SiteOps authentication + authorization.

Authentication: Firebase Authentication ID tokens.
Authorization: Firestore users/{firebase_uid} profile.

User profile shape:
  employee_id: str
  role: worker | manager | admin
  site_ids: list[str]
  active: bool

The browser never supplies a trusted employee_id, role, reviewer identity,
or site list. Those values are derived server-side from the authenticated
Firebase UID and its SiteOps profile.
"""

from dataclasses import dataclass
import os

import firebase_admin
from firebase_admin import auth as firebase_auth
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.db.firestore_store import get_user_profile

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    uid: str
    employee_id: str
    role: str
    site_ids: tuple[str, ...]
    email: str | None = None

    @property
    def is_worker(self) -> bool:
        return self.role == "worker"

    @property
    def is_manager(self) -> bool:
        return self.role in {"manager", "admin"}

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _initialize_firebase() -> None:
    if firebase_admin._apps:
        return

    options = {}
    project_id = os.environ.get("FIREBASE_PROJECT_ID") or os.environ.get("FIRESTORE_PROJECT_ID")
    if project_id:
        options["projectId"] = project_id

    # Local development can use GOOGLE_APPLICATION_CREDENTIALS. Production
    # should use the Cloud Run service account rather than a JSON key file.
    firebase_admin.initialize_app(options=options)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Firebase bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        _initialize_firebase()
        decoded = firebase_auth.verify_id_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    uid = decoded.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication token has no user id")

    profile = get_user_profile(uid)
    if not profile:
        raise HTTPException(status_code=403, detail="No SiteOps user profile exists for this account")

    if not profile.get("active", True):
        raise HTTPException(status_code=403, detail="This SiteOps account is disabled")

    role = profile.get("role")
    employee_id = profile.get("employee_id")
    site_ids = profile.get("site_ids") or []
    if role not in {"worker", "manager", "admin"} or not employee_id:
        raise HTTPException(status_code=403, detail="SiteOps user profile is incomplete")

    return CurrentUser(
        uid=uid,
        employee_id=str(employee_id),
        role=role,
        site_ids=tuple(str(site) for site in site_ids),
        email=decoded.get("email"),
    )


def require_manager(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_manager:
        raise HTTPException(status_code=403, detail="Manager access required")
    return user


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

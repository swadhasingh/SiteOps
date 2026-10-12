"""Create/update a SiteOps authorization profile for an existing Firebase Auth user.

This does NOT create a Firebase Auth account. It only writes users/{uid} in Firestore.

Example:
  python scripts/set_siteops_profile.py \
    --uid YOUR_FIREBASE_UID \
    --role manager \
    --employee-id MGR-TEST-001 \
    --site SITE-MUM-01
"""

import argparse
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_ID = "siteops-506520"
KEY_PATH = Path(__file__).resolve().parents[1] / "firestore-key.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", required=True)
    parser.add_argument("--role", choices=["worker", "manager", "admin"], required=True)
    parser.add_argument("--employee-id", required=True)
    parser.add_argument("--site", action="append", dest="sites", required=True)
    args = parser.parse_args()

    if not KEY_PATH.exists():
        raise SystemExit(f"Firebase key not found: {KEY_PATH}")

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(KEY_PATH))
        firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})

    firestore.client().collection("users").document(args.uid).set(
        {
            "employee_id": args.employee_id,
            "role": args.role,
            "site_ids": args.sites,
            "active": True,
        },
        merge=True,
    )

    print("SiteOps profile saved successfully.")
    print(f"Firebase UID: {args.uid}")
    print(f"Employee ID: {args.employee_id}")
    print(f"Role: {args.role}")
    print(f"Sites: {', '.join(args.sites)}")


if __name__ == "__main__":
    main()

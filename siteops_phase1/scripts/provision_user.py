"""Create a SiteOps Firebase Auth account and its Firestore authorization profile.

Usage:
  python scripts/provision_user.py --email worker@example.com --role worker \
    --employee-id EMP-1001 --site SITE-MUM-01

The password is prompted interactively and is never written to Firestore.
"""

import argparse
import getpass

import firebase_admin
from firebase_admin import auth, credentials, firestore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=["worker", "manager", "admin"], required=True)
    parser.add_argument("--employee-id", required=True)
    parser.add_argument("--site", action="append", dest="sites", required=True)
    args = parser.parse_args()

    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    password = getpass.getpass("Temporary password: ")
    user = auth.create_user(email=args.email, password=password)

    firestore.Client().collection("users").document(user.uid).set({
        "employee_id": args.employee_id,
        "role": args.role,
        "site_ids": args.sites,
        "active": True,
    })

    print(f"Created Firebase user: {args.email}")
    print(f"Firebase UID: {user.uid}")
    print(f"Employee ID: {args.employee_id}")
    print(f"Role: {args.role}")
    print(f"Sites: {', '.join(args.sites)}")


if __name__ == "__main__":
    main()

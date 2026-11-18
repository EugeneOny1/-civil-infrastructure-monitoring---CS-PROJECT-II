"""
InfraVision — Safe Administrative Account Email Migration Utility
-----------------------------------------------------------------
Updates the registered email addresses for:
1. Administrator: Eugene.Odhiambo@strathmore.edu
2. Eng. Regina: Eugy.Onyi@gmail.com

Preserves:
- Immutable User _id
- Existing password hashes
- Role authorizations (admin, engineer)
- EBK Professional Engineering accreditations
- All historical reports, reviews, and inspection notebooks

Usage:
  # With explicit MongoDB Atlas connection URI:
  python backend/scripts/update_user_emails.py --mongo-uri "mongodb+srv://<user>:<password>@<cluster>.mongodb.net/civil_infrastructure?retryWrites=true&w=majority"

  # Or using MONGO_URI from backend/.env or environment variable:
  python backend/scripts/update_user_emails.py
"""

import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from pymongo import MongoClient

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

def parse_args():
    parser = argparse.ArgumentParser(description="Update Admin and Engineer Regina account emails safely.")
    parser.add_argument(
        "--mongo-uri",
        type=str,
        default=os.getenv("MONGO_URI"),
        help="MongoDB connection URI (defaults to MONGO_URI from environment or backend/.env)"
    )
    parser.add_argument(
        "--admin-email",
        type=str,
        default="Eugene.Odhiambo@strathmore.edu",
        help="New Administrator email address"
    )
    parser.add_argument(
        "--regina-email",
        type=str,
        default="Eugy.Onyi@gmail.com",
        help="New Engineer Regina email address"
    )
    return parser.parse_args()


def load_env_file():
    env_path = backend_dir / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k not in os.environ and v:
                        os.environ[k] = v


def main():
    load_env_file()
    args = parse_args()

    mongo_uri = args.mongo_uri or os.getenv("MONGO_URI")
    if not mongo_uri:
        print("ERROR: No MongoDB URI provided. Please pass --mongo-uri '<your-mongodb-atlas-uri>' or set MONGO_URI in backend/.env.")
        sys.exit(1)

    admin_email = args.admin_email.strip().lower()
    regina_email = args.regina_email.strip().lower()

    # Redact URI for logging
    redacted_uri = mongo_uri
    if "@" in mongo_uri:
        prefix, rest = mongo_uri.split("://", 1)
        _, host_part = rest.split("@", 1)
        redacted_uri = f"{prefix}://<credentials-hidden>@{host_part}"

    print("==================================================================")
    print("  InfraVision Account Email Migration Utility")
    print("==================================================================")
    print(f"Connecting to MongoDB: {redacted_uri}")

    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=8000)
        # Determine database name
        db_name = os.getenv("DB_NAME", "civil_infrastructure")
        db = client.get_database(db_name)
        # Verify connection
        client.admin.command('ping')
        print("Connected to MongoDB successfully.")
    except Exception as e:
        print(f"ERROR: Could not connect to MongoDB: {e}")
        print("\nIf you are using MongoDB Atlas, ensure your IP address is whitelisted in Atlas Network Access, or run this with --mongo-uri.")
        sys.exit(1)

    users_col = db["users"]
    now_iso = datetime.now(timezone.utc).isoformat()

    # -------------------------------------------------------------
    # 1. Locate and update Administrator account
    # -------------------------------------------------------------
    admin_user = users_col.find_one({"role": "admin"})
    if not admin_user:
        # Fallback search by email keyword or name
        admin_user = users_col.find_one({"email": {"$regex": "admin", "$options": "i"}})

    if not admin_user:
        print("\nWARNING: No existing user document with role='admin' found.")
    else:
        old_admin_email = admin_user.get("email", "<unknown>")
        user_id = admin_user["_id"]
        print(f"\n[1/2] Administrator Account Found:")
        print(f"      User ID:       {user_id}")
        print(f"      Name:          {admin_user.get('name', 'Administrator')}")
        print(f"      Role:          {admin_user.get('role')}")
        print(f"      Current Email: {old_admin_email}")

        # Check collision
        collision = users_col.find_one({"email": admin_email, "_id": {"$ne": user_id}})
        if collision:
            print(f"      ERROR: Email '{admin_email}' is already registered to user ID '{collision['_id']}'. Cannot overwrite.")
        else:
            users_col.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "email": admin_email,
                        "is_email_verified": True,
                        "two_factor_otp": None,
                        "two_factor_attempts": 0,
                        "email_updated_at": now_iso
                    }
                }
            )
            print(f"      >>> SUCCESS: Administrator email updated to: {admin_email}")

    # -------------------------------------------------------------
    # 2. Locate and update Engineer Regina account
    # -------------------------------------------------------------
    regina_user = users_col.find_one({"name": {"$regex": "regina", "$options": "i"}})
    if not regina_user:
        regina_user = users_col.find_one({"email": {"$regex": "regina", "$options": "i"}})
    if not regina_user:
        # Fallback to engineer with kenha.co.ke
        regina_user = users_col.find_one({"role": "engineer", "email": {"$regex": "kenha", "$options": "i"}})

    if not regina_user:
        print("\nWARNING: No existing user document for 'Regina' or role='engineer' found.")
    else:
        old_regina_email = regina_user.get("email", "<unknown>")
        user_id = regina_user["_id"]
        print(f"\n[2/2] Engineer Regina Account Found:")
        print(f"      User ID:       {user_id}")
        print(f"      Name:          {regina_user.get('name', 'Eng. Regina')}")
        print(f"      Role:          {regina_user.get('role')}")
        print(f"      EBK Reg:       {regina_user.get('ebk_registration', 'A-45892 (Civil)')}")
        print(f"      Current Email: {old_regina_email}")

        # Check collision
        collision = users_col.find_one({"email": regina_email, "_id": {"$ne": user_id}})
        if collision:
            print(f"      ERROR: Email '{regina_email}' is already registered to user ID '{collision['_id']}'. Cannot overwrite.")
        else:
            users_col.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "email": regina_email,
                        "is_email_verified": True,
                        "two_factor_otp": None,
                        "two_factor_attempts": 0,
                        "email_updated_at": now_iso
                    }
                }
            )
            print(f"      >>> SUCCESS: Engineer Regina email updated to: {regina_email}")

    print("\n==================================================================")
    print("  Migration Complete!")
    print("  All roles, passwords, and historical data preserved.")
    print("  Next logins will dispatch 2FA OTP codes to the new inboxes.")
    print("==================================================================")

if __name__ == "__main__":
    main()

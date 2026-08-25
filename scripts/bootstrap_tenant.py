#!/usr/bin/env python3
"""
Create a new tenant + its first ApiKey, or mint an additional key for an
existing tenant. Prints the plaintext key exactly once — it is not
recoverable afterward, only its hash is stored.

Usage:
    python scripts/bootstrap_tenant.py --name "Acme Corp" --email acme@example.com
    python scripts/bootstrap_tenant.py --existing-tenant-id <uuid> --role admin --key-name "prod key"
"""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neurowave_engine.core.security import generate_api_key  # noqa: E402
from neurowave_engine.db.database import get_db_session  # noqa: E402
from neurowave_engine.db.models import ApiKey, Role, Tenant  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing-tenant-id", help="Mint a key for an existing tenant instead of creating one")
    parser.add_argument("--name", help="Display name for a new tenant")
    parser.add_argument("--email", help="Email for a new tenant")
    parser.add_argument("--role", choices=[r.value for r in Role], default=Role.DEVELOPER.value)
    parser.add_argument("--key-name", default="bootstrap key", help="Label for this key")
    args = parser.parse_args()

    session = get_db_session()
    try:
        if args.existing_tenant_id:
            tenant = session.query(Tenant).filter(Tenant.id == uuid.UUID(args.existing_tenant_id)).first()
            if not tenant:
                print(f"No tenant found with id {args.existing_tenant_id}", file=sys.stderr)
                sys.exit(1)
        else:
            tenant = Tenant(id=uuid.uuid4(), name=args.name, email=args.email)
            session.add(tenant)
            session.flush()

        raw_key, key_prefix, hashed_secret = generate_api_key()
        api_key = ApiKey(
            id=uuid.uuid4(), tenant_id=tenant.id, key_prefix=key_prefix, hashed_secret=hashed_secret,
            role=Role(args.role), name=args.key_name,
        )
        session.add(api_key)
        session.commit()

        print(f"Tenant (tenant_id): {tenant.id}")
        print(f"API key (shown once, store it now): {raw_key}")
        print(f"Role: {args.role}")
    finally:
        session.close()


if __name__ == "__main__":
    main()

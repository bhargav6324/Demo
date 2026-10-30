"""Explicit database lifecycle commands; never run automatically at server startup."""

import argparse
from datetime import date, datetime, time, timezone

from pydantic import ValidationError

from app.core.config import Settings
from app.core.database import Database
from app.models import Base
from app.services.seed import DEFAULT_AS_OF, seed_database


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override LIBRARY_DATABASE_URL for this command")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create missing tables without changing existing data")
    seed = commands.add_parser("seed", help="Initialize and seed an empty local demo database")
    seed.add_argument("--as-of", type=date.fromisoformat, default=DEFAULT_AS_OF.date(), help="Fixed UTC scenario date, e.g. 2026-10-30")
    reset = commands.add_parser("reset", help="Drop and recreate application tables; does not seed")
    reset.add_argument("--confirm-reset", action="store_true", help="Required acknowledgement of deleting application data")
    args = parser.parse_args(argv)
    try:
        settings = Settings()
    except ValidationError:
        parser.error("Invalid environment configuration; verify required settings")
    if args.command in {"seed", "reset"} and settings.environment == "production":
        parser.error("Demo seed/reset commands are disabled in production")
    if args.command == "reset" and not args.confirm_reset:
        parser.error("Reset deletes application data; pass --confirm-reset explicitly")
    database = Database(args.database_url or settings.database_url)
    try:
        if args.command == "reset":
            Base.metadata.drop_all(database.engine)
        database.initialize()
        if args.command == "seed":
            anchor = datetime.combine(args.as_of, time.min, timezone.utc)
            created = seed_database(database, anchor)
            print("Synthetic demo data seeded" if created else "Seed already present; no data changed")
        else:
            print("Application tables reset (empty)" if args.command == "reset" else "Application tables initialized")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Database command failed: {exc}\n")
    finally:
        database.dispose()


if __name__ == "__main__":
    main()

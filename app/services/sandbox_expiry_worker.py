"""One-shot command for scheduled sandbox expiry reconciliation.

Run periodically from a scheduler, for example:
    python -m app.services.sandbox_expiry_worker --batch-size 100
"""

import argparse

from app.db.session import SessionLocal
from app.services.sandbox_lifecycle import expire_due_sandboxes


def main() -> int:
    """Reconcile one bounded batch and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 1000:
        parser.error("--batch-size must be between 1 and 1000")

    with SessionLocal() as db:
        expired_count = expire_due_sandboxes(db, batch_size=args.batch_size)
    print(f"Expired {expired_count} sandbox record(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

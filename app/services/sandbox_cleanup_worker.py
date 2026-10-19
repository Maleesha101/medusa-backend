"""One-shot command to retry provider cleanup for terminal sandboxes.

Run with:
    python -m app.services.sandbox_cleanup_worker --batch-size 50

The default controller intentionally fails closed. A real provider must be
explicitly wired by reviewed deployment code before cleanup can succeed.
"""

import argparse

from app.db.session import SessionLocal
from app.services.sandbox_cleanup import reconcile_provider_cleanup


def main() -> int:
    """Process one bounded batch and report cleanup outcomes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 500:
        parser.error("--batch-size must be between 1 and 500")

    with SessionLocal() as db:
        result = reconcile_provider_cleanup(db, batch_size=args.batch_size)
    print(
        "Provider cleanup: "
        f"processed={result['processed']} cleaned={result['cleaned']} failed={result['failed']}"
    )
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

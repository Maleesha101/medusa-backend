"""One-shot scheduled worker for operational alert evaluation and email delivery.

Run periodically:
    python -m app.services.operational_alert_worker --batch-size 100
"""

import argparse

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.operational_alerts import (
    dispatch_operational_alert_notifications,
    synchronize_operational_alerts,
)


def main() -> int:
    """Evaluate alert state and dispatch a bounded batch of notification intents."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100:
        parser.error("--batch-size must be between 1 and 100")

    with SessionLocal() as db:
        transitions = synchronize_operational_alerts(db, get_settings())
        delivery = dispatch_operational_alert_notifications(db, args.batch_size)
    print(
        "Operational alerts: "
        f"{transitions['created']} created, "
        f"{transitions['escalated']} escalated, "
        f"{transitions['resolved']} resolved; "
        f"{delivery['sent']} sent, "
        f"{delivery['retry_scheduled']} retry scheduled, "
        f"{delivery['exhausted']} exhausted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

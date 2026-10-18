from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.sandbox_instance import SandboxInstance


def test_sandbox_state_check_constraint(session_factory) -> None:
    with session_factory() as db:
        instance = SandboxInstance(
            challenge_id=999,
            owner_user_id=999,
            state="arbitrary",
            expires_at=datetime.now(UTC),
        )
        db.add(instance)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

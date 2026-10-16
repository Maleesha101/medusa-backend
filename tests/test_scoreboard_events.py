import json

from redis.exceptions import ConnectionError as RedisConnectionError

from app.services import scoreboard_events


class FakeRedis:
    def __init__(self, failure=None):
        self.failure = failure
        self.published = []
        self.closed = False

    def publish(self, channel, payload):
        if self.failure:
            raise self.failure
        self.published.append((channel, payload))

    def close(self):
        self.closed = True


def test_publish_scoreboard_update_emits_non_sensitive_event(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(scoreboard_events.Redis, "from_url", lambda *args, **kwargs: client)

    scoreboard_events.publish_scoreboard_update(competition_id=12, submission_id=99)

    assert client.closed
    assert len(client.published) == 1
    channel, payload = client.published[0]
    assert channel == "medusa:scoreboard:competition:12"
    assert json.loads(payload) == {
        "type": "scoreboard.updated",
        "competition_id": 12,
        "submission_id": 99,
    }
    assert "flag" not in payload


def test_publish_scoreboard_update_does_not_fail_committed_submission(monkeypatch):
    client = FakeRedis(failure=RedisConnectionError("redis unavailable"))
    monkeypatch.setattr(scoreboard_events.Redis, "from_url", lambda *args, **kwargs: client)

    # Publishing is best-effort: a Redis outage must not turn a committed solve
    # into a failed submission response.
    scoreboard_events.publish_scoreboard_update(competition_id=12, submission_id=99)

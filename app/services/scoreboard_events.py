"""Redis Pub/Sub notifications for scoreboard changes."""

import json
import logging

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)
SCOREBOARD_CHANNEL_PREFIX = "medusa:scoreboard:competition:"


def publish_scoreboard_update(competition_id: int, submission_id: int) -> None:
    """Publish a non-sensitive invalidation event after a solve is committed.

    Publishing is best-effort: a committed submission must not be reported as failed
    merely because live notifications are temporarily unavailable. Clients can always
    recover the authoritative state from the REST scoreboard endpoint.
    """
    channel = f"{SCOREBOARD_CHANNEL_PREFIX}{competition_id}"
    payload = json.dumps(
        {
            "type": "scoreboard.updated",
            "competition_id": competition_id,
            "submission_id": submission_id,
        }
    )
    try:
        client = Redis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            client.publish(channel, payload)
        finally:
            client.close()
    except RedisError:
        logger.exception(
            "Could not publish scoreboard update for competition_id=%s",
            competition_id,
        )


def create_async_redis_client() -> AsyncRedis:
    """Create an async Redis client for WebSocket subscriptions."""
    return AsyncRedis.from_url(get_settings().redis_url, decode_responses=True)

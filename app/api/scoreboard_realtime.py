"""Public WebSocket stream for competition scoreboard invalidation events."""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.competition import Competition
from app.services.scoreboard_events import (
    SCOREBOARD_CHANNEL_PREFIX,
    create_async_redis_client,
)

router = APIRouter(tags=["scoreboard-realtime"])
PUBLIC_COMPETITION_STATUSES = {"published", "active", "completed"}


@router.websocket("/competitions/{competition_id}/scoreboard/ws")
async def scoreboard_updates(websocket: WebSocket, competition_id: int) -> None:
    """Stream scoreboard invalidation events for a public competition.

    Events contain no flags or team/member data. Clients should refetch the REST
    scoreboard after receiving an event; REST remains the authoritative source.
    """
    db: Session = SessionLocal()
    try:
        competition = db.get(Competition, competition_id)
        is_public = (
            competition is not None
            and competition.is_public
            and competition.status in PUBLIC_COMPETITION_STATUSES
        )
    finally:
        db.close()

    if not is_public:
        await websocket.close(code=1008, reason="Competition not found")
        return

    await websocket.accept()
    redis_client = create_async_redis_client()
    pubsub = redis_client.pubsub()
    receive_task: asyncio.Task | None = None
    try:
        await pubsub.subscribe(f"{SCOREBOARD_CHANNEL_PREFIX}{competition_id}")
        receive_task = asyncio.create_task(websocket.receive_text())
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message and message.get("type") == "message":
                # Only forward the known event shape, never arbitrary Redis payloads.
                payload = json.loads(message["data"])
                if (
                    payload.get("type") == "scoreboard.updated"
                    and payload.get("competition_id") == competition_id
                ):
                    await websocket.send_json(payload)

            if receive_task.done():
                receive_task.result()  # raises WebSocketDisconnect on client disconnect
                receive_task = asyncio.create_task(websocket.receive_text())
            else:
                await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    except (RedisError, ValueError, TypeError):
        # End the stream safely; clients can reconnect and refetch REST state.
        await websocket.close(code=1011, reason="Realtime updates temporarily unavailable")
    finally:
        if receive_task is not None and not receive_task.done():
            receive_task.cancel()
        try:
            await pubsub.unsubscribe(f"{SCOREBOARD_CHANNEL_PREFIX}{competition_id}")
            await pubsub.aclose()
        finally:
            await redis_client.aclose()

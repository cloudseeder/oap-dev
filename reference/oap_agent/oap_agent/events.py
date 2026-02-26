"""In-memory event bus for SSE broadcasting."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

MAX_SUBSCRIBERS = 50


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._shutdown = asyncio.Event()

    def subscribe(self) -> tuple[str, asyncio.Queue]:
        """Register a new subscriber. Returns (subscriber_id, queue).

        Raises RuntimeError if too many subscribers are connected.
        """
        if len(self._subscribers) >= MAX_SUBSCRIBERS:
            raise RuntimeError("Too many SSE subscribers")
        sub_id = uuid.uuid4().hex[:8]
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[sub_id] = queue
        return sub_id, queue

    def unsubscribe(self, subscriber_id: str) -> None:
        """Remove a subscriber."""
        self._subscribers.pop(subscriber_id, None)

    async def publish(self, event_type: str, data: Any) -> None:
        """Put an event onto all subscriber queues. Drops if queue is full."""
        event = {"event": event_type, "data": data}
        for queue in list(self._subscribers.values()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    @property
    def shutting_down(self) -> bool:
        return self._shutdown.is_set()

    def shutdown(self) -> None:
        """Signal all SSE streams to stop."""
        self._shutdown.set()
        # Push a sentinel so streams blocked on queue.get() wake up
        for queue in list(self._subscribers.values()):
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

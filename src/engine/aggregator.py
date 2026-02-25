from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Awaitable

from src.models.whale_order import WhaleOrder
from src.storage.database import Database
from src.engine.alert_rules import AlertEngine

logger = logging.getLogger(__name__)

PushCallback = Callable[[WhaleOrder, list[str]], Awaitable[None]]


class Aggregator:
    """
    Central aggregation hub.
    Receives orders from all collectors, deduplicates, stores,
    evaluates alert rules, and dispatches push notifications.
    """

    def __init__(self, db: Database, alert_engine: AlertEngine, push_callback: PushCallback) -> None:
        self.db = db
        self.alert_engine = alert_engine
        self._push_callback = push_callback
        self._seen_ids: set[str] = set()
        self._stats = {"received": 0, "new": 0, "alerted": 0}

    async def ingest(self, orders: list[WhaleOrder]) -> None:
        for order in orders:
            self._stats["received"] += 1

            if order.id in self._seen_ids:
                continue

            is_new = await self.db.insert_order(order)
            if not is_new:
                self._seen_ids.add(order.id)
                continue

            self._seen_ids.add(order.id)
            self._stats["new"] += 1

            # keep memory bounded
            if len(self._seen_ids) > 50_000:
                self._seen_ids = set(list(self._seen_ids)[-25_000:])

            matched_rules = self.alert_engine.evaluate(order)
            if matched_rules:
                self._stats["alerted"] += 1
                logger.info("ALERT %s | %s", matched_rules, order.summary())
                try:
                    await self._push_callback(order, matched_rules)
                except Exception as e:
                    logger.error("Push callback failed: %s", e)

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

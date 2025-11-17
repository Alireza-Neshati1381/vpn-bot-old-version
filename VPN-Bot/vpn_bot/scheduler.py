"""Background scheduler that checks for expired orders."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from .telegram import TelegramAPIError, TelegramBot
from .xui_api import XUIClient, XUIError

LOGGER = logging.getLogger(__name__)


class ExpirationWorker(threading.Thread):
    """Simple polling worker that removes expired VPN accounts."""

    def __init__(
        self,
        *,
        interval: float,
        fetch_expired: Callable[[], list],
        mark_expired: Callable[[int], None],
        get_order_details: Callable[[int], dict],
        telegram_bot: TelegramBot,
        make_client: Callable[[int], XUIClient],
    ) -> None:
        super().__init__(daemon=True)
        self.interval = interval
        self.fetch_expired = fetch_expired
        self.mark_expired = mark_expired
        self.get_order_details = get_order_details
        self.telegram_bot = telegram_bot
        self.make_client = make_client
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # pragma: no cover - background thread
        LOGGER.info("expiration worker started")
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                LOGGER.exception("expiration worker tick failed: %s", exc)
            self._stop.wait(self.interval)
        LOGGER.info("expiration worker stopped")

    def _tick(self) -> None:
        expired_orders = self.fetch_expired()
        if not expired_orders:
            return
        LOGGER.info("found %s expired orders", len(expired_orders))
        for order in expired_orders:
            order_id = order["id"]
            details = self.get_order_details(order_id)
            try:
                if details.get("config_id") and details.get("inbound_id"):
                    client = self.make_client(details["server_id"])
                    client.remove_client(details["inbound_id"], details["config_id"])
            except (XUIError, KeyError) as exc:
                LOGGER.warning("failed to remove config for order %s: %s", order_id, exc)
            self.mark_expired(order_id)
            self._notify(details)

    def _notify(self, details: dict) -> None:
        user_id = details.get("telegram_id")
        if not user_id:
            return
        message = "Your VPN configuration expired and has been removed."
        try:
            self.telegram_bot.send_message(int(user_id), message)
        except TelegramAPIError as exc:
            LOGGER.warning("could not send expiration message: %s", exc)

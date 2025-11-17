"""Application entrypoint.

Running ``python main.py`` starts the Telegram bot and the background
expiration worker. The implementation intentionally avoids heavy
frameworks so it can run on systems without additional build tools.
"""
from __future__ import annotations

import logging
import signal
import sys
import threading
from typing import Optional

from vpn_bot.config import load_settings
from vpn_bot.handlers import BotApp
from vpn_bot.scheduler import ExpirationWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
LOGGER = logging.getLogger(__name__)


def main() -> int:
    settings = load_settings()
    app = BotApp(settings)

    worker = ExpirationWorker(
        interval=60,
        fetch_expired=app.fetch_expired_orders,
        mark_expired=app.mark_expired,
        get_order_details=app.get_order_details,
        telegram_bot=app.bot,
        make_client=app.make_client,
    )
    worker.start()

    stop_event = threading.Event()

    def handle_stop(signum: int, frame) -> None:  # pragma: no cover - signal handler
        LOGGER.info("received stop signal %s", signum)
        stop_event.set()
        worker.stop()

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    try:
        app.run()
    except KeyboardInterrupt:  # pragma: no cover - interactive use
        LOGGER.info("exiting")
    finally:
        worker.stop()
        worker.join(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Small wrapper around the Telegram Bot API using :mod:`requests`."""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional

import requests

LOGGER = logging.getLogger(__name__)


class TelegramAPIError(RuntimeError):
    """Error raised when Telegram returns a failure."""


class TelegramBot:
    """Calls the HTTP Bot API directly.

    Only a handful of methods are implemented because the project only
    needs sending text, sending photos and acknowledging callback queries.
    """

    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}/"

    def _request(self, method: str, *, params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = requests.post(self.base_url + method, params=params, data=data, timeout=20)
        payload = response.json()
        if not payload.get("ok"):
            raise TelegramAPIError(str(payload))
        return payload["result"]

    def get_updates(self, *, offset: Optional[int] = None, timeout: int = 25) -> Iterable[Dict[str, Any]]:
        params: Dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        response = requests.get(self.base_url + "getUpdates", params=params, timeout=timeout + 5)
        data = response.json()
        if not data.get("ok"):
            raise TelegramAPIError(str(data))
        return data.get("result", [])

    def send_message(self, chat_id: int, text: str, *, reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            params["reply_markup"] = json_dumps(reply_markup)
        return self._request("sendMessage", params=params)

    def send_photo(
        self,
        chat_id: int,
        file_id: str,
        *,
        caption: Optional[str] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"chat_id": chat_id, "photo": file_id}
        if caption:
            params["caption"] = caption
        if reply_markup is not None:
            params["reply_markup"] = json_dumps(reply_markup)
        return self._request("sendPhoto", params=params)

    def answer_callback_query(self, callback_query_id: str, *, text: Optional[str] = None) -> None:
        params: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text
        self._request("answerCallbackQuery", params=params)


def json_dumps(value: Dict[str, Any]) -> str:
    """A minimal JSON encoder that avoids importing :mod:`json` repeatedly."""

    import json

    return json.dumps(value, separators=(",", ":"))

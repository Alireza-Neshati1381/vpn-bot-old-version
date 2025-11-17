"""Minimal client for the 3x-ui (Xray) panel API.

The implementation mirrors the reference script provided by the customer
which relies on HTTP cookies instead of bearer tokens and uses the
``addClient`` style endpoints. 3x-ui expects those exact paths and a JSON
stringified ``settings`` payload, therefore the earlier token based
implementation failed to authenticate correctly on panels that live under
nested paths (e.g. ``https://host:port/testpatch/``).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin
from uuid import uuid4

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

SUCCESS_STATUSES = {"success", True}

LOGGER = logging.getLogger(__name__)


class XUIError(RuntimeError):
    """Raised when the panel returns an unexpected error."""


class XUIClient:
    """Very small wrapper around the JSON API."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        verify_ssl: bool = False,
        timeout: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.session = requests.Session()
        self._authenticated = False
        if not verify_ssl:
            urllib3.disable_warnings(InsecureRequestWarning)

    def _build_url(self, path: str) -> str:
        """Return an absolute panel URL while preserving nested paths."""

        return urljoin(self.base_url, path)

    def _login(self) -> None:
        """Authenticate and populate the session cookies."""

        response = self.session.post(
            self._build_url("login/"),
            json={"username": self.username, "password": self.password},
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") not in SUCCESS_STATUSES and data.get("success") not in SUCCESS_STATUSES:
            raise XUIError(f"login failed: {data}")
        self._authenticated = True

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        retry: bool = True,
    ) -> Dict[str, Any]:
        if not self._authenticated:
            self._login()
        url = self._build_url(path)
        response = self.session.request(
            method,
            url,
            json=json_body,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        if response.status_code == 401 and retry:
            # Session expired, obtain fresh cookies and retry once.
            LOGGER.info("session expired, re-authenticating")
            self._authenticated = False
            self._login()
            return self._request(method, path, json_body=json_body, retry=False)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") not in SUCCESS_STATUSES and payload.get("success") not in SUCCESS_STATUSES:
            raise XUIError(f"API call failed: {payload}")
        return payload

    def create_client(self, inbound_id: int, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a client on the provided inbound using ``addClient`` endpoint."""

        uid = str(
            config.get("id")
            or config.get("uuid")
            or config.get("client_id")
            or config.get("email")
            or uuid4()
        )
        email = str(config.get("email") or uid)
        expiry_time = int(config.get("expireTime") or config.get("expiryTime") or 0)
        if expiry_time and expiry_time < 10**12:
            # API expects milliseconds.
            expiry_time *= 1000
        total_bytes = int(config.get("totalGB") or config.get("total_bytes") or 0)
        limit_ip = int(config.get("limitIp") or config.get("concurrent") or 1)
        client_entry = {
            "id": uid,
            "flow": config.get("flow", ""),
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expiry_time,
            "enable": True,
            "tgId": str(config.get("tgId") or ""),
            "subId": str(config.get("subId") or uid[:10]),
            "reset": int(config.get("reset") or 0),
        }
        payload = {
            "id": int(inbound_id),
            "settings": json.dumps({"clients": [client_entry]}),
        }
        response = self._request("POST", "panel/api/inbounds/addClient", json_body=payload)
        response.setdefault("client", client_entry)
        return response

    def remove_client(self, inbound_id: int, client_id: str) -> Dict[str, Any]:
        """Remove a client identified by ``client_id`` using ``delClient``."""

        payload = {"id": int(inbound_id), "clientIds": [client_id]}
        return self._request("POST", "panel/api/inbounds/delClient", json_body=payload)

    def get_client_traffic(self, inbound_id: int, client_id: str) -> Dict[str, Any]:
        """Return the traffic statistics for a client."""

        path = f"panel/api/inbounds/getClientTraffics/{int(inbound_id)}?clientId={client_id}"
        return self._request("GET", path)

    def get_inbound(self, inbound_id: int) -> Dict[str, Any]:
        """Fetch inbound details used to build configuration links."""

        return self._request("GET", f"panel/api/inbounds/get/{int(inbound_id)}")

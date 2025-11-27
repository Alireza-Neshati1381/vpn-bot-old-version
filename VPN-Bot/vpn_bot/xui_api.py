"""Minimal client for the 3x-ui (Xray) panel API.

The implementation mirrors the reference script provided by the customer
which relies on HTTP cookies instead of bearer tokens and uses the
``addClient`` style endpoints. 3x-ui expects those exact paths and a JSON
stringified ``settings`` payload, therefore the earlier token based
implementation failed to authenticate correctly on panels that live under
nested paths (e.g. ``https://host:port/testpatch/``).

This implementation incorporates best practices from AlamorVPN_Bot for
handling SSL issues, cookie detection, and API compatibility across
different 3x-ui panel versions.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from uuid import uuid4

import requests
import urllib3
from requests.exceptions import ConnectionError, SSLError
from urllib3.exceptions import InsecureRequestWarning

SUCCESS_STATUSES = {"success", True}

LOGGER = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF = 1.0  # seconds


class XUIError(RuntimeError):
    """Raised when the panel returns an unexpected error."""


class XUIConnectionError(XUIError):
    """Raised when a connection to the panel fails."""


class XUIClient:
    """Very small wrapper around the JSON API.

    This client supports various 3x-ui panel versions and configurations:
    - Both JSON and form data login methods (tries both for compatibility)
    - Cookie-agnostic session detection (works with any cookie name)
    - Automatic re-authentication on session expiry
    - Better SSL/TLS error handling with helpful hints
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        verify_ssl: bool = False,
        timeout: int = 20,
    ) -> None:
        # Store original URL with trailing slash
        self.base_url = base_url.rstrip("/") + "/"
        # Check if URL ends with /login
        self._url_ends_with_login = self._check_url_ends_with_login(base_url)
        # Login URL is always the provided URL (it IS the login page)
        self._login_url = self.base_url
        # API base URL strips /login suffix if present
        self._api_base_url = self._compute_api_base_url(self.base_url, self._url_ends_with_login)
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.session = requests.Session()
        # Set Accept header for better compatibility with different panel versions
        self.session.headers.update({"Accept": "application/json"})
        self._authenticated = False
        if not verify_ssl:
            urllib3.disable_warnings(InsecureRequestWarning)

    @staticmethod
    def _check_url_ends_with_login(url: str) -> bool:
        """Check if URL ends with /login (case-insensitive)."""
        return url.rstrip("/").lower().endswith("/login")

    @staticmethod
    def _compute_api_base_url(base_url: str, url_ends_with_login: bool) -> str:
        """Compute the API base URL.

        If URL ends with /login, strip /login for API calls.
        If URL doesn't end with /login, use it as-is for API calls.
        """
        if url_ends_with_login:
            # Strip /login/ from the end
            url = base_url.rstrip("/")
            if url.lower().endswith("/login"):
                url = url[:-6]  # Remove '/login' (6 characters)
            return url.rstrip("/") + "/"
        return base_url

    def _build_url(self, path: str) -> str:
        """Return an absolute panel URL while preserving nested paths."""

        return urljoin(self._api_base_url, path)

    @staticmethod
    def _is_ssl_error(exc: Exception) -> bool:
        """Check if the exception is an SSL/TLS related error."""
        if isinstance(exc, SSLError):
            return True
        error_str = str(exc)
        return "SSL" in error_str or "ssl" in error_str

    def _handle_connection_error(self, exc: Exception) -> None:
        """Convert connection errors to user-friendly XUIConnectionError."""
        error_str = str(exc)
        base_msg = f"Failed to connect to panel at {self.base_url}"

        if self._is_ssl_error(exc):
            # SSL/TLS handshake issue
            hint = (
                "This usually means the panel URL uses https:// but the server "
                "expects http://, or the server has SSL/TLS misconfiguration. "
                "Try changing the server URL from https:// to http://"
            )
            raise XUIConnectionError(f"{base_msg}: SSL/TLS error. {hint}") from exc

        if "Connection refused" in error_str:
            hint = "Make sure the panel is running and the port is correct."
            raise XUIConnectionError(f"{base_msg}: Connection refused. {hint}") from exc

        if "timed out" in error_str.lower() or "timeout" in error_str.lower():
            hint = "The server took too long to respond. Check network connectivity."
            raise XUIConnectionError(f"{base_msg}: Connection timed out. {hint}") from exc

        # Generic connection error
        raise XUIConnectionError(f"{base_msg}: {exc}") from exc

    def _try_login_request(self, use_json: bool = True) -> Optional[Dict[str, Any]]:
        """Attempt a single login request.

        Args:
            use_json: If True, send credentials as JSON. If False, send as form data.

        Returns:
            Response data dict if successful, None if failed.
        """
        credentials = {"username": self.username, "password": self.password}
        try:
            if use_json:
                response = self.session.post(
                    self._login_url,
                    json=credentials,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
            else:
                # Some 3x-ui versions expect form data instead of JSON
                response = self.session.post(
                    self._login_url,
                    data=credentials,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
            response.raise_for_status()
            return response.json()
        except json.JSONDecodeError as exc:
            # Log partial response for debugging but don't fail yet
            response_text = response.text[:200] if response else "No response"
            LOGGER.warning(
                "Failed to decode JSON response from login: %s. Response: %s",
                exc,
                response_text,
            )
            return None
        except (SSLError, ConnectionError):
            raise  # Re-raise for retry handling
        except requests.exceptions.RequestException as exc:
            LOGGER.warning("Login request failed: %s", exc)
            return None

    def _validate_login_response(self, data: Optional[Dict[str, Any]]) -> bool:
        """Validate the login response and check for session cookies.

        Uses cookie-agnostic detection: if any cookie is set by the panel,
        we consider the login successful. This provides better compatibility
        across different 3x-ui versions that may use different cookie names.

        Args:
            data: Response data from login attempt.

        Returns:
            True if login was successful, False otherwise.
        """
        if not data:
            return False

        # Check if API reports success
        api_success = data.get("status") in SUCCESS_STATUSES or data.get("success") in SUCCESS_STATUSES

        if not api_success:
            return False

        # Cookie-agnostic session detection (from AlamorVPN_Bot)
        # If ANY cookie is set, we consider it a successful session
        if self.session.cookies:
            cookie_names = "; ".join(c.name for c in self.session.cookies)
            LOGGER.debug("Login successful. Session cookies set: %s", cookie_names)
            return True

        # Some panels may return success with token in response body instead
        if data.get("obj") is not None:
            LOGGER.debug("Login successful. Token returned in response body.")
            return True

        LOGGER.warning(
            "Login API returned success but no session cookie or token was found. "
            "The panel may have an unusual authentication mechanism."
        )
        # Still consider it successful if the API said so
        return True

    def _login(self) -> None:
        """Authenticate and populate the session cookies.

        Tries both JSON and form data login methods for better compatibility
        with different 3x-ui panel versions.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(MAX_RETRIES):
            try:
                # Try JSON first (most common)
                data = self._try_login_request(use_json=True)
                if self._validate_login_response(data):
                    self._authenticated = True
                    LOGGER.info("Successfully logged in to panel using JSON")
                    return

                # Fall back to form data (some panels require this)
                LOGGER.debug("JSON login failed or incomplete, trying form data")
                data = self._try_login_request(use_json=False)
                if self._validate_login_response(data):
                    self._authenticated = True
                    LOGGER.info("Successfully logged in to panel using form data")
                    return

                # Both methods failed
                raise XUIError(f"Login failed: {data}")

            except (SSLError, ConnectionError) as exc:
                last_exc = exc
                hint = ""
                if self._is_ssl_error(exc) and attempt == MAX_RETRIES - 1:
                    hint = " Hint: Try changing the server URL from https:// to http://"
                LOGGER.warning(
                    "connection attempt %d/%d failed: %s%s",
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                    hint,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF * (attempt + 1))
                continue

        # All retries exhausted
        if last_exc is not None:
            self._handle_connection_error(last_exc)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        retry: bool = True,
    ) -> Dict[str, Any]:
        """Make an authenticated API request to the panel.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path relative to base URL
            json_body: Optional JSON payload for POST requests
            retry: Whether to retry on authentication failure

        Returns:
            Response data as dictionary

        Raises:
            XUIError: If the API returns an error
            XUIConnectionError: If connection to panel fails
        """
        if not self._authenticated:
            self._login()
        url = self._build_url(path)
        last_exc: Optional[Exception] = None
        response: Optional[requests.Response] = None

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(
                    method,
                    url,
                    json=json_body,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
                # Handle authentication errors (401 or 403)
                # Some panels return 403 instead of 401 for session expiry
                if response.status_code in (401, 403) and retry:
                    LOGGER.debug(
                        "Session expired (status %d), re-authenticating",
                        response.status_code,
                    )
                    self._authenticated = False
                    self._login()
                    return self._request(method, path, json_body=json_body, retry=False)

                response.raise_for_status()

                # Handle empty responses
                if not response.text:
                    LOGGER.debug("Empty response from %s", path)
                    return {"success": True}

                try:
                    payload = response.json()
                except json.JSONDecodeError as exc:
                    # Log partial response for debugging
                    response_preview = response.text[:200] if response.text else "empty"
                    LOGGER.error(
                        "Failed to decode JSON from %s: %s. Response preview: %s",
                        path,
                        exc,
                        response_preview,
                    )
                    raise XUIError(f"Invalid JSON response from panel: {response_preview}") from exc

                if payload.get("status") not in SUCCESS_STATUSES and payload.get("success") not in SUCCESS_STATUSES:
                    raise XUIError(f"API call failed: {payload}")
                return payload

            except (SSLError, ConnectionError) as exc:
                last_exc = exc
                hint = ""
                if self._is_ssl_error(exc) and attempt == MAX_RETRIES - 1:
                    hint = " Hint: Try changing the server URL from https:// to http://"
                LOGGER.warning(
                    "request attempt %d/%d failed: %s%s",
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                    hint,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF * (attempt + 1))
                continue

        # All retries exhausted
        if last_exc is not None:
            self._handle_connection_error(last_exc)
        # Unreachable: _handle_connection_error always raises, but this satisfies type checkers
        raise XUIConnectionError(f"Failed to connect to panel at {self.base_url}")  # pragma: no cover

    def create_client(self, inbound_id: int, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a client on the provided inbound using ``addClient`` endpoint."""
        # Extract client ID from various possible config keys
        uid = (
            config.get("id")
            or config.get("uuid")
            or config.get("client_id")
            or config.get("email")
            or str(uuid4())
        )
        uid = str(uid)
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

    def list_inbounds(self) -> List[Dict[str, Any]]:
        """List all inbounds configured on the panel.

        Returns:
            List of inbound configurations.
        """
        response = self._request("GET", "panel/api/inbounds/list")
        inbounds = response.get("obj", [])
        if isinstance(inbounds, list):
            return inbounds
        return []

    def delete_client_by_path(self, inbound_id: int, client_id: str) -> Dict[str, Any]:
        """Remove a client using the path-based endpoint format.

        Some 3x-ui panel versions use this format instead of the JSON body format.
        This is an alternative to remove_client() for compatibility.

        Args:
            inbound_id: The inbound ID containing the client
            client_id: The client UUID/ID to delete

        Returns:
            API response
        """
        path = f"panel/api/inbounds/{int(inbound_id)}/delClient/{client_id}"
        return self._request("POST", path)

    def get_client_traffic_by_id(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get traffic statistics for a client by their UUID.

        This is an alternative to get_client_traffic() that doesn't require
        knowing the inbound ID.

        Args:
            client_id: The client UUID/ID

        Returns:
            Traffic statistics or None if not found
        """
        try:
            response = self._request("GET", f"panel/api/inbounds/getClientTrafficsById/{client_id}")
            obj = response.get("obj")
            if isinstance(obj, list) and len(obj) > 0:
                return obj[0]
            elif isinstance(obj, dict):
                return obj
            return None
        except XUIError:
            return None

    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed client information including traffic data.

        Searches through all inbounds to find the client by UUID or email.

        Args:
            client_id: The client UUID or email

        Returns:
            Client info dict or None if not found
        """
        inbounds = self.list_inbounds()
        if not inbounds:
            return None

        for inbound in inbounds:
            try:
                settings = inbound.get("settings")
                if isinstance(settings, str):
                    settings = json.loads(settings)

                clients = settings.get("clients", []) if isinstance(settings, dict) else []

                for client in clients:
                    if not isinstance(client, dict):
                        continue
                    if client.get("id") == client_id or client.get("email") == client_id:
                        # Return a copy to avoid modifying the original inbound data
                        result = client.copy()
                        # Try to add traffic info
                        traffic = self.get_client_traffic_by_id(client_id)
                        if traffic:
                            result.update(traffic)
                        return result
            except (json.JSONDecodeError, TypeError) as exc:
                LOGGER.warning(
                    "Error parsing settings for inbound %s: %s",
                    inbound.get("id", "unknown"),
                    exc,
                )
                continue

        return None

    def check_connection(self) -> bool:
        """Verify connection to the panel is working.

        Attempts to login and returns True if successful, False otherwise.
        Useful for validating server credentials before storing them.

        Returns:
            True if connection and authentication successful, False otherwise
        """
        try:
            if not self._authenticated:
                self._login()
            return self._authenticated
        except (XUIError, XUIConnectionError):
            return False

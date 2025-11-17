"""High level bot application logic.

The code focuses on clarity instead of features. Every operation relies on
SQLite and HTTP requests that are available in a default Python installation.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from urllib.parse import quote, urlencode, urlparse

from .config import Settings
from . import database
from .telegram import TelegramAPIError, TelegramBot
from .xui_api import XUIClient, XUIError

LOGGER = logging.getLogger(__name__)

ROLE_ADMIN = "ADMIN"
ROLE_ACCOUNTANT = "ACCOUNTANT"
ROLE_USER = "USER"

STATUS_WAITING_RECEIPT = "WAITING_RECEIPT"
STATUS_PENDING_REVIEW = "PENDING_REVIEW"
STATUS_ACTIVE = "ACTIVE"
STATUS_REJECTED = "REJECTED"
STATUS_EXPIRED = "EXPIRED"


def _extract_payload(response: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize API responses that may wrap useful data under multiple keys."""

    if not isinstance(response, dict):
        return {}
    for key in ("data", "obj", "result"):
        candidate = response.get(key)
        if isinstance(candidate, dict):
            return candidate
    return response


def _as_dict(value: Any) -> Dict[str, Any]:
    """Convert JSON strings or ``None`` values into dictionaries."""

    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _find_client(settings: Dict[str, Any], *, client_id: Optional[str], email: str) -> Dict[str, Any]:
    """Locate the client entry returned by the panel."""

    clients = settings.get("clients")
    if not isinstance(clients, list):
        return {}
    for client in clients:
        if not isinstance(client, dict):
            continue
        if client_id and client.get("id") == client_id:
            return client
        if client_id and client.get("uuid") == client_id:
            return client
        if client.get("email") == email:
            return client
    return {}


def _tls_parameters(stream_settings: Dict[str, Any], security: str) -> Dict[str, str]:
    """Collect TLS-related query parameters."""

    params: Dict[str, str] = {}
    if security and security != "none":
        params["security"] = security
        tls_settings = stream_settings.get(f"{security}Settings")
        if isinstance(tls_settings, dict):
            server_name = tls_settings.get("serverName")
            if server_name:
                params["sni"] = server_name
            alpn = tls_settings.get("alpn")
            if isinstance(alpn, list) and alpn:
                params["alpn"] = ",".join(alpn)
            fingerprint = tls_settings.get("fingerprint")
            if fingerprint:
                params["fp"] = fingerprint
    return params


def _network_parameters(stream_settings: Dict[str, Any], network: str) -> Dict[str, str]:
    """Collect network specific query parameters."""

    params: Dict[str, str] = {}
    if network == "ws":
        ws = stream_settings.get("wsSettings")
        if isinstance(ws, dict):
            if ws.get("path"):
                params["path"] = ws["path"]
            headers = ws.get("headers")
            if isinstance(headers, dict) and headers.get("Host"):
                params["host"] = headers["Host"]
    elif network == "grpc":
        grpc = stream_settings.get("grpcSettings")
        if isinstance(grpc, dict):
            if grpc.get("serviceName"):
                params["serviceName"] = grpc["serviceName"]
            if grpc.get("mode"):
                params["mode"] = grpc["mode"]
    elif network == "tcp":
        tcp = stream_settings.get("tcpSettings")
        if isinstance(tcp, dict):
            header = tcp.get("header")
            if isinstance(header, dict) and header.get("type") and header.get("type") != "none":
                params["headerType"] = header["type"]
    elif network == "http":
        http_settings = stream_settings.get("httpSettings")
        if isinstance(http_settings, dict):
            path = http_settings.get("path")
            if isinstance(path, list):
                params["path"] = ",".join(path)
            elif isinstance(path, str):
                params["path"] = path
            host = http_settings.get("host")
            if isinstance(host, list) and host:
                params["host"] = ",".join(host)
            elif isinstance(host, str):
                params["host"] = host
    return {k: v for k, v in params.items() if v}


def build_config_link(base_url: str, inbound: Dict[str, Any], client: Dict[str, Any]) -> Optional[str]:
    """Craft a shareable configuration string for the created client."""

    if not inbound or not client:
        return None
    host = urlparse(base_url).hostname or inbound.get("listen")
    port = inbound.get("port")
    protocol = inbound.get("protocol")
    if not host or not port or not protocol:
        return None
    remark = inbound.get("remark") or client.get("email") or "VPN"
    stream_settings = _as_dict(inbound.get("streamSettings"))
    network = stream_settings.get("network", "tcp")
    security = stream_settings.get("security", "none")
    if protocol == "vless":
        user_id = client.get("id") or client.get("uuid")
        if not user_id:
            return None
        params = {"type": network, "encryption": "none"}
        params.update(_tls_parameters(stream_settings, security))
        params.update(_network_parameters(stream_settings, network))
        query = urlencode({k: v for k, v in params.items() if v})
        return f"vless://{user_id}@{host}:{port}?{query}#{quote(str(remark))}"
    if protocol == "vmess":
        user_id = client.get("id") or client.get("uuid")
        if not user_id:
            return None
        tls_params = _tls_parameters(stream_settings, security)
        net_params = _network_parameters(stream_settings, network)
        vmess_config = {
            "v": "2",
            "ps": str(remark),
            "add": host,
            "port": str(port),
            "id": user_id,
            "aid": str(client.get("alterId") or client.get("aid") or 0),
            "scy": client.get("security") or "auto",
            "net": network,
            "type": net_params.get("headerType", "none"),
            "host": net_params.get("host", tls_params.get("sni", "")),
            "path": net_params.get("path", ""),
            "tls": "tls" if security and security != "none" else "",
            "sni": tls_params.get("sni", ""),
            "alpn": tls_params.get("alpn", ""),
        }
        encoded = base64.b64encode(json.dumps(vmess_config, separators=(",", ":")).encode()).decode()
        return f"vmess://{encoded}"
    if protocol == "trojan":
        password = client.get("password") or client.get("id") or client.get("uuid")
        if not password:
            return None
        params = {"type": network}
        params.update(_tls_parameters(stream_settings, security))
        params.update(_network_parameters(stream_settings, network))
        query = urlencode({k: v for k, v in params.items() if v})
        if query:
            query = f"?{query}"
        return f"trojan://{password}@{host}:{port}{query}#{quote(str(remark))}"
    return None


class BotApp:
    """Very small Telegram bot that processes updates sequentially."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.conn = database.connect(settings.database_path)
        database.initialize(self.conn)
        self.bot = TelegramBot(settings.bot_token)
        self.states: Dict[int, Dict[str, object]] = {}

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------
    def run(self) -> None:  # pragma: no cover - infinite loop
        LOGGER.info("bot started")
        offset: Optional[int] = None
        while True:
            try:
                updates = self.bot.get_updates(offset=offset, timeout=25)
            except Exception as exc:  # pragma: no cover - network error
                LOGGER.error("failed to fetch updates: %s", exc)
                time.sleep(self.settings.poll_interval)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    self._process_update(update)
                except Exception as exc:
                    LOGGER.exception("unhandled error while processing update: %s", exc)
            time.sleep(self.settings.poll_interval)

    # ------------------------------------------------------------------
    def _process_update(self, update: Dict) -> None:
        if "message" in update:
            self._handle_message(update["message"])
        elif "callback_query" in update:
            self._handle_callback(update["callback_query"])

    # ------------------------------------------------------------------
    def _handle_message(self, message: Dict) -> None:
        chat_id = message["chat"]["id"]
        text = message.get("text")
        user = self._ensure_user(message)
        if text and text.startswith("/start"):
            self._send_welcome(user, chat_id)
            return
        if text and text.startswith("/menu"):
            self._send_dashboard(user, chat_id)
            return
        state = self.states.get(chat_id)
        if state:
            handler = state.get("handler")
            if callable(handler):
                handler(message, state)
            return
        # Default fallback simply keeps dashboard visible
        self._send_dashboard(user, chat_id)

    # ------------------------------------------------------------------
    def _handle_callback(self, callback: Dict) -> None:
        chat_id = callback["message"]["chat"]["id"]
        data = callback.get("data", "")
        user = self._get_user_by_chat(chat_id)
        if not user:
            return
        self.bot.answer_callback_query(callback["id"])
        if data == "admin:add_server":
            self._prompt_add_server(chat_id)
        elif data == "admin:list_servers":
            self._list_servers(chat_id)
        elif data.startswith("admin:delete_server:"):
            server_id = int(data.split(":")[-1])
            self._delete_server(chat_id, server_id)
        elif data == "admin:add_plan":
            self._prompt_add_plan(chat_id)
        elif data == "admin:list_plans":
            self._list_plans(chat_id)
        elif data.startswith("admin:delete_plan:"):
            plan_id = int(data.split(":")[-1])
            self._delete_plan(chat_id, plan_id)
        elif data == "admin:assign_role":
            self._prompt_assign_role(chat_id)
        elif data == "admin:list_accountants":
            self._list_accountants(chat_id)
        elif data == "admin:set_bank":
            self._prompt_bank_card(chat_id)
        elif data == "accountant:pending":
            self._show_pending_orders(chat_id)
        elif data.startswith("accountant:approve:"):
            order_id = int(data.split(":")[-1])
            self._approve_order(chat_id, order_id)
        elif data.startswith("accountant:reject:"):
            order_id = int(data.split(":")[-1])
            self._reject_order(chat_id, order_id)
        elif data == "user:buy":
            self._show_plans_for_purchase(chat_id)
        elif data.startswith("user:buy:"):
            plan_id = int(data.split(":")[-1])
            self._start_purchase(chat_id, plan_id)
        elif data == "user:status":
            self._show_user_orders(chat_id)
        else:
            self._send_dashboard(user, chat_id)

    # ------------------------------------------------------------------
    def _ensure_user(self, message: Dict) -> Dict:
        chat = message["chat"]
        sender = message.get("from", {})
        telegram_id = str(chat["id"])
        with database.transaction(self.conn) as cur:
            cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            row = database.fetch_one(cur)
            if row:
                return row
            cur.execute("SELECT COUNT(*) AS admin_count FROM users WHERE role = ?", (ROLE_ADMIN,))
            admin_count = cur.fetchone()[0]
            role = ROLE_ADMIN if admin_count == 0 else ROLE_USER
            cur.execute(
                "INSERT INTO users (telegram_id, username, first_name, role) VALUES (?, ?, ?, ?)",
                (
                    telegram_id,
                    sender.get("username") or chat.get("username"),
                    sender.get("first_name") or chat.get("first_name"),
                    role,
                ),
            )
        LOGGER.info("registered new user %s with role %s", telegram_id, role)
        with database.transaction(self.conn) as cur:
            cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            return database.fetch_one(cur) or {}

    # ------------------------------------------------------------------
    def _get_user_by_chat(self, chat_id: int) -> Optional[Dict]:
        with database.transaction(self.conn) as cur:
            cur.execute("SELECT * FROM users WHERE telegram_id = ?", (str(chat_id),))
            return database.fetch_one(cur)

    # ------------------------------------------------------------------
    def _send_welcome(self, user: Dict, chat_id: int) -> None:
        role = user.get("role", ROLE_USER)
        text = (
            "Welcome to the VPN shop bot!\n"
            "You are registered as {role}. Use the menu buttons below to get started."
        ).format(role=role.title())
        self.bot.send_message(chat_id, text, reply_markup=self._dashboard_keyboard(role))

    # ------------------------------------------------------------------
    def _send_dashboard(self, user: Dict, chat_id: int) -> None:
        role = user.get("role", ROLE_USER)
        text = "Main dashboard ({role}).".format(role=role.title())
        self.bot.send_message(chat_id, text, reply_markup=self._dashboard_keyboard(role))

    # ------------------------------------------------------------------
    def _dashboard_keyboard(self, role: str) -> Dict:
        if role == ROLE_ADMIN:
            return {
                "inline_keyboard": [
                    [
                        {"text": "Add server", "callback_data": "admin:add_server"},
                        {"text": "List servers", "callback_data": "admin:list_servers"},
                    ],
                    [
                        {"text": "Add plan", "callback_data": "admin:add_plan"},
                        {"text": "List plans", "callback_data": "admin:list_plans"},
                    ],
                    [
                        {"text": "Assign roles", "callback_data": "admin:assign_role"},
                        {"text": "Accountants", "callback_data": "admin:list_accountants"},
                    ],
                    [
                        {"text": "Set bank card", "callback_data": "admin:set_bank"},
                        {"text": "Pending receipts", "callback_data": "accountant:pending"},
                    ],
                ]
            }
        if role == ROLE_ACCOUNTANT:
            return {
                "inline_keyboard": [
                    [{"text": "Pending receipts", "callback_data": "accountant:pending"}],
                    [{"text": "View plans", "callback_data": "user:buy"}],
                    [{"text": "My orders", "callback_data": "user:status"}],
                ]
            }
        return {
            "inline_keyboard": [
                [{"text": "Buy plan", "callback_data": "user:buy"}],
                [{"text": "Order status", "callback_data": "user:status"}],
            ]
        }

    # ------------------------------------------------------------------
    def _prompt_add_server(self, chat_id: int) -> None:
        self.states[chat_id] = {"handler": self._handle_add_server}
        self.bot.send_message(
            chat_id,
            "Send server information as 'Title,URL,Username,Password'.",
        )

    def _handle_add_server(self, message: Dict, state: Dict) -> None:
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 4:
            self.bot.send_message(chat_id, "Invalid format. Please send Title,URL,Username,Password")
            return
        title, url, username, password = parts
        with database.transaction(self.conn) as cur:
            cur.execute(
                "INSERT INTO servers (title, base_url, username, password) VALUES (?, ?, ?, ?)",
                (title, url, username, password),
            )
        self.states.pop(chat_id, None)
        self.bot.send_message(chat_id, "Server saved.")
        user = self._get_user_by_chat(chat_id)
        if user:
            self._send_dashboard(user, chat_id)

    # ------------------------------------------------------------------
    def _list_servers(self, chat_id: int) -> None:
        with database.transaction(self.conn) as cur:
            cur.execute("SELECT id, title, base_url FROM servers ORDER BY id")
            servers = database.fetch_all(cur)
        if not servers:
            text = "No servers stored."
        else:
            text = "\n".join(f"#{s['id']} - {s['title']} ({s['base_url']})" for s in servers)
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": f"Delete #{s['id']}", "callback_data": f"admin:delete_server:{s['id']}"}
                ]
                for s in servers
            ]
        } if servers else self._dashboard_keyboard(ROLE_ADMIN)
        self.bot.send_message(chat_id, text, reply_markup=keyboard)

    # ------------------------------------------------------------------
    def _delete_server(self, chat_id: int, server_id: int) -> None:
        with database.transaction(self.conn) as cur:
            cur.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        self.bot.send_message(chat_id, f"Server #{server_id} deleted.")

    # ------------------------------------------------------------------
    def _prompt_add_plan(self, chat_id: int) -> None:
        self.states[chat_id] = {"handler": self._handle_add_plan}
        self.bot.send_message(
            chat_id,
            (
                "Send plan data as 'Name,ServerID,InboundID,Country,VolumeGB,DurationDays,MultiUser,Price'.\n"
                "Example: Basic,1,100,IR,50,30,1,5"
            ),
        )

    def _handle_add_plan(self, message: Dict, state: Dict) -> None:
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 8:
            self.bot.send_message(chat_id, "Invalid format. Please send 8 comma separated values.")
            return
        name, server_id, inbound_id, country, volume, duration, multi, price = parts
        try:
            server_id = int(server_id)
            inbound_id = int(inbound_id)
            volume = int(volume)
            duration = int(duration)
            multi = int(multi)
            price = float(price)
        except ValueError:
            self.bot.send_message(chat_id, "Numeric fields must be numbers.")
            return
        with database.transaction(self.conn) as cur:
            cur.execute(
                "INSERT INTO plans (server_id, name, country, inbound_id, volume_gb, duration_days, multi_user, price)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (server_id, name, country, inbound_id, volume, duration, multi, price),
            )
        self.states.pop(chat_id, None)
        self.bot.send_message(chat_id, "Plan saved.")

    # ------------------------------------------------------------------
    def _list_plans(self, chat_id: int) -> None:
        with database.transaction(self.conn) as cur:
            cur.execute(
                "SELECT plans.id, plans.name, plans.country, plans.price, plans.duration_days, plans.volume_gb, servers.title"
                " FROM plans JOIN servers ON plans.server_id = servers.id ORDER BY plans.id"
            )
            plans = database.fetch_all(cur)
        if not plans:
            text = "No plans configured."
            keyboard = self._dashboard_keyboard(ROLE_ADMIN)
        else:
            lines = []
            keyboard = {"inline_keyboard": []}
            for plan in plans:
                lines.append(
                    (
                        f"#{plan['id']} - {plan['name']} ({plan['country']}) - "
                        f"{plan['volume_gb']}GB/{plan['duration_days']}d - ${plan['price']} on {plan['title']}"
                    )
                )
                keyboard["inline_keyboard"].append(
                    [{"text": f"Delete #{plan['id']}", "callback_data": f"admin:delete_plan:{plan['id']}"}]
                )
            text = "\n".join(lines)
        self.bot.send_message(chat_id, text, reply_markup=keyboard)

    # ------------------------------------------------------------------
    def _delete_plan(self, chat_id: int, plan_id: int) -> None:
        with database.transaction(self.conn) as cur:
            cur.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        self.bot.send_message(chat_id, f"Plan #{plan_id} deleted.")

    # ------------------------------------------------------------------
    def _prompt_assign_role(self, chat_id: int) -> None:
        self.states[chat_id] = {"handler": self._handle_assign_role}
        self.bot.send_message(chat_id, "Send assignment as '@username ROLE'. ROLE can be ADMIN or ACCOUNTANT.")

    def _handle_assign_role(self, message: Dict, state: Dict) -> None:
        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        try:
            username, role = text.split()
        except ValueError:
            self.bot.send_message(chat_id, "Invalid format. Use '@username ROLE'.")
            return
        role = role.upper()
        if role not in {ROLE_ADMIN, ROLE_ACCOUNTANT}:
            self.bot.send_message(chat_id, "Role must be ADMIN or ACCOUNTANT.")
            return
        with database.transaction(self.conn) as cur:
            cur.execute("SELECT * FROM users WHERE username = ?", (username.lstrip("@"),))
            user = database.fetch_one(cur)
            if not user:
                self.bot.send_message(chat_id, "User not found. Ask them to /start the bot first.")
                return
            cur.execute("UPDATE users SET role = ? WHERE id = ?", (role, user["id"]))
        self.states.pop(chat_id, None)
        self.bot.send_message(chat_id, f"Role updated for {username} -> {role}.")

    # ------------------------------------------------------------------
    def _list_accountants(self, chat_id: int) -> None:
        with database.transaction(self.conn) as cur:
            cur.execute("SELECT username, first_name FROM users WHERE role = ? ORDER BY id", (ROLE_ACCOUNTANT,))
            users = database.fetch_all(cur)
        if not users:
            text = "No accountants assigned."
        else:
            text = "\n".join(f"@{u['username'] or ''} - {u['first_name'] or ''}" for u in users)
        self.bot.send_message(chat_id, text)

    # ------------------------------------------------------------------
    def _prompt_bank_card(self, chat_id: int) -> None:
        self.states[chat_id] = {"handler": self._handle_bank_card}
        self.bot.send_message(chat_id, "Send the bank card number to store.")

    def _handle_bank_card(self, message: Dict, state: Dict) -> None:
        chat_id = message["chat"]["id"]
        card = message.get("text", "").strip()
        if not card:
            self.bot.send_message(chat_id, "Card number cannot be empty.")
            return
        with database.transaction(self.conn) as cur:
            cur.execute("REPLACE INTO settings (key, value) VALUES ('bank_card', ?)", (card,))
        self.states.pop(chat_id, None)
        self.bot.send_message(chat_id, "Bank card saved.")

    # ------------------------------------------------------------------
    def _show_pending_orders(self, chat_id: int) -> None:
        with database.transaction(self.conn) as cur:
            cur.execute(
                "SELECT orders.id, orders.user_id, users.username, plans.name, orders.receipt_file_id "
                "FROM orders JOIN users ON orders.user_id = users.id "
                "JOIN plans ON orders.plan_id = plans.id WHERE orders.status = ?",
                (STATUS_PENDING_REVIEW,),
            )
            rows = database.fetch_all(cur)
        if not rows:
            self.bot.send_message(chat_id, "No pending receipts.")
            return
        for row in rows:
            caption = f"Order #{row['id']} from @{row['username']} for {row['name']}"
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": f"Approve #{row['id']}", "callback_data": f"accountant:approve:{row['id']}"},
                        {"text": f"Reject #{row['id']}", "callback_data": f"accountant:reject:{row['id']}"},
                    ]
                ]
            }
            file_id = row.get("receipt_file_id")
            if file_id:
                self.bot.send_photo(chat_id, file_id, caption=caption, reply_markup=keyboard)
            else:
                self.bot.send_message(chat_id, caption, reply_markup=keyboard)

    # ------------------------------------------------------------------
    def _approve_order(self, chat_id: int, order_id: int) -> None:
        order = self._get_order(order_id)
        if not order:
            self.bot.send_message(chat_id, "Order not found.")
            return
        if order["status"] != STATUS_PENDING_REVIEW:
            self.bot.send_message(chat_id, "Order is not waiting for approval.")
            return
        plan = self._get_plan(order["plan_id"])
        if not plan:
            self.bot.send_message(chat_id, "Plan not found for order.")
            return
        server = self._get_server(plan["server_id"])
        if not server:
            self.bot.send_message(chat_id, "Server not found for plan.")
            return
        client = XUIClient(server["base_url"], server["username"], server["password"], verify_ssl=self.settings.xui_verify_ssl)
        expires_at = datetime.utcnow() + timedelta(days=plan["duration_days"])
        config_payload = {
            "email": f"order-{order_id}",
            "expireTime": int(expires_at.timestamp() * 1000),
            "totalGB": plan["volume_gb"] * 1024 * 1024 * 1024,
            "limitIp": plan["multi_user"],
        }
        try:
            response = client.create_client(plan["inbound_id"], config_payload)
            client_payload = _extract_payload(response)
            config_id = (
                client_payload.get("id")
                or client_payload.get("clientId")
                or client_payload.get("uuid")
            )
            if config_id is not None:
                config_id = str(config_id)
        except XUIError as exc:
            self.bot.send_message(chat_id, f"Panel error: {exc}")
            return
        inbound_details: Dict[str, Any] = {}
        client_entry: Dict[str, Any] = {}
        try:
            inbound_response = client.get_inbound(plan["inbound_id"])
            inbound_details = _extract_payload(inbound_response)
            settings = _as_dict(inbound_details.get("settings"))
            client_entry = _find_client(settings, client_id=config_id, email=config_payload["email"])
        except XUIError as exc:
            LOGGER.warning("failed to load inbound details for config: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("unexpected error while parsing inbound data: %s", exc)
        with database.transaction(self.conn) as cur:
            cur.execute(
                "UPDATE orders SET status = ?, approved_at = ?, expires_at = ?, config_id = ? WHERE id = ?",
                (
                    STATUS_ACTIVE,
                    datetime.utcnow().isoformat(),
                    expires_at.isoformat(),
                    config_id,
                    order_id,
                ),
            )
        self.bot.send_message(chat_id, f"Order #{order_id} approved.")
        # Notify user
        config_text = build_config_link(server["base_url"], inbound_details, client_entry)
        message_lines = [
            "Your VPN configuration is ready!",
            f"Plan: {plan['name']}",
            f"Expires: {expires_at.isoformat()}",
        ]
        if config_text:
            message_lines.extend(["", f"Config: {config_text}"])
        try:
            self.bot.send_message(
                int(order["telegram_id"]),
                "\n".join(message_lines),
            )
        except TelegramAPIError as exc:
            LOGGER.warning("failed to notify user about approval: %s", exc)

    # ------------------------------------------------------------------
    def _reject_order(self, chat_id: int, order_id: int) -> None:
        order = self._get_order(order_id)
        if not order:
            self.bot.send_message(chat_id, "Order not found.")
            return
        with database.transaction(self.conn) as cur:
            cur.execute("UPDATE orders SET status = ? WHERE id = ?", (STATUS_REJECTED, order_id))
        self.bot.send_message(chat_id, f"Order #{order_id} rejected.")
        try:
            self.bot.send_message(int(order["telegram_id"]), "Your payment receipt was rejected.")
        except TelegramAPIError as exc:
            LOGGER.warning("failed to notify about rejection: %s", exc)

    # ------------------------------------------------------------------
    def _show_plans_for_purchase(self, chat_id: int) -> None:
        with database.transaction(self.conn) as cur:
            cur.execute("SELECT id, name, price, duration_days, volume_gb FROM plans ORDER BY id")
            plans = database.fetch_all(cur)
        if not plans:
            self.bot.send_message(chat_id, "No plans available right now.")
            return
        lines = []
        keyboard = {"inline_keyboard": []}
        for plan in plans:
            lines.append(
                f"#{plan['id']} - {plan['name']}: {plan['volume_gb']}GB / {plan['duration_days']} days - ${plan['price']}"
            )
            keyboard["inline_keyboard"].append(
                [{"text": f"Buy #{plan['id']}", "callback_data": f"user:buy:{plan['id']}"}]
            )
        with database.transaction(self.conn) as cur:
            cur.execute("SELECT value FROM settings WHERE key = 'bank_card'")
            card_row = database.fetch_one(cur)
        card_text = f"\nPay to card: {card_row['value']}" if card_row else ""
        self.bot.send_message(chat_id, "\n".join(lines) + card_text, reply_markup=keyboard)

    # ------------------------------------------------------------------
    def _start_purchase(self, chat_id: int, plan_id: int) -> None:
        plan = self._get_plan(plan_id)
        if not plan:
            self.bot.send_message(chat_id, "Plan not found.")
            return
        user = self._get_user_by_chat(chat_id)
        if not user:
            return
        with database.transaction(self.conn) as cur:
            cur.execute(
                "INSERT INTO orders (user_id, plan_id, status) VALUES (?, ?, ?)",
                (user["id"], plan_id, STATUS_WAITING_RECEIPT),
            )
            order_id = cur.lastrowid
        self.states[chat_id] = {"handler": self._handle_receipt_upload, "order_id": order_id}
        self.bot.send_message(chat_id, f"Send payment receipt photo for order #{order_id}.")

    def _handle_receipt_upload(self, message: Dict, state: Dict) -> None:
        chat_id = message["chat"]["id"]
        photos = message.get("photo") or []
        if not photos:
            self.bot.send_message(chat_id, "Please send the receipt as a photo.")
            return
        file_id = photos[-1]["file_id"]
        order_id = state.get("order_id")
        with database.transaction(self.conn) as cur:
            cur.execute(
                "UPDATE orders SET status = ?, receipt_file_id = ? WHERE id = ?",
                (STATUS_PENDING_REVIEW, file_id, order_id),
            )
        self.states.pop(chat_id, None)
        self.bot.send_message(chat_id, "Receipt received. Please wait for review.")

    # ------------------------------------------------------------------
    def _show_user_orders(self, chat_id: int) -> None:
        user = self._get_user_by_chat(chat_id)
        if not user:
            return
        with database.transaction(self.conn) as cur:
            cur.execute(
                "SELECT orders.id, orders.status, orders.expires_at, plans.name, orders.traffic_used"
                " FROM orders JOIN plans ON orders.plan_id = plans.id WHERE orders.user_id = ? ORDER BY orders.id DESC",
                (user["id"],),
            )
            rows = database.fetch_all(cur)
        if not rows:
            self.bot.send_message(chat_id, "You have no orders yet.")
            return
        lines = []
        for row in rows:
            expires = row.get("expires_at") or "-"
            lines.append(
                f"Order #{row['id']} - {row['name']}\nStatus: {row['status']}\nExpires: {expires}\nUsed: {row['traffic_used']} GB"
            )
        self.bot.send_message(chat_id, "\n\n".join(lines))

    # ------------------------------------------------------------------
    def _get_order(self, order_id: int) -> Optional[Dict]:
        with database.transaction(self.conn) as cur:
            cur.execute(
                "SELECT orders.*, users.telegram_id FROM orders JOIN users ON orders.user_id = users.id WHERE orders.id = ?",
                (order_id,),
            )
            return database.fetch_one(cur)

    def _get_plan(self, plan_id: int) -> Optional[Dict]:
        with database.transaction(self.conn) as cur:
            cur.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
            return database.fetch_one(cur)

    def _get_server(self, server_id: int) -> Optional[Dict]:
        with database.transaction(self.conn) as cur:
            cur.execute("SELECT * FROM servers WHERE id = ?", (server_id,))
            return database.fetch_one(cur)

    # ------------------------------------------------------------------
    # Helpers for background worker
    # ------------------------------------------------------------------
    def fetch_expired_orders(self) -> list:
        with database.transaction(self.conn) as cur:
            cur.execute(
                "SELECT id FROM orders WHERE status = ? AND expires_at IS NOT NULL AND expires_at <= ?",
                (STATUS_ACTIVE, datetime.utcnow().isoformat()),
            )
            return database.fetch_all(cur)

    def mark_expired(self, order_id: int) -> None:
        with database.transaction(self.conn) as cur:
            cur.execute(
                "UPDATE orders SET status = ?, config_id = NULL WHERE id = ?",
                (STATUS_EXPIRED, order_id),
            )

    def get_order_details(self, order_id: int) -> Dict:
        with database.transaction(self.conn) as cur:
            cur.execute(
                "SELECT orders.id, orders.config_id, users.telegram_id, plans.inbound_id, plans.server_id"
                " FROM orders JOIN users ON orders.user_id = users.id"
                " JOIN plans ON orders.plan_id = plans.id WHERE orders.id = ?",
                (order_id,),
            )
            row = database.fetch_one(cur)
            return row or {}

    def make_client(self, server_id: int) -> XUIClient:
        server = self._get_server(server_id)
        if not server:
            raise RuntimeError("server not found")
        return XUIClient(
            server["base_url"],
            server["username"],
            server["password"],
            verify_ssl=self.settings.xui_verify_ssl,
        )

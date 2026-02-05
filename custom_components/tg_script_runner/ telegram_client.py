from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

import aiohttp

_LOGGER = logging.getLogger(__name__)

OnRunEntity = Callable[[str], Awaitable[str]]
OnHelp = Callable[[], Awaitable[str]]


@dataclass(frozen=True)
class TgUpdate:
    update_id: int
    chat_id: int
    user_id: int | None
    text: str | None


class TgBot:
    def __init__(
        self,
        token: str,
        allowed_users: set[int],
        command_map: dict[str, str],
        on_run_entity: OnRunEntity,
        on_help: OnHelp,
        poll_interval_s: float = 2.0,
    ):
        self._token = token
        self._allowed_users = allowed_users
        self._command_map = command_map
        self._on_run_entity = on_run_entity
        self._on_help = on_help
        self._poll_interval_s = poll_interval_s

        self._base = f"https://api.telegram.org/bot{token}"
        self._stopping = asyncio.Event()
        self._offset: int | None = None
        self._session: aiohttp.ClientSession | None = None

    def _is_allowed(self, user_id: int | None) -> bool:
        if not self._allowed_users:
            # якщо список пустий — дозволено всім (можеш змінити на “заборонити”)
            return True
        return user_id is not None and user_id in self._allowed_users

    async def run(self) -> None:
        self._session = aiohttp.ClientSession()
        try:
            while not self._stopping.is_set():
                try:
                    updates = await self._get_updates()
                    for u in updates:
                        self._offset = u.update_id + 1
                        await self._handle_update(u)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    _LOGGER.exception("Telegram polling error")
                await asyncio.sleep(self._poll_interval_s)
        finally:
            await self._session.close()
            self._session = None

    async def stop(self) -> None:
        self._stopping.set()

    async def _get_updates(self) -> list[TgUpdate]:
        assert self._session is not None

        params = {
            "timeout": "15",
        }
        if self._offset is not None:
            params["offset"] = str(self._offset)

        async with self._session.get(f"{self._base}/getUpdates", params=params) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram getUpdates failed: {data}")

        result = []
        for item in data.get("result", []):
            upd_id = int(item.get("update_id"))
            msg = item.get("message") or item.get("edited_message")
            if not msg:
                continue
            chat = msg.get("chat") or {}
            from_user = msg.get("from") or {}
            text = msg.get("text")

            result.append(
                TgUpdate(
                    update_id=upd_id,
                    chat_id=int(chat.get("id")),
                    user_id=(int(from_user["id"]) if "id" in from_user else None),
                    text=text,
                )
            )
        return result

    async def _send(self, chat_id: int, text: str) -> None:
        assert self._session is not None
        payload = {"chat_id": chat_id, "text": text}
        async with self._session.post(f"{self._base}/sendMessage", json=payload) as resp:
            data = await resp.json()
            if not data.get("ok"):
                _LOGGER.warning("Telegram sendMessage failed: %s", data)

    async def _handle_update(self, u: TgUpdate) -> None:
        if not u.text:
            return

        if not self._is_allowed(u.user_id):
            await self._send(u.chat_id, "⛔️ Доступ заборонено")
            return

        text = u.text.strip()

        # /help
        if text.startswith("/help"):
            await self._send(u.chat_id, await self._on_help())
            return

        # map commands: /pc_off -> script.pc_off
        cmd = text.split()[0]
        if cmd in self._command_map:
            entity_id = self._command_map[cmd]
            msg = await self._on_run_entity(entity_id)
            await self._send(u.chat_id, msg)
            return

        # /run <entity_id>
        if text.startswith("/run"):
            parts = text.split(maxsplit=1)
            if len(parts) != 2:
                await self._send(u.chat_id, "Використання: /run script.pc_off")
                return
            entity_id = parts[1].strip()
            msg = await self._on_run_entity(entity_id)
            await self._send(u.chat_id, msg)
            return

        await self._send(u.chat_id, "Невідома команда. Напиши /help")

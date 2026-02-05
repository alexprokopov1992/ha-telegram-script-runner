from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

_LOGGER = logging.getLogger(__name__)

OnRunEntity = Callable[[str], Awaitable[str]]
OnHelp = Callable[[], Awaitable[str]]

class TgBot:
    def __init__(
        self,
        token: str,
        allowed_users: set[int],
        command_map: dict[str, str],
        on_run_entity: OnRunEntity,
        on_help: OnHelp,
    ):
        self._token = token
        self._allowed_users = allowed_users
        self._command_map = command_map
        self._on_run_entity = on_run_entity
        self._on_help = on_help

        self._app: Application | None = None
        self._stopping = asyncio.Event()

    def _is_allowed(self, update: Update) -> bool:
        if not self._allowed_users:
            # якщо пусто — дозволено всім (можеш зробити навпаки)
            return True
        user = update.effective_user
        return bool(user and user.id in self._allowed_users)

    async def run(self) -> None:
        self._app = Application.builder().token(self._token).build()

        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("run", self._cmd_run))

        # Додаткові кастом-команди з мапи (/away, /pc_off, ...)
        for cmd in self._command_map.keys():
            name = cmd.lstrip("/")

            async def _handler(update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd=cmd):
                if not self._is_allowed(update):
                    await update.message.reply_text("⛔️ Доступ заборонено")
                    return
                entity_id = self._command_map.get(_cmd, "")
                if not entity_id:
                    await update.message.reply_text("Немає привʼязки для команди")
                    return
                msg = await self._on_run_entity(entity_id)
                await update.message.reply_text(msg)

            self._app.add_handler(CommandHandler(name, _handler))

        await self._app.initialize()
        await self._app.start()
        # polling
        await self._app.updater.start_polling(drop_pending_updates=True)

        try:
            await self._stopping.wait()
        finally:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def stop(self) -> None:
        self._stopping.set()

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            await update.message.reply_text("⛔️ Доступ заборонено")
            return
        text = await self._on_help()
        await update.message.reply_text(text)

    async def _cmd_run(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            await update.message.reply_text("⛔️ Доступ заборонено")
            return
        if not context.args:
            await update.message.reply_text("Використання: /run script.pc_off")
            return
        entity_id = context.args[0]
        msg = await self._on_run_entity(entity_id)
        await update.message.reply_text(msg)

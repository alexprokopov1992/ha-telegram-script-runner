from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, CONF_TOKEN, CONF_ALLOWED_USERS, CONF_COMMAND_MAP
from .telegram_client import TgBot

_LOGGER = logging.getLogger(__name__)

def _parse_allowed_users(raw: str) -> set[int]:
    raw = (raw or "").strip()
    if not raw:
        return set()
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            pass
    return out

def _parse_command_map(raw: str) -> dict[str, str]:
    """
    Accepts:
      - multiline text:
          /pc_on=script.turn_on_pc
          /pc_off=script.shutdown_pc
      - single line with literal \n:
          /pc_on=script.turn_on_pc\n/pc_off=script.shutdown_pc
      - single line separated by ';':
          /pc_on=script.turn_on_pc; /pc_off=script.shutdown_pc
    """
    raw = (raw or "").strip()
    if not raw:
        return {}

    # If user typed "\n" literally in a single-line field, convert it to real newlines
    raw = raw.replace("\\n", "\n")

    # Split into "lines", and additionally allow ';' as separator inside a line
    parts: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # allow multiple mappings in one line separated by ';'
        parts.extend([p.strip() for p in line.split(";") if p.strip()])

    m: dict[str, str] = {}
    for item in parts:
        if not item or item.startswith("#"):
            continue
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and v:
            m[k] = v

    return m


class TgCoordinator:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        self._bot: TgBot | None = None
        self._task: asyncio.Task | None = None

    async def async_start(self) -> None:
        cfg = {**self.entry.data, **self.entry.options}

        token = cfg[CONF_TOKEN]
        allowed_users = _parse_allowed_users(cfg.get(CONF_ALLOWED_USERS, ""))
        command_map = _parse_command_map(cfg.get(CONF_COMMAND_MAP, ""))

        self._bot = TgBot(
            token=token,
            allowed_users=allowed_users,
            command_map=command_map,
            on_run_entity=self._handle_run_entity,
            on_help=self._handle_help,
        )

        self._task = self.hass.async_create_task(self._bot.run())
        _LOGGER.info("Telegram Script Runner started")

    async def async_stop(self) -> None:
        if self._bot:
            await self._bot.stop()
        if self._task:
            self._task.cancel()
            self._task = None
        _LOGGER.info("Telegram Script Runner stopped")

    async def _handle_help(self) -> str:
        cfg = {**self.entry.data, **self.entry.options}
        command_map = _parse_command_map(cfg.get(CONF_COMMAND_MAP, ""))

        lines = [
            "Команди:",
            "/run <entity_id>  — запуск entity (script/automation/scene/switch і т.д.)",
        ]
        if command_map:
            lines.append("")
            lines.append("Швидкі команди:")
            for k, v in command_map.items():
                lines.append(f"{k} → {v}")
        return "\n".join(lines)

    async def _handle_run_entity(self, entity_id: str) -> str:
        entity_id = (entity_id or "").strip()
        if "." not in entity_id:
            return "Невірний entity_id. Приклад: script.pc_off"

        domain, _ = entity_id.split(".", 1)

        # Найчастіше достатньо turn_on (script, scene, switch, light...)
        # Для automation може бути trigger або turn_on; дам універсальний підхід:
        try:
            if domain == "automation":
                await self.hass.services.async_call(
                    "automation", "trigger", {"entity_id": entity_id}, blocking=True
                )
            else:
                await self.hass.services.async_call(
                    domain, "turn_on", {"entity_id": entity_id}, blocking=True
                )
        except Exception as e:
            _LOGGER.exception("Failed to run %s", entity_id)
            return f"Помилка запуску {entity_id}: {e}"

        return f"✅ Запустив: {entity_id}"

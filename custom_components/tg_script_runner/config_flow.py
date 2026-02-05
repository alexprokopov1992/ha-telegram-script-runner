from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, CONF_TOKEN, CONF_ALLOWED_USERS, CONF_COMMAND_MAP

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): str,
        vol.Optional(CONF_ALLOWED_USERS, default=""): str,  # "123,456"
        vol.Optional(CONF_COMMAND_MAP, default=""): str,    # "/away=script.away_mode\n/pc_off=script.pc_off"
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

        token = user_input[CONF_TOKEN].strip()
        allowed_users_raw = user_input.get(CONF_ALLOWED_USERS, "").strip()
        command_map_raw = user_input.get(CONF_COMMAND_MAP, "").strip()

        data = {
            CONF_TOKEN: token,
            CONF_ALLOWED_USERS: allowed_users_raw,
            CONF_COMMAND_MAP: command_map_raw,
        }

        return self.async_create_entry(title="Telegram Script Runner", data=data)

    @callback
    def async_get_options_flow(self, config_entry):
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is None:
            defaults = {**self.config_entry.data, **self.config_entry.options}
            schema = vol.Schema(
                {
                    vol.Required(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): str,
                    vol.Optional(CONF_ALLOWED_USERS, default=defaults.get(CONF_ALLOWED_USERS, "")): str,
                    vol.Optional(CONF_COMMAND_MAP, default=defaults.get(CONF_COMMAND_MAP, "")): str,
                }
            )
            return self.async_show_form(step_id="init", data_schema=schema)

        return self.async_create_entry(title="", data=user_input)

"""
Smart-home clients for the Zora multi-agent stack.

Phase 7: thin wrappers around Home Assistant REST, Philips Hue bridges,
and MQTT brokers. Each client is optional — the SmartHomeAgent checks
which backends are configured via ``smart_home_config.load()`` and only
hands tool calls to the ones that exist.
"""

from .config import SmartHomeConfig, SmartHomeConfigStore
from .ha_client import HomeAssistantClient
from .hue_client import HueClient
from .mqtt_client import MqttClient

__all__ = [
    "SmartHomeConfig",
    "SmartHomeConfigStore",
    "HomeAssistantClient",
    "HueClient",
    "MqttClient",
]

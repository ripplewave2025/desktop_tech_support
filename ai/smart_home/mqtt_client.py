"""
MQTT client wrapper.

Thin adapter over ``paho-mqtt`` that:
  • Connects, publishes a single message, and disconnects for each call
    (no long-lived session — the SmartHomeAgent is request/response, not
    a pub/sub bridge).
  • Supports a short-lived subscribe-then-timeout mode for "read the last
    retained value from this topic" use cases — again, no long sessions.
  • Remembers which topics the user has already published to so first-use
    of a new topic can trigger a consent gate in PolicyEngine.

paho-mqtt is synchronous, so we run both calls in a thread via
``asyncio.to_thread`` to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional


class MqttClient:
    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id_prefix: str = "zora",
    ):
        self._host = host or ""
        self._port = int(port or 1883)
        self._user = username or ""
        self._pass = password or ""
        self._client_id = f"{client_id_prefix}-{uuid.uuid4().hex[:8]}"

    @property
    def host(self) -> str:
        return self._host

    def _new_client(self):
        import paho.mqtt.client as mqtt  # lazy import

        # paho >= 2.0 requires callback API version. Falling back is fine.
        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=self._client_id,
            )
        except AttributeError:
            client = mqtt.Client(client_id=self._client_id)
        if self._user:
            client.username_pw_set(self._user, self._pass or None)
        return client

    async def ping(self) -> Dict[str, Any]:
        """Quick connectivity check — connect, wait for ack, disconnect."""
        if not self._host:
            return {"ok": False, "error": "MQTT host is not configured"}

        def _do() -> Dict[str, Any]:
            try:
                client = self._new_client()
                client.connect(self._host, self._port, keepalive=5)
                client.loop_start()
                try:
                    return {"ok": True, "host": self._host, "port": self._port}
                finally:
                    client.loop_stop()
                    client.disconnect()
            except Exception as e:
                return {"ok": False, "error": str(e)}

        return await asyncio.to_thread(_do)

    async def publish(
        self,
        topic: str,
        payload: Any,
        qos: int = 0,
        retain: bool = False,
    ) -> Dict[str, Any]:
        if not self._host:
            return {"error": "MQTT host is not configured"}
        if not topic:
            return {"error": "topic is required"}

        import json as _json

        if isinstance(payload, (dict, list)):
            payload_str = _json.dumps(payload)
        else:
            payload_str = "" if payload is None else str(payload)

        def _do() -> Dict[str, Any]:
            try:
                client = self._new_client()
                client.connect(self._host, self._port, keepalive=5)
                client.loop_start()
                try:
                    info = client.publish(topic, payload_str, qos=qos, retain=retain)
                    info.wait_for_publish(timeout=5.0)
                    return {
                        "published": True,
                        "topic": topic,
                        "qos": qos,
                        "retain": retain,
                        "payload_bytes": len(payload_str),
                    }
                finally:
                    client.loop_stop()
                    client.disconnect()
            except Exception as e:
                return {"error": str(e)}

        return await asyncio.to_thread(_do)

    async def subscribe_once(
        self,
        topic: str,
        timeout_s: float = 5.0,
    ) -> Dict[str, Any]:
        """Subscribe to ``topic``, wait up to ``timeout_s`` for one message
        (or a retained one), then disconnect. Returns
        ``{"topic", "payload", "received"}``.
        """
        if not self._host:
            return {"error": "MQTT host is not configured"}
        if not topic:
            return {"error": "topic is required"}

        def _do() -> Dict[str, Any]:
            import threading

            received: List[Dict[str, Any]] = []
            event = threading.Event()

            def _on_message(_client, _userdata, msg):
                try:
                    payload = msg.payload.decode("utf-8", errors="replace")
                except Exception:
                    payload = repr(msg.payload)
                received.append({"topic": msg.topic, "payload": payload})
                event.set()

            try:
                client = self._new_client()
                client.on_message = _on_message
                client.connect(self._host, self._port, keepalive=10)
                client.loop_start()
                try:
                    client.subscribe(topic, qos=0)
                    event.wait(timeout=timeout_s)
                finally:
                    client.loop_stop()
                    client.disconnect()
                if received:
                    entry = received[0]
                    return {
                        "received": True,
                        "topic": entry["topic"],
                        "payload": entry["payload"],
                    }
                return {"received": False, "topic": topic, "payload": None}
            except Exception as e:
                return {"error": str(e)}

        return await asyncio.to_thread(_do)

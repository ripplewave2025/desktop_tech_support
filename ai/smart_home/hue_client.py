"""
Philips Hue bridge client.

Hue bridges expose a simple HTTP JSON API on port 80:
  GET  /api/<username>/lights              → list
  GET  /api/<username>/groups              → rooms / zones
  PUT  /api/<username>/lights/<id>/state   → on/off/brightness/ct/hsv
  PUT  /api/<username>/groups/<id>/action  → scene / room-level control

The "username" is really a bridge-specific auth token issued after the
user physically presses the link button and we POST {"devicetype": "..."}.
No cloud account is required for LAN control.

We keep this client LAN-only and never talk to the Hue cloud.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class HueClient:
    def __init__(self, bridge_ip: str, username: str, timeout_s: float = 5.0):
        self._ip = (bridge_ip or "").strip()
        self._user = (username or "").strip()
        self._timeout = timeout_s

    @property
    def bridge_ip(self) -> str:
        return self._ip

    @property
    def base_url(self) -> str:
        return f"http://{self._ip}/api/{self._user}" if self._ip and self._user else ""

    async def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        import httpx  # lazy import

        base = self.base_url
        if not base:
            raise RuntimeError("Hue bridge is not configured (missing IP or username).")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.request(method, f"{base}{path}", json=json_body)
            resp.raise_for_status()
            return resp.json() if resp.content else None

    async def ping(self) -> Dict[str, Any]:
        """Best-effort connectivity check."""
        try:
            result = await self._request("GET", "/config")
            if isinstance(result, list) and result and isinstance(result[0], dict) and "error" in result[0]:
                return {"ok": False, "error": result[0]["error"].get("description", "unknown")}
            return {"ok": True, "bridge": (result or {}).get("name", "hue-bridge")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def list_lights(self) -> List[Dict[str, Any]]:
        data = await self._request("GET", "/lights") or {}
        if not isinstance(data, dict):
            return []
        return [
            {
                "entity_id": f"hue.light.{lid}",
                "hue_id": lid,
                "name": info.get("name", f"light-{lid}"),
                "state": "on" if (info.get("state", {}).get("on")) else "off",
                "attributes": info.get("state", {}),
            }
            for lid, info in data.items()
        ]

    async def list_groups(self) -> List[Dict[str, Any]]:
        data = await self._request("GET", "/groups") or {}
        if not isinstance(data, dict):
            return []
        return [
            {
                "entity_id": f"hue.group.{gid}",
                "hue_id": gid,
                "name": info.get("name", f"group-{gid}"),
                "type": info.get("type", ""),
                "lights": info.get("lights", []),
                "state": "on" if (info.get("state", {}).get("any_on")) else "off",
                "attributes": info.get("action", {}),
            }
            for gid, info in data.items()
        ]

    async def set_light_state(self, hue_id: str, body: Dict[str, Any]) -> Any:
        return await self._request("PUT", f"/lights/{hue_id}/state", body)

    async def set_group_action(self, hue_id: str, body: Dict[str, Any]) -> Any:
        return await self._request("PUT", f"/groups/{hue_id}/action", body)

    @staticmethod
    async def discover(timeout_s: float = 3.0) -> List[Dict[str, str]]:
        """Discover Hue bridges on the LAN.

        Tries the official discovery endpoint first (a LAN-independent
        Philips service that returns bridges on the user's public IP),
        then falls back to mDNS via zeroconf. Returns empty list if both
        fail — callers should then prompt the user for a manual IP.
        """
        # 1) Philips discovery endpoint — fastest, usually works behind NAT.
        try:
            import httpx
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.get("https://discovery.meethue.com/")
                if resp.status_code == 200:
                    data = resp.json() or []
                    found = [
                        {"id": b.get("id", ""), "ip": b.get("internalipaddress", "")}
                        for b in data
                        if b.get("internalipaddress")
                    ]
                    if found:
                        return found
        except Exception:
            pass

        # 2) mDNS fallback via zeroconf. Only reached if the Philips endpoint
        #    fails (firewalls, offline, etc).
        try:
            from zeroconf import Zeroconf, ServiceBrowser  # type: ignore
            import asyncio
            import socket

            discovered: List[Dict[str, str]] = []

            class _Listener:
                def add_service(self, zc, type_, name):
                    info = zc.get_service_info(type_, name)
                    if info and info.addresses:
                        ip = socket.inet_ntoa(info.addresses[0])
                        discovered.append({"id": name, "ip": ip})

                def update_service(self, zc, type_, name):
                    pass

                def remove_service(self, zc, type_, name):
                    pass

            zc = Zeroconf()
            try:
                ServiceBrowser(zc, "_hue._tcp.local.", _Listener())
                await asyncio.sleep(timeout_s)
            finally:
                zc.close()
            return discovered
        except Exception:
            return []

    @staticmethod
    async def create_username(bridge_ip: str, device_label: str = "zora-desktop") -> Dict[str, Any]:
        """Press-the-button onboarding — user must press the physical link
        button on top of the Hue bridge within 30 seconds before calling this.
        Returns ``{ok, username}`` on success.
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"http://{bridge_ip}/api",
                    json={"devicetype": f"{device_label}#zora"},
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and data:
                    first = data[0]
                    if "success" in first:
                        return {"ok": True, "username": first["success"]["username"]}
                    if "error" in first:
                        return {
                            "ok": False,
                            "error": first["error"].get("description", "unknown"),
                            "hint": "Press the link button on your Hue bridge and try again within 30 seconds.",
                        }
                return {"ok": False, "error": "unexpected response from bridge"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

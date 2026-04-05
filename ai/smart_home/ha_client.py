"""
Home Assistant REST client.

Thin async wrapper around the documented /api/states and /api/services
endpoints. We deliberately avoid the WebSocket API because:
  • REST is enough for the "turn on the living room lights" use case,
  • WebSocket needs a long-lived subscription manager we don't need yet,
  • Any HA install that has REST also has tokens the same way.

Docs: https://developers.home-assistant.io/docs/api/rest/
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class HomeAssistantClient:
    def __init__(self, url: str, token: str, timeout_s: float = 10.0):
        self._url = (url or "").rstrip("/")
        self._token = token or ""
        self._timeout = timeout_s

    @property
    def base_url(self) -> str:
        return self._url

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if not self._url or not self._token:
            raise RuntimeError("Home Assistant is not configured (missing url or token).")

        import httpx  # lazy import so tests don't need it

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.request(
                method,
                f"{self._url}{path}",
                headers=self._headers(),
                json=json_body,
            )
            resp.raise_for_status()
            if not resp.content:
                return None
            try:
                return resp.json()
            except Exception:
                return resp.text

    async def ping(self) -> Dict[str, Any]:
        """GET /api/ — used by onboarding to validate url + token."""
        try:
            result = await self._request("GET", "/api/")
            return {"ok": True, "message": (result or {}).get("message", "connected")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def list_states(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """List every entity state, optionally filtered by domain
        (e.g. ``light``, ``switch``, ``climate``, ``lock``)."""
        states = await self._request("GET", "/api/states") or []
        if domain:
            prefix = f"{domain}."
            states = [s for s in states if (s.get("entity_id") or "").startswith(prefix)]
        # Return only the fields we actually use in the agent layer.
        return [
            {
                "entity_id": s.get("entity_id"),
                "state": s.get("state"),
                "attributes": s.get("attributes") or {},
                "last_changed": s.get("last_changed"),
            }
            for s in states
        ]

    async def get_state(self, entity_id: str) -> Dict[str, Any]:
        state = await self._request("GET", f"/api/states/{entity_id}")
        if not state:
            return {}
        return {
            "entity_id": state.get("entity_id"),
            "state": state.get("state"),
            "attributes": state.get("attributes") or {},
            "last_changed": state.get("last_changed"),
        }

    async def call_service(
        self,
        domain: str,
        service: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """POST /api/services/<domain>/<service> with an optional payload.

        Returns the list of states that changed, per HA's REST contract.
        """
        body = dict(data or {})
        return await self._request("POST", f"/api/services/{domain}/{service}", body)

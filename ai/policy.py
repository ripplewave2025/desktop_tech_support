"""
Safety and trust policy helpers for the multi-agent stack.
"""

from __future__ import annotations

from typing import Dict, Iterable, List
from urllib.parse import urlparse

from .task_types import ConsentGate, ExecutionStep


class PolicyEngine:
    OFFICIAL_DOMAINS = {
        "microsoft.com",
        "learn.microsoft.com",
        "support.microsoft.com",
        "dell.com",
        "support.hp.com",
        "hp.com",
        "lenovo.com",
        "support.lenovo.com",
        "playwright.dev",
    }
    COMMUNITY_DOMAINS = {
        "answers.microsoft.com",
        "community.hp.com",
        "reddit.com",
        "superuser.com",
    }
    AUTO_EXECUTION_TRUST_LEVELS = {"official", "local"}
    HIGH_RISK_KEYWORDS = {
        "delete", "remove", "uninstall", "registry", "buy", "purchase",
        "checkout", "payment", "send", "submit", "post", "publish",
        "install", "sign in", "password", "2fa",
    }
    MANUAL_LOGIN_KEYWORDS = {
        "sign in", "login", "2fa", "one-time code", "verification code",
        "password", "passkey",
    }

    def classify_url(self, url: str) -> str:
        if not url:
            return "unknown"
        if url.startswith("local://"):
            return "local"
        host = (urlparse(url).hostname or "").lower()
        if host in self.OFFICIAL_DOMAINS or any(host.endswith(f".{domain}") for domain in self.OFFICIAL_DOMAINS):
            return "official"
        if host in self.COMMUNITY_DOMAINS or any(host.endswith(f".{domain}") for domain in self.COMMUNITY_DOMAINS):
            return "community"
        return "unofficial"

    def confidence_bonus(self, url: str) -> float:
        level = self.classify_url(url)
        if level == "official":
            return 0.35
        if level == "local":
            return 0.4
        if level == "community":
            return 0.12
        if level == "unknown":
            return 0.03
        return 0.0

    def detect_risk(self, text: str) -> str:
        lowered = text.lower()
        if any(keyword in lowered for keyword in self.HIGH_RISK_KEYWORDS):
            return "high"
        if any(word in lowered for word in ("driver", "bios", "firmware", "firewall")):
            return "medium"
        return "low"

    def requires_manual_login(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.MANUAL_LOGIN_KEYWORDS)

    def build_consent_gates(self, steps: Iterable[ExecutionStep]) -> List[ConsentGate]:
        """Return consent gates for every step that needs confirmation.

        Two sources feed this:
          1. Playbook authors who set ``requires_confirmation`` / ``irreversible``
             / ``manual_gate`` directly on a step.
          2. Runtime policy rules (Phase 3d) that upgrade steps based on
             their tool + args — e.g. ``launch_app`` outside Program Files,
             ``browser_*`` hitting a non-allowlisted host, or any write to
             the persistent user profile.
        """
        gates: List[ConsentGate] = []
        for step in steps:
            # Rule-based upgrades happen in-place so the orchestrator's
            # consent-pause loop (which reads these flags on the step) still
            # honors them even without a ConsentGate lookup.
            self._apply_runtime_policy(step)
            if step.requires_confirmation or step.irreversible or step.manual_gate:
                reason = "Manual login required" if step.manual_gate else step.description
                gates.append(
                    ConsentGate(
                        step_id=step.step_id,
                        reason=reason,
                        risk="high" if step.irreversible else "medium",
                    )
                )
        return gates

    # --- Phase 3d runtime policy rules -----------------------------------
    # These upgrade individual steps based on what they actually do, so a
    # recipe author can't accidentally skip the consent gate on a risky
    # action just by forgetting to set the YAML flag.

    _TRUSTED_LAUNCH_PREFIXES = (
        "c:\\program files",
        "c:\\program files (x86)",
        "c:\\windows",
        "%programfiles%",
        "%programfiles(x86)%",
        "%windir%",
    )

    _SMART_HOME_IRREVERSIBLE_ACTIONS = {
        "unlock", "disarm", "disarm_away", "disarm_home",
        "open", "open_door", "open_garage",
        "arm_night", "arm_away", "arm_home",
    }

    def _apply_runtime_policy(self, step: ExecutionStep) -> None:
        tool = (step.tool_name or "").strip()
        args = step.tool_args or {}
        if not tool:
            return

        # launch_app outside a trusted install dir → require confirmation.
        if tool == "launch_app":
            path = str(args.get("path") or args.get("name") or "").strip()
            if path and not self._is_trusted_launch_path(path):
                step.requires_confirmation = True
                if not step.description:
                    step.description = f"Confirm launching {path}"

        # gui_wizard_next has enough side effects (it may click through a
        # EULA + real install) that we default it to requiring confirmation.
        if tool == "gui_wizard_next":
            step.requires_confirmation = True

        # browser_open / browser_click to non-allowlisted hosts → gate it.
        if tool in {"browser_open", "browser_click", "browser_fill"}:
            url = str(args.get("url") or args.get("target") or "")
            # browser_click is usually intra-page and has no URL, leave it.
            if url:
                level = self.classify_url(url)
                if level in {"unofficial", "unknown"}:
                    step.requires_confirmation = True

        # Writing a value into the persistent user profile is low-risk in
        # isolation but we still want a confirmation gate for credentials.
        if tool == "user_profile_set":
            field = str(args.get("field") or "").lower()
            if any(hint in field for hint in ("token", "password", "secret", "api_key", "apikey")):
                step.requires_confirmation = True

        # Smart-home destructive actions (Phase 7) always require an
        # explicit confirmation AND a manual gate — stricter than any
        # other tool class.
        if tool == "smart_home_call":
            action = str(args.get("action") or "").lower()
            if action in self._SMART_HOME_IRREVERSIBLE_ACTIONS:
                step.requires_confirmation = True
                step.manual_gate = True

        # Writing smart-home credentials (HA token, Hue pairing, MQTT
        # password) — sensitive, require a confirmation gate.
        if tool == "smart_home_setup":
            if any(args.get(k) for k in ("token", "password", "username")):
                step.requires_confirmation = True

        # MQTT publish to a topic we've never seen before — free-form
        # topics can brick devices, so the first use gets gated until
        # the executor adds the topic to known_topics.
        if tool == "mqtt_publish":
            topic = str(args.get("topic") or "").strip()
            if topic and not self._is_known_mqtt_topic(topic):
                step.requires_confirmation = True

    def _is_trusted_launch_path(self, path: str) -> bool:
        lowered = path.lower().replace("/", "\\")
        return any(lowered.startswith(prefix) for prefix in self._TRUSTED_LAUNCH_PREFIXES)

    def _is_known_mqtt_topic(self, topic: str) -> bool:
        """Check whether an MQTT topic has already been published to.

        First-time publishes should be gated behind a confirmation (see
        the runtime rule above). We read from the smart-home config store
        — silent-fail so that a missing store never upgrades every step.
        """
        try:
            from .smart_home import SmartHomeConfigStore
            config = SmartHomeConfigStore().load()
            return topic in (config.mqtt.known_topics or [])
        except Exception:
            # If the store can't be loaded, default to "unknown" so we
            # gate — safer than accidentally auto-executing a publish.
            return False

    def can_auto_execute(self, steps: Iterable[ExecutionStep], sources: Iterable[Dict[str, str]]) -> bool:
        if any(step.requires_confirmation or step.irreversible or step.manual_gate for step in steps):
            return False

        ranked_sources = list(sources)
        if not ranked_sources:
            return False

        primary = ranked_sources[0]
        trust_level = primary.get("officialness") or self.classify_url(primary.get("url", ""))
        if trust_level not in self.AUTO_EXECUTION_TRUST_LEVELS:
            return False

        return True

import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.knowledge import KnowledgeLoader
from ai.oem import OEMService
from ai.orchestrator import TaskOrchestrator
from ai.policy import PolicyEngine
from ai.research import ResearchService
from ai.router import RouterAgent
from ai.task_types import AgentRoute, ExecutionStep, OEMProfile, OEMTool, TaskIntent
from storage.db import ZoraMemoryStore


class FakeExecutor:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    async def execute(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name == "web_search":
            return self.results.get(tool_name, {"results": []})
        return self.results.get(tool_name, {"ok": True, "tool": tool_name, "arguments": arguments})


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeOEMService:
    def __init__(self, profile=None):
        self.profile = profile or OEMProfile(
            manufacturer="Dell Inc.",
            model="XPS 15",
            tools=[
                OEMTool(
                    vendor="dell",
                    name="SupportAssist",
                    status="installed",
                    executable="SupportAssist.exe",
                    path="C:/Program Files/Dell/SupportAssist.exe",
                )
            ],
        )

    def detect_profile(self):
        return self.profile


class TestRouterAgent(unittest.TestCase):
    def setUp(self):
        self.router = RouterAgent()
        self.profile = OEMProfile(manufacturer="Dell Inc.", model="XPS")

    def test_routes_oem_requests(self):
        route = self.router.route("Run SupportAssist and check my drivers", self.profile)
        self.assertEqual(route.agent_name, "OEMAgent")

    def test_routes_file_requests(self):
        route = self.router.route("Where is my PDF file?", self.profile)
        self.assertEqual(route.agent_name, "FilesAgent")

    def test_build_intent_sets_browser_flags(self):
        intent = self.router.build_intent("Open the support portal and sign in", self.profile)
        self.assertTrue(intent.requires_browser)
        self.assertTrue(intent.needs_manual_login)


class TestResearchService(unittest.TestCase):
    def setUp(self):
        self.knowledge = KnowledgeLoader()
        self.policy = PolicyEngine()
        self.executor = FakeExecutor(
            {
                "web_search": {
                    "results": [
                        {"title": "Community fix", "url": "https://example.com/fix", "snippet": "random advice"},
                        {"title": "Microsoft settings", "url": "https://learn.microsoft.com/windows", "snippet": "dark mode settings"},
                    ]
                }
            }
        )
        self.service = ResearchService(self.knowledge, self.policy, self.executor)

    def test_official_sources_rank_higher(self):
        intent = TaskIntent(raw_message="Change this to dark mode", normalized_goal="Change this to dark mode", route_hint="WindowsAgent")
        route = AgentRoute(agent_name="WindowsAgent", reason="settings", domain="windows")
        profile = OEMProfile(manufacturer="Dell Inc.", model="XPS")
        packet = run_async(self.service.gather(intent, route, profile))
        self.assertGreater(len(packet.candidates), 0)
        self.assertIn(packet.candidates[0].officialness, {"official", "local"})


class TestOEMService(unittest.TestCase):
    @patch("ai.oem.os.path.exists", return_value=True)
    @patch("ai.oem.shutil.which", return_value="")
    @patch("ai.oem.subprocess.run")
    def test_detects_profile_and_tools(self, mock_run, mock_which, mock_exists):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"System":{"Manufacturer":"Dell Inc.","Model":"XPS 15"},"Bios":{"SerialNumber":"123","SMBIOSBIOSVersion":"1.2.3"}}',
        )
        service = OEMService()
        profile = service.detect_profile()
        self.assertEqual(profile.vendor_slug, "dell")
        self.assertGreater(len(profile.tools), 0)


class TestTaskOrchestrator(unittest.TestCase):
    def _make_orchestrator(self, executor=None, profile=None, tmpdir=None):
        return TaskOrchestrator(
            provider=None,
            executor=executor or FakeExecutor(),
            store=ZoraMemoryStore(os.path.join(tmpdir, "zora.db")),
            knowledge=KnowledgeLoader(),
            oem_service=FakeOEMService(profile),
        )

    def test_support_case_plan_requires_consent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = self._make_orchestrator(tmpdir=tmpdir)
            plan = run_async(orchestrator.plan_task("Prepare a support ticket and track it"))
            self.assertEqual(plan.route.agent_name, "SupportCaseAgent")
            self.assertGreater(len(plan.consent_gates), 0)
            self.assertFalse(plan.auto_execute)

    def test_safe_windows_plan_auto_executes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = FakeExecutor()
            orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
            plan = run_async(orchestrator.plan_task("Change this to dark mode"))
            self.assertEqual(plan.route.agent_name, "WindowsAgent")
            self.assertTrue(plan.auto_execute)
            events = []

            async def collect():
                async for event in orchestrator.execute_plan(plan.task_id):
                    events.append(event)

            run_async(collect())
            self.assertTrue(any(event.get("type") == "tool_result" for event in events))
            self.assertTrue(any(call[0] == "change_windows_setting" for call in executor.calls))

    def test_local_knowledge_playbooks_are_trusted_for_auto_execute(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = FakeExecutor()
            orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
            plan = run_async(orchestrator.plan_task("Where is my PDF file?"))
            self.assertEqual(plan.route.agent_name, "FilesAgent")
            self.assertTrue(plan.auto_execute)

    def test_oem_plan_prefers_installed_vendor_tool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = FakeExecutor()
            orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
            plan = run_async(orchestrator.plan_task("Run the OEM hardware check"))
            self.assertEqual(plan.route.agent_name, "OEMAgent")
            self.assertEqual(plan.steps[0].tool_name, "launch_app")
            self.assertIn("SupportAssist", plan.steps[0].title)

    def test_zoom_link_routes_to_browser_playbook(self):
        """Phase 2 verification: 'join my Zoom meeting' hits BrowserSupportAgent
        and hydrates the browser-zoom-join playbook steps, including the
        gui_click_label handoff to the Zoom desktop client."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = FakeExecutor(
                {
                    "web_search": {
                        "results": [
                            {
                                "title": "Zoom join link",
                                "url": "https://zoom.us/j/1234567890",
                                "snippet": "Click to join the meeting",
                            }
                        ]
                    }
                }
            )
            orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
            plan = run_async(
                orchestrator.plan_task(
                    "Join my Zoom meeting at https://zoom.us/j/1234567890"
                )
            )
            self.assertEqual(plan.route.agent_name, "BrowserSupportAgent")
            tool_names = [s.tool_name for s in plan.steps]
            self.assertIn("browser_open", tool_names)
            self.assertIn("gui_click_label", tool_names)
            # Placeholder substitution for the selected URL should have resolved
            # (either to the web-search result or the summary source).
            open_step = next(s for s in plan.steps if s.tool_name == "browser_open")
            self.assertFalse(
                open_step.tool_args["url"].startswith("{"),
                f"URL placeholder was not substituted: {open_step.tool_args['url']}",
            )

    def test_skip_if_expression_skips_step(self):
        """Phase 5 verification: a step with skip_if='True' should not run
        its tool, and the plan should continue to the next step."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = FakeExecutor()
            orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
            plan = run_async(orchestrator.plan_task("Change this to dark mode"))
            # Splice a skip_if step in front of the dark-mode step.
            plan.steps.insert(
                0,
                ExecutionStep(
                    step_id="should-be-skipped",
                    title="This step should be skipped",
                    description="Explicit skip test",
                    kind="tool",
                    agent_name="WindowsAgent",
                    tool_name="notify",
                    tool_args={"title": "never", "message": "never"},
                    skip_if="True",
                ),
            )
            orchestrator._save_plan(plan)

            events = []

            async def collect():
                async for event in orchestrator.execute_plan(plan.task_id):
                    events.append(event)

            run_async(collect())
            self.assertFalse(
                any(call[0] == "notify" and call[1].get("title") == "never" for call in executor.calls),
                "skipped step should not have fired notify",
            )
            # The dark-mode step should still have run.
            self.assertTrue(
                any(call[0] == "change_windows_setting" for call in executor.calls),
                "plan should continue after skip_if",
            )

    def test_select_from_list_pauses_like_ask_user(self):
        """Phase 5 verification: select_from_list emits the same
        awaiting_user_input pause event, but also carries a choices list
        and a kind='select_from_list' discriminator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = FakeExecutor(
                {
                    "select_from_list": {
                        "status": "awaiting_user_input",
                        "prompt": "Which installer?",
                        "field_name": "installer_path",
                        "choices": [
                            {"label": "setup-a.exe", "value": "C:/Downloads/setup-a.exe"},
                            {"label": "setup-b.exe", "value": "C:/Downloads/setup-b.exe"},
                        ],
                        "kind": "select_from_list",
                    },
                }
            )
            orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
            plan = run_async(orchestrator.plan_task("Change this to dark mode"))
            plan.steps.insert(
                0,
                ExecutionStep(
                    step_id="pick-installer",
                    title="Pick an installer",
                    description="Disambiguate between installers",
                    kind="tool",
                    agent_name="WindowsAgent",
                    tool_name="select_from_list",
                    tool_args={
                        "prompt": "Which installer?",
                        "field_name": "installer_path",
                        "choices": ["a", "b"],
                    },
                ),
            )
            orchestrator._save_plan(plan)

            events = []

            async def collect():
                async for event in orchestrator.execute_plan(plan.task_id):
                    events.append(event)

            run_async(collect())
            request = next((e for e in events if e.get("type") == "user_input_request"), None)
            self.assertIsNotNone(request, "expected user_input_request from select_from_list")
            self.assertEqual(request.get("kind"), "select_from_list")
            self.assertEqual(len(request.get("choices", [])), 2)

    def test_followup_scheduler_surfaces_due_items(self):
        """Phase 4b verification: seeding the DB with an open case that has a
        past-due follow-up should make check_follow_ups() return it, and
        resolve_follow_up() should mark it resolved."""
        import json as _json
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "zora.db")
            store = ZoraMemoryStore(db_path)
            case_id = "CASE-TEST01"
            past = "2020-01-01T00:00:00Z"
            case_payload = {
                "case_id": case_id,
                "issue_summary": "Printer offline after update",
                "status": "open",
                "follow_ups": [
                    {"title": "Check back on driver reinstall", "due_at": past, "status": "open"},
                ],
            }
            # Insert directly via the private connect — mirrors how save_plan writes.
            with store._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO case_records (case_id, task_id, status, ticket_number, portal_url, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (case_id, "task-xyz", "open", "", "", _json.dumps(case_payload)),
                )

            orchestrator = TaskOrchestrator(
                provider=None,
                executor=FakeExecutor(),
                store=store,
                knowledge=KnowledgeLoader(),
                oem_service=FakeOEMService(),
            )
            due = orchestrator.check_follow_ups()
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["case"]["case_id"], case_id)
            self.assertEqual(len(due[0]["due_follow_ups"]), 1)

            updated = orchestrator.resolve_follow_up(case_id, "Check back on driver reinstall")
            self.assertIsNotNone(updated)
            # After resolution the scheduler should no longer surface it.
            self.assertEqual(orchestrator.check_follow_ups(), [])

    def test_bluetooth_pair_routes_to_windows_playbook(self):
        """Phase 3 verification: 'pair my bluetooth headphones' hits the
        WindowsAgent windows-bluetooth-pair playbook, which opens Bluetooth
        settings, asks the user for the advertised device name, and ends
        with gui_click_label('Done')."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = FakeExecutor()
            orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
            plan = run_async(
                orchestrator.plan_task("Pair my bluetooth headphones")
            )
            self.assertEqual(plan.route.agent_name, "WindowsAgent")
            tool_names = [s.tool_name for s in plan.steps]
            # Key beats in the bluetooth pairing recipe.
            self.assertIn("change_windows_setting", tool_names)
            self.assertIn("ask_user", tool_names)
            self.assertIn("gui_click_label", tool_names)
            # The ask_user step should exist and target the right field.
            ask_steps = [s for s in plan.steps if s.tool_name == "ask_user"]
            self.assertTrue(ask_steps)
            self.assertEqual(ask_steps[0].tool_args.get("field_name"), "bt_device_name")
            # The final click-device step should preserve the {user.*}
            # placeholder for late-binding resolution (it's not resolved yet
            # because the user hasn't answered).
            click_device_steps = [
                s for s in plan.steps
                if s.tool_name == "gui_click_label"
                and "{user." in str(s.tool_args.get("label", ""))
            ]
            self.assertTrue(
                click_device_steps,
                f"expected a gui_click_label with {{user.*}} placeholder, got: {[s.tool_args for s in plan.steps if s.tool_name=='gui_click_label']}",
            )
            # The recipe has a manual gate (put device in pairing mode)
            # so the plan should not auto-execute.
            self.assertFalse(plan.auto_execute)
            self.assertTrue(len(plan.consent_gates) > 0)

    def test_installer_from_downloads_requires_confirmation_via_policy(self):
        """Phase 3d verification: the install-from-downloads recipe ends up
        with a launch_app step targeting {user.installer_path} (a
        non-trusted path placeholder). Policy should upgrade the launch
        step to requires_confirmation even though the YAML didn't mark it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = FakeExecutor()
            orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
            plan = run_async(
                orchestrator.plan_task("install the setup.exe from downloads")
            )
            self.assertEqual(plan.route.agent_name, "WindowsAgent")
            launch_steps = [s for s in plan.steps if s.tool_name == "launch_app"]
            self.assertTrue(launch_steps, "expected a launch_app step in install recipe")
            self.assertTrue(
                launch_steps[0].requires_confirmation,
                "policy should gate launch_app on non-trusted path",
            )

    def test_ask_user_pauses_plan_and_resumes_after_input(self):
        """Phase 1 verification: an ask_user step pauses execution and emits a
        user_input_request event; resume_with_input unblocks the plan and
        subsequent steps see the answer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = FakeExecutor(
                {
                    "ask_user": {
                        "status": "awaiting_user_input",
                        "prompt": "What name should I use?",
                        "field_name": "display_name",
                    },
                }
            )
            orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
            plan = run_async(orchestrator.plan_task("Change this to dark mode"))
            # Splice an ask_user step in front of the dark-mode step so we
            # exercise the pause path without needing a full playbook.
            plan.steps.insert(
                0,
                ExecutionStep(
                    step_id="ask-display-name",
                    title="Ask for display name",
                    description="Get the user's preferred name.",
                    kind="tool",
                    agent_name="WindowsAgent",
                    tool_name="ask_user",
                    tool_args={
                        "prompt": "What name should I use?",
                        "field_name": "display_name",
                    },
                ),
            )
            orchestrator._save_plan(plan)

            events = []

            async def collect():
                async for event in orchestrator.execute_plan(plan.task_id):
                    events.append(event)

            run_async(collect())
            # Plan should have paused with a user_input_request, not a tool_result
            # for the dark-mode step.
            self.assertTrue(
                any(e.get("type") == "user_input_request" for e in events),
                f"expected user_input_request, got: {[e.get('type') for e in events]}",
            )
            request_event = next(e for e in events if e.get("type") == "user_input_request")
            self.assertEqual(request_event["field_name"], "display_name")
            self.assertEqual(request_event["step_id"], "ask-display-name")

            # The dark-mode tool must NOT have run yet.
            self.assertFalse(
                any(call[0] == "change_windows_setting" for call in executor.calls),
                "dark-mode step ran before ask_user was answered",
            )

            # Simulate the user submitting their answer.
            resumed = orchestrator.resume_with_input(
                plan.task_id, "ask-display-name", "Alex"
            )
            self.assertIsNotNone(resumed)
            # Saved in the per-task input map for later placeholder lookup.
            self.assertEqual(
                orchestrator._user_inputs[plan.task_id]["ask-display-name"]["value"],
                "Alex",
            )

            # Second pass: plan should continue through the dark-mode step now.
            events2 = []

            async def resume():
                async for event in orchestrator.execute_plan(plan.task_id):
                    events2.append(event)

            run_async(resume())
            self.assertTrue(
                any(call[0] == "change_windows_setting" for call in executor.calls),
                "dark-mode step did not run after ask_user resume",
            )


class TestSmartHomeConfigStore(unittest.TestCase):
    """Phase 7a: credential store obfuscation + round-trip."""

    def test_secrets_are_obfuscated_on_disk(self):
        import json as _json
        from ai.smart_home import SmartHomeConfigStore
        from ai.smart_home.config import HomeAssistantConfig, MqttConfig, HueConfig, SmartHomeConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "smart_home.json")
            store = SmartHomeConfigStore(path=path)
            config = SmartHomeConfig(
                home_assistant=HomeAssistantConfig(
                    url="http://homeassistant.local:8123",
                    token="super-secret-long-lived-token-xyz",
                ),
                mqtt=MqttConfig(
                    host="broker.local",
                    port=1883,
                    username="mqtt_user",
                    password="mqtt_pass",
                ),
                hue=HueConfig(bridge_ip="192.168.1.42", username="hue-user-token"),
                aliases={"living room lights": "light.living_room"},
            )
            store.save(config)

            # On disk: neither the HA token nor the MQTT password should
            # appear as plaintext.
            with open(path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            self.assertNotIn("super-secret-long-lived-token-xyz", raw_text)
            self.assertNotIn("mqtt_pass", raw_text)
            self.assertNotIn("hue-user-token", raw_text)
            # But the URL and the alias (non-secret) are still readable.
            self.assertIn("homeassistant.local", raw_text)
            self.assertIn("living room lights", raw_text)

            # Round-trip: load() should return the original plaintext values.
            reloaded = store.load()
            self.assertEqual(
                reloaded.home_assistant.token,
                "super-secret-long-lived-token-xyz",
            )
            self.assertEqual(reloaded.mqtt.password, "mqtt_pass")
            self.assertEqual(reloaded.hue.username, "hue-user-token")

    def test_redacted_snapshot_hides_secrets(self):
        from ai.smart_home import SmartHomeConfigStore
        from ai.smart_home.config import HomeAssistantConfig, SmartHomeConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "smart_home.json")
            store = SmartHomeConfigStore(path=path)
            store.save(SmartHomeConfig(
                home_assistant=HomeAssistantConfig(
                    url="http://ha.local",
                    token="plaintext-token-that-should-be-hidden",
                ),
            ))
            snapshot = store.redacted_snapshot()
            self.assertEqual(snapshot["home_assistant"]["url"], "http://ha.local")
            self.assertEqual(snapshot["home_assistant"]["token"], "***")
            self.assertTrue(snapshot["home_assistant"]["configured"])
            self.assertTrue(snapshot["any_configured"])
            self.assertFalse(snapshot["mqtt"]["configured"])


class TestSmartHomeRouting(unittest.TestCase):
    """Phase 7d: router rules route smart-home phrases to SmartHomeAgent."""

    def setUp(self):
        self.router = RouterAgent()
        self.profile = OEMProfile(manufacturer="Dell Inc.", model="XPS")

    def test_turn_off_lights_routes_to_smart_home(self):
        route = self.router.route("Turn off the living room lights", self.profile)
        self.assertEqual(route.agent_name, "SmartHomeAgent")

    def test_set_thermostat_routes_to_smart_home(self):
        route = self.router.route("Set the thermostat to 68", self.profile)
        self.assertEqual(route.agent_name, "SmartHomeAgent")

    def test_unlock_door_routes_to_smart_home(self):
        route = self.router.route("Unlock the front door", self.profile)
        self.assertEqual(route.agent_name, "SmartHomeAgent")

    def test_connect_home_assistant_routes_to_smart_home(self):
        route = self.router.route("Connect my Home Assistant", self.profile)
        self.assertEqual(route.agent_name, "SmartHomeAgent")

    def test_bluetooth_still_routes_to_windows(self):
        """Regression: 'pair my bluetooth' should still be Windows, not smart-home."""
        route = self.router.route("Pair my bluetooth headphones", self.profile)
        self.assertEqual(route.agent_name, "WindowsAgent")


class TestSmartHomePlanning(unittest.TestCase):
    """Phase 7 end-to-end: plan_task → hydrated playbook → consent gates."""

    def _patch_store_path(self, tmpdir):
        """Isolate the smart-home config store to a temp file for each test."""
        import ai.smart_home.config as sh_config_mod
        from ai.smart_home.config import SmartHomeConfigStore
        original_init = SmartHomeConfigStore.__init__
        isolated_path = os.path.join(tmpdir, "smart_home.json")

        def _patched_init(self, path=None):
            original_init(self, path=isolated_path)

        SmartHomeConfigStore.__init__ = _patched_init
        return original_init

    def _restore_store(self, original_init):
        from ai.smart_home.config import SmartHomeConfigStore
        SmartHomeConfigStore.__init__ = original_init

    def _make_orchestrator(self, executor=None, tmpdir=None):
        return TaskOrchestrator(
            provider=None,
            executor=executor or FakeExecutor(),
            store=ZoraMemoryStore(os.path.join(tmpdir, "zora.db")),
            knowledge=KnowledgeLoader(),
            oem_service=FakeOEMService(),
        )

    def test_turn_off_lights_hydrates_toggle_playbook(self):
        """Phase 7 verification: 'turn off the lights' picks the
        smart-home-toggle-device playbook and hydrates an ask_user step +
        a smart_home_call(toggle) step."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original = self._patch_store_path(tmpdir)
            try:
                executor = FakeExecutor()
                orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
                plan = run_async(orchestrator.plan_task("Turn off the living room lights"))
                self.assertEqual(plan.route.agent_name, "SmartHomeAgent")
                tool_names = [s.tool_name for s in plan.steps]
                self.assertIn("ask_user", tool_names)
                self.assertIn("smart_home_call", tool_names)
                call_step = next(s for s in plan.steps if s.tool_name == "smart_home_call")
                self.assertEqual(call_step.tool_args.get("action"), "toggle")
                # The entity_id should still carry the late-binding placeholder.
                self.assertIn("{user.", str(call_step.tool_args.get("entity_id", "")))
            finally:
                self._restore_store(original)

    def test_unlock_door_is_manual_gated_by_policy(self):
        """Phase 7 verification: the unlock recipe gets policy-upgraded to
        irreversible + manual_gate on the smart_home_call step, regardless
        of what the YAML specifies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original = self._patch_store_path(tmpdir)
            try:
                executor = FakeExecutor()
                orchestrator = self._make_orchestrator(executor=executor, tmpdir=tmpdir)
                plan = run_async(orchestrator.plan_task("Unlock the front door"))
                self.assertEqual(plan.route.agent_name, "SmartHomeAgent")
                call_steps = [
                    s for s in plan.steps
                    if s.tool_name == "smart_home_call"
                    and s.tool_args.get("action") == "unlock"
                ]
                self.assertTrue(call_steps, "expected an unlock smart_home_call step")
                self.assertTrue(
                    call_steps[0].requires_confirmation,
                    "policy should gate unlock action",
                )
                self.assertTrue(
                    call_steps[0].manual_gate,
                    "unlock should be manual-gated in addition to consent",
                )
                # The plan as a whole should not auto-execute.
                self.assertFalse(plan.auto_execute)
                self.assertTrue(len(plan.consent_gates) > 0)
            finally:
                self._restore_store(original)

    def test_no_backend_configured_returns_onboarding_hint(self):
        """Phase 7 verification: when no smart-home backend is configured
        and the user asks something generic that only matches the
        SmartHomeAgent fallback (no playbook tag hit), the agent returns
        a gentle 'connect a hub' notify step."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original = self._patch_store_path(tmpdir)
            try:
                from ai.agents import SmartHomeAgent
                from ai.task_types import ResearchPacket

                agent = SmartHomeAgent()
                intent = TaskIntent(
                    raw_message="Control my smart home",
                    normalized_goal="Control my smart home",
                    route_hint="SmartHomeAgent",
                )
                route = AgentRoute(
                    agent_name="SmartHomeAgent",
                    reason="smart home",
                    domain="smart_home",
                )
                profile = OEMProfile(manufacturer="Dell Inc.", model="XPS")
                research = ResearchPacket(query="smart home")
                steps = run_async(agent.build_steps(intent, route, research, profile))
                self.assertEqual(len(steps), 1)
                self.assertEqual(steps[0].tool_name, "notify")
                # Title should clearly signal "no hub connected" / "not configured".
                self.assertIn("no smart-home hub", steps[0].title.lower())
            finally:
                self._restore_store(original)


if __name__ == "__main__":
    unittest.main()

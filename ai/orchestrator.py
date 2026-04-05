"""
Multi-agent task orchestrator.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from typing import Any, AsyncIterator, Dict, Optional, Set

from .agents import (
    BrowserSupportAgent,
    ConciergeAgent,
    DesktopNavigationAgent,
    FilesAgent,
    OEMAgent,
    SmartHomeAgent,
    SupportCaseAgent,
    WindowsAgent,
)
from .agents.base import _PLACEHOLDER_RE, SafeDict, _substitute
from .knowledge import KnowledgeLoader
from .oem import OEMService
from .policy import PolicyEngine
from .research import ResearchService
from .router import RouterAgent
from .task_types import CaseRecord, ExecutionPlan
from .tool_executor import ToolExecutor
from storage.db import ZoraMemoryStore


class _DotDict(dict):
    """Dict that also supports attribute access for simpleeval skip_if namespaces."""

    def __getattr__(self, item: str) -> Any:
        if item in self:
            value = self[item]
            if isinstance(value, dict) and not isinstance(value, _DotDict):
                return _DotDict(value)
            return value
        return ""


class TaskOrchestrator:
    def __init__(
        self,
        provider=None,
        executor: Optional[ToolExecutor] = None,
        store: Optional[ZoraMemoryStore] = None,
        knowledge: Optional[KnowledgeLoader] = None,
        policy: Optional[PolicyEngine] = None,
        oem_service: Optional[OEMService] = None,
    ):
        self._provider = provider
        self._executor = executor or ToolExecutor()
        self._store = store or ZoraMemoryStore()
        self._knowledge = knowledge or KnowledgeLoader()
        self._policy = policy or PolicyEngine()
        self._oem_service = oem_service or OEMService()
        self._router = RouterAgent(self._policy)
        self._research = ResearchService(self._knowledge, self._policy, self._executor)
        self._concierge = ConciergeAgent()
        self._agents = {
            "WindowsAgent": WindowsAgent(),
            "FilesAgent": FilesAgent(),
            "OEMAgent": OEMAgent(),
            "BrowserSupportAgent": BrowserSupportAgent(),
            "DesktopNavigationAgent": DesktopNavigationAgent(),
            "SupportCaseAgent": SupportCaseAgent(),
            "SmartHomeAgent": SmartHomeAgent(),
        }
        self._active_plans: Dict[str, ExecutionPlan] = {}
        self._confirmed_steps: Dict[str, Set[str]] = {}
        # Per-task ask_user state: task_id → {step_id → {field_name, value}}.
        # ``value`` is None until the user submits it; resume_with_input() fills
        # it in and execute_plan() picks it up on the next pass.
        self._user_inputs: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # Per-task previous-step results: task_id → {step_id → result dict}.
        # Feeds the ``prev.<step_id>`` namespace that Phase 5 skip_if
        # expressions read from.
        self._prev_results: Dict[str, Dict[str, Dict[str, Any]]] = {}

    async def plan_task(self, message: str) -> ExecutionPlan:
        profile = self._oem_service.detect_profile()
        self._store.save_profile(profile.to_dict())

        intent = self._router.build_intent(message, profile)
        route = self._router.route(message, profile)
        research = await self._research.gather(intent, route, profile)
        specialist = self._agents[route.agent_name]
        if research.playbook_steps:
            steps = await specialist.hydrate_steps(
                research.playbook_steps, intent, route, research, profile
            )
            if not steps:
                steps = await specialist.build_steps(intent, route, research, profile)
        else:
            steps = await specialist.build_steps(intent, route, research, profile)
        consent_gates = self._policy.build_consent_gates(steps)
        case_record = None
        if route.agent_name == "SupportCaseAgent":
            selected = research.selected
            case_record = CaseRecord(
                case_id=f"CASE-{uuid.uuid4().hex[:8].upper()}",
                issue_summary=intent.normalized_goal,
                portal_url=selected.url if selected else "",
                source_url=selected.url if selected else "",
            )

        task_id = f"task-{uuid.uuid4().hex[:12]}"
        plan = ExecutionPlan(
            task_id=task_id,
            summary="",
            intent=intent,
            route=route,
            steps=steps,
            research=research,
            oem_profile=profile,
            consent_gates=consent_gates,
            sources=research.candidates[:5],
            case_record=case_record,
            auto_execute=self._policy.can_auto_execute(steps, [source.to_dict() for source in research.candidates[:5]]),
        )
        plan.summary = await self._concierge.summarize(plan, provider=self._provider)
        self._active_plans[task_id] = plan
        self._confirmed_steps.setdefault(task_id, set())
        self._save_plan(plan)
        return plan

    def get_plan(self, task_id: str) -> Optional[ExecutionPlan]:
        if task_id in self._active_plans:
            return self._active_plans[task_id]
        stored = self._store.load_plan(task_id)
        if not stored:
            return None
        plan = ExecutionPlan.from_dict(stored)
        self._active_plans[task_id] = plan
        self._confirmed_steps.setdefault(task_id, set())
        return plan

    def confirm_step(self, task_id: str, step_id: str) -> Optional[ExecutionPlan]:
        plan = self.get_plan(task_id)
        if not plan:
            return None
        self._confirmed_steps.setdefault(task_id, set()).add(step_id)
        for gate in plan.consent_gates:
            if gate.step_id == step_id:
                gate.status = "approved"
        self._store.record_consent(task_id, step_id, "approved", "User confirmed step", self._now())
        self._save_plan(plan)
        return plan

    def resume_with_input(
        self, task_id: str, step_id: str, value: Any
    ) -> Optional[ExecutionPlan]:
        """Record a user's answer to an ``ask_user`` step so the plan can resume.

        Also mirrors the value into the persistent user profile under the
        field name the step declared, so later steps that reference
        ``{user.<field_name>}`` can pick it up.
        """
        plan = self.get_plan(task_id)
        if not plan:
            return None
        task_inputs = self._user_inputs.setdefault(task_id, {})
        pending = task_inputs.get(step_id) or {}
        pending["value"] = value
        task_inputs[step_id] = pending
        field_name = pending.get("field_name")
        if field_name:
            # Persist through the same tool the playbooks can read from.
            # Defensively tolerate fake executors used in tests.
            profile_set = getattr(self._executor, "_tool_user_profile_set", None)
            if callable(profile_set):
                try:
                    profile_set({"field": field_name, "value": value})
                except Exception:
                    pass
        for step in plan.steps:
            if step.step_id == step_id and step.status == "awaiting_user_input":
                step.status = "completed"
        plan.status = "running"
        self._save_plan(plan)
        return plan

    def cancel_task(self, task_id: str) -> Optional[ExecutionPlan]:
        plan = self.get_plan(task_id)
        if not plan:
            return None
        plan.status = "cancelled"
        self._save_plan(plan)
        return plan

    async def handle_message_stream(self, message: str) -> AsyncIterator[Dict]:
        plan = await self.plan_task(message)
        yield {"type": "tool_call", "name": "RouterAgent", "arguments": {"message": message}}
        yield {"type": "tool_result", "name": "RouterAgent", "result": plan.route.to_dict()}
        yield {"type": "tool_call", "name": "ResearchAgent", "arguments": {"query": plan.research.query}}
        yield {"type": "tool_result", "name": "ResearchAgent", "result": plan.research.to_dict()}
        yield {"type": "tool_call", "name": plan.route.agent_name, "arguments": {"task_id": plan.task_id}}
        yield {"type": "tool_result", "name": plan.route.agent_name, "result": {
            "summary": plan.summary,
            "steps": [step.to_dict() for step in plan.steps],
            "task_id": plan.task_id,
            "auto_execute": plan.auto_execute,
        }}
        yield {"type": "text", "content": plan.summary}
        if plan.auto_execute:
            async for event in self.execute_plan(plan.task_id, emit_done=False, include_headers=False):
                yield event
        else:
            yield {
                "type": "text",
                "content": f"Plan ready as {plan.task_id}. I will stop before sensitive actions unless you confirm them.",
            }
        yield {"type": "done"}

    async def execute_plan(
        self,
        task_id: str,
        emit_done: bool = True,
        include_headers: bool = True,
    ) -> AsyncIterator[Dict]:
        plan = self.get_plan(task_id)
        if not plan:
            if emit_done:
                yield {"type": "text", "content": f"Task {task_id} was not found."}
                yield {"type": "done"}
            return

        if include_headers:
            yield {"type": "tool_call", "name": plan.route.agent_name, "arguments": {"task_id": task_id}}
            yield {"type": "tool_result", "name": plan.route.agent_name, "result": {"summary": plan.summary}}

        for step in plan.steps:
            if step.status == "completed":
                continue

            # Phase 5: skip_if — evaluate the expression against prev/user/
            # oem/intent namespaces and skip the step if truthy. Failures
            # here are intentionally quiet: if an expression can't evaluate,
            # we default to executing the step so the user is never silently
            # skipped through something important.
            if step.skip_if and self._should_skip_step(step, plan, task_id):
                step.status = "skipped"
                self._save_plan(plan)
                yield {
                    "type": "tool_result",
                    "name": step.tool_name or step.agent_name,
                    "result": {"skipped": True, "reason": f"skip_if: {step.skip_if}"},
                }
                continue

            if step.manual_gate or step.requires_confirmation or step.irreversible:
                approved = step.step_id in self._confirmed_steps.get(task_id, set())
                if not approved:
                    step.status = "awaiting_confirmation"
                    plan.status = "awaiting_confirmation"
                    self._store.record_consent(task_id, step.step_id, "pending", step.description, self._now())
                    self._save_plan(plan)
                    yield {
                        "type": "consent_request",
                        "task_id": task_id,
                        "step_id": step.step_id,
                        "title": step.title,
                        "reason": step.description,
                    }
                    if emit_done:
                        yield {"type": "done"}
                    return

            yield {"type": "tool_call", "name": step.tool_name or step.agent_name, "arguments": step.tool_args}

            # Phase 5: retry loop. Retries only kick in on error results,
            # and only for regular tool steps (not ask_user sentinels).
            attempts = 0
            max_attempts = max(1, int(step.retry or 0) + 1)
            result: Dict[str, Any] = {}
            while attempts < max_attempts:
                attempts += 1
                result = await self._execute_step(step, task_id=task_id)
                if not result.get("error") or attempts >= max_attempts:
                    break

            if result.get("error"):
                if step.continue_on_error:
                    step.status = "failed_continued"
                    self._save_plan(plan)
                    yield {
                        "type": "tool_result",
                        "name": step.tool_name or step.agent_name,
                        "result": {**result, "continue_on_error": True},
                    }
                    # Still record in prev so later skip_if can branch on it.
                    self._prev_results.setdefault(task_id, {})[step.step_id] = result
                    continue

                step.status = "failed"
                plan.status = "blocked"
                self._save_plan(plan)
                yield {"type": "tool_result", "name": step.tool_name or step.agent_name, "result": result}
                yield {"type": "text", "content": f"I got blocked on '{step.title}': {result['error']}"}
                if emit_done:
                    yield {"type": "done"}
                return

            # ask_user sentinel — pause the plan and emit a user_input_request
            # event. resume_with_input() writes the answer back, then the next
            # execute_plan pass picks it up as a completed step.
            if result.get("status") == "awaiting_user_input":
                field_name = result.get("field_name") or "answer"
                prompt = result.get("prompt") or step.description
                step.status = "awaiting_user_input"
                plan.status = "awaiting_user_input"
                self._user_inputs.setdefault(task_id, {})[step.step_id] = {
                    "field_name": field_name,
                    "prompt": prompt,
                    "value": None,
                }
                self._save_plan(plan)
                event = {
                    "type": "user_input_request",
                    "task_id": task_id,
                    "step_id": step.step_id,
                    "field_name": field_name,
                    "prompt": prompt,
                }
                # Phase 5: select_from_list extends the pause event with a
                # ``choices`` list and a ``kind`` discriminator so the UI
                # can render a radio-list card instead of a text field.
                if result.get("choices"):
                    event["choices"] = result["choices"]
                if result.get("kind"):
                    event["kind"] = result["kind"]
                yield event
                if emit_done:
                    yield {"type": "done"}
                return

            step.status = "completed"
            plan.status = "running"
            self._prev_results.setdefault(task_id, {})[step.step_id] = result
            self._save_plan(plan)
            yield {"type": "tool_result", "name": step.tool_name or step.agent_name, "result": result}

        plan.status = "completed"
        self._save_plan(plan)
        yield {"type": "text", "content": f"Finished task {task_id}. {len(plan.steps)} step(s) completed."}
        if emit_done:
            yield {"type": "done"}

    async def _execute_step(self, step, task_id: Optional[str] = None):
        if step.kind == "manual":
            return {"status": "manual_gate", "message": step.description}
        if not step.tool_name:
            return {"status": "noop", "message": step.description}
        # Late-binding substitution for values collected during the run
        # (ask_user answers stored in _user_inputs + user_profile JSON).
        # Steps that hydrated with {user.<field>} placeholders get resolved
        # here so later steps can consume inputs that didn't exist at
        # plan-creation time.
        resolved_args = self._resolve_late_placeholders(step.tool_args, task_id)
        return await self._executor.execute(step.tool_name, resolved_args)

    def _should_skip_step(
        self, step, plan: ExecutionPlan, task_id: Optional[str]
    ) -> bool:
        """Evaluate the step's ``skip_if`` expression in a sandboxed context.

        The expression gets four root namespaces:
          • prev   — {step_id → tool_result dict} from already-run steps
          • user   — persisted user profile + ask_user answers
          • oem    — the plan's OEM profile dict
          • intent — the plan's TaskIntent dict

        We use simpleeval to avoid exec/eval — only literals, comparisons,
        boolean ops, and attribute/subscript access are allowed. Any error
        evaluates to "don't skip" so the user never gets silently skipped.
        """
        expression = (step.skip_if or "").strip()
        if not expression:
            return False
        try:
            from simpleeval import SimpleEval  # type: ignore
        except Exception:
            return False

        prev_ns = dict(self._prev_results.get(task_id or "", {})) if task_id else {}
        user_ns: Dict[str, Any] = {}
        # Per-task ask_user answers take precedence over persisted profile.
        if task_id and task_id in self._user_inputs:
            for info in self._user_inputs[task_id].values():
                field = info.get("field_name")
                value = info.get("value")
                if field and value is not None:
                    user_ns[field] = value
        loader = getattr(self._executor, "_load_user_profile", None)
        if callable(loader):
            try:
                for key, value in (loader() or {}).items():
                    user_ns.setdefault(key, value)
            except Exception:
                pass

        names = {
            "prev": _DotDict(prev_ns),
            "user": _DotDict(user_ns),
            "oem": _DotDict(plan.oem_profile.to_dict()),
            "intent": _DotDict(plan.intent.to_dict()),
        }
        try:
            evaluator = SimpleEval(names=names)
            return bool(evaluator.eval(expression))
        except Exception:
            return False

    def _resolve_late_placeholders(
        self, tool_args: Dict[str, Any], task_id: Optional[str]
    ) -> Dict[str, Any]:
        """Re-run placeholder substitution with a ``user.*`` namespace.

        Reads:
          - per-task ``ask_user`` answers from ``self._user_inputs[task_id]``
          - the persistent user profile JSON via the executor
        """
        if not tool_args:
            return tool_args
        namespace: Dict[str, Any] = {}
        # Per-task ask_user values (keyed by field_name for convenience).
        if task_id and task_id in self._user_inputs:
            for step_id, info in self._user_inputs[task_id].items():
                field = info.get("field_name")
                value = info.get("value")
                if field and value is not None:
                    namespace[f"user.{field}"] = value
        # Persisted profile fields as fallback.
        loader = getattr(self._executor, "_load_user_profile", None)
        if callable(loader):
            try:
                for key, value in (loader() or {}).items():
                    namespace.setdefault(f"user.{key}", value)
            except Exception:
                pass
        if not namespace:
            return tool_args
        safe = SafeDict(namespace)
        return _substitute(tool_args, safe)

    # --- Phase 4b: follow-up scheduler -----------------------------------

    def check_follow_ups(self) -> list[Dict[str, Any]]:
        """Return every open case with at least one follow-up whose due_at
        has passed. Each entry includes the matching follow-ups so callers
        can surface them in the UI or fire notifications.
        """
        now_iso = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        due: list[Dict[str, Any]] = []
        for case in self._store.list_open_cases():
            matching = []
            for item in case.get("follow_ups", []) or []:
                status = (item.get("status") or "open").lower()
                due_at = item.get("due_at") or ""
                if status != "open" or not due_at:
                    continue
                if due_at <= now_iso:
                    matching.append(item)
            if matching:
                due.append({"case": case, "due_follow_ups": matching})
        return due

    def resolve_follow_up(self, case_id: str, follow_up_title: str) -> Optional[Dict[str, Any]]:
        """Mark a named follow-up on a case as resolved."""
        case = self._store.get_case(case_id)
        if not case:
            return None
        changed = False
        for item in case.get("follow_ups", []) or []:
            if item.get("title") == follow_up_title and item.get("status") != "resolved":
                item["status"] = "resolved"
                changed = True
        if changed:
            self._store.update_case(case_id, case)
        return case

    async def fire_due_follow_up_notifications(self) -> int:
        """Background lifespan task helper: notify on every due follow-up.

        Returns the number of notifications fired. Safe to call on a timer —
        each due follow-up only fires once per due-date tick because firing
        implies the user saw the pill in the UI and will resolve it manually.
        """
        due = self.check_follow_ups()
        notify = getattr(self._executor, "_tool_notify", None)
        fired = 0
        if not callable(notify):
            return 0
        for entry in due:
            case = entry["case"]
            for item in entry["due_follow_ups"]:
                try:
                    notify({
                        "title": f"Follow-up: {case.get('case_id', '')}",
                        "message": f"{item.get('title', 'Follow-up due')} — {case.get('issue_summary', '')}",
                    })
                    fired += 1
                except Exception:
                    pass
        return fired

    def oem_snapshot(self) -> Dict:
        profile = self._oem_service.detect_profile()
        self._store.save_profile(profile.to_dict())
        return profile.to_dict()

    def knowledge_version(self) -> Dict:
        return self._knowledge.current_version()

    def _save_plan(self, plan: ExecutionPlan) -> None:
        self._active_plans[plan.task_id] = plan
        self._store.save_plan(
            plan.task_id,
            plan.intent.raw_message,
            plan.route.agent_name,
            plan.status,
            plan.created_at,
            plan.to_dict(),
        )

    def _now(self) -> str:
        return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

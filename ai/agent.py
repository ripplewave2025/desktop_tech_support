"""
Zora Agent — the AI reasoning loop.

Takes user messages, calls the AI provider with tool definitions,
executes tool calls, feeds results back, and loops until the AI
produces a final text response. This is the brain of Zora.
"""

import json
import logging
from typing import List, Dict, Any, Optional, AsyncIterator, Callable

from .providers import AIProvider, AIMessage, AIResponse, ToolCall
from .tools import TOOL_DEFINITIONS, get_tools_for_model
from .tool_executor import ToolExecutor

logger = logging.getLogger("zora.agent")

SYSTEM_PROMPT = """\
You are Zora — a sharp, friendly AI desktop companion for Windows PCs.
You're the tech-savvy friend everyone wishes they had. Proactive, humble, and you drop a pun when the moment's right.

## Personality
- Warm, confident, approachable — never robotic, never condescending
- Simple, clear English. No jargon unless explaining it
- Puns when it fits: "Your Wi-Fi's back! Connection therapy for the win."
- NARRATE LIVE: "Opening Settings... ✅ Checking for updates... ✅"
- Celebrate wins, be honest when stuck
- Keep messages short — 2-4 lines max
- Be proactive: fix things before the user even asks

## Your Tools

### See & Control the Screen
- `screenshot_and_analyze` — See what's on screen via vision AI
- `read_screen` / `find_text_on_screen` — OCR text and locate elements
- `mouse_click` / `mouse_move` / `mouse_scroll` — Mouse control
- `type_text` / `press_hotkey` — Keyboard input

### Apps & Windows
- `list_windows` / `focus_window` — Manage open windows
- `launch_app` — Open any application
- `open_url` — Open websites in default browser
- `safe_op` — **PREFERRED** way to do system tasks. Pick an op_id like
  `net.flush_dns`, `service.restart`, `sys.disk_health`, `defender.scan_quick`,
  `repair.sfc`. Call `safe_op_list` to see all. This is safer than
  `run_powershell` because parameters are validated server-side.
- `run_powershell` — FALLBACK only when no `safe_op` covers the task

### OEM Driver / BIOS Updates (Dell, HP, Lenovo)
When the user says "update my drivers", "check for updates", "my computer is
out of date", or similar — DO NOT manually open Device Manager and click
around. Use the OEM's own tool:
- `oem_detect` — find out if this is a Dell/HP/Lenovo and which tool is installed
- `oem_scan_drivers` — read-only scan for pending updates (uses dcu-cli /
  HPImageAssistant / ThinInstaller in silent mode)
- `oem_apply_drivers` — install pending updates (DEFAULTS TO DRY-RUN; you
  MUST confirm with the user and then call again with `dry_run=false`)
If the machine isn't Dell/HP/Lenovo, `oem_*` returns a support URL instead.

### Diagnostics & Fixes
- `run_diagnostic` — Scan 8 categories (internet, audio, printer, display, hardware, software, files, security)
- `apply_fix` / `apply_remediation` — Auto-fix issues (52 structured fixes)
- `run_flow_diagnostic` — Decision-tree diagnostics like real tech support
- `change_windows_setting` — WiFi, updates, power, dark mode, bluetooth, etc.

### Desktop Assistant
- `send_email` — Draft emails via Outlook or default mail client
- `manage_files` — Move, copy, rename, find, organize files by type
- `clipboard` — Read/write system clipboard
- `remember` — Save notes, reminders, follow-ups across sessions
- `notify` — Show Windows notification toasts

### System & Support
- `get_system_info` — CPU, RAM, disk, uptime
- `list_processes` / `kill_process` — Manage running programs
- `web_search` — Search the web for solutions
- `create_support_ticket` — Draft support tickets with diagnostics
- `download_tool` — Download open-source tools from GitHub if needed
- `highlight_screen_area` — Point things out on screen

## How to Use the Computer
1. `screenshot_and_analyze` — LOOK first
2. Decide what to click/type
3. `mouse_click` or `type_text` to act
4. Screenshot again to VERIFY
5. Tell the user what happened

## How to Help Non-Technical Users
- Never assume they know tech terms — explain everything simply
- When they say "my computer is slow," run diagnostics automatically
- When they say "help me with email," use `send_email` to draft it
- When they say "organize my files," use `manage_files` with organize_by_type
- When they say "remind me," use `remember` to save it
- When they need software help, look at their screen and guide them step by step
- When you can't fix something, create a support ticket or open the vendor's support page
- For third-party apps: screenshot → understand the UI → click through it for them

## Important Rules
1. ALWAYS screenshot first — look before you leap
2. Chain: see → act → verify → report
3. Ask confirmation before: killing processes, deleting files, changing settings
4. Never touch System32 or protected system files
5. If admin needed: "Right-click Zora → 'Run as administrator' for this one."
6. Microsoft/Store issues → create_support_ticket
7. Save important findings with `remember` for follow-up

## Response Style
- Short, clear, human. 2-4 lines max
- ✅ ❌ ⏳ 🔍 emojis naturally
- "One sec..." not "Please wait while I process your request"
- "Done!" not "The operation has been completed successfully"
- End tasks with "Anything else?" or "What's next?"
"""

MAX_TOOL_ROUNDS = 10

# ── Expert-mode addendum ────────────────────────────────────────
# Appended to SYSTEM_PROMPT when the user has flipped on power-user mode.
# Does NOT replace the prompt — the personality and consent rules still
# apply. It just changes the *delivery* and unlocks deeper diagnostics.
EXPERT_MODE_ADDENDUM = """\

## EXPERT MODE — Power User

The user has explicitly enabled expert mode in settings. They know Windows
internals; they want a smart copilot, not training wheels.

Adjust your behavior:

- **Use technical terms freely.** "Bugcheck 0x7E in nvlddmkm.sys", not
  "your PC crashed because of a graphics driver issue." Both are fine, but
  lead with the precise term.
- **Show raw output, not summaries, when asked.** If you ran `safe_op` and
  the user asks "what did it return?", paste the stdout in a code block.
  Don't paraphrase unless they ask.
- **Suggest deeper diagnostics.** Reach for Event Viewer queries, DISM,
  bcdedit, Reliability Monitor, PowerShell `Get-WinEvent` filters, and
  raw `safe_op` calls. In novice mode you'd open Settings; here, suggest
  the registry path or the cmdlet.
- **Show risk levels.** When proposing a `safe_op`, mention the risk tier
  ("read", "write", "dangerous") so the user can decide whether they want
  the consent gate or to skip ahead.
- **Less hand-holding language.** Drop "Anything else?" and "One sec...".
  Be direct: "Done. SFC reports no integrity violations." Move on.
- **Link KB articles.** When a fix has a Microsoft KB or vendor article,
  cite the URL inline so the user can go deeper.

Security gates and irreversible-action confirmations STILL apply — expert
mode does not bypass safety, only friction.
"""


class ZoraAgent:
    """The agent loop: AI reasoning + tool execution + conversation management."""

    def __init__(
        self,
        provider: AIProvider,
        executor: Optional[ToolExecutor] = None,
        system_prompt: Optional[str] = None,
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
        expert_mode: bool = False,
    ):
        self._provider = provider
        self._executor = executor or ToolExecutor()
        self._max_rounds = max_tool_rounds
        self._expert_mode = bool(expert_mode)
        # Build the effective prompt: caller-supplied OR built-in SYSTEM_PROMPT,
        # then append the expert addendum if power-user mode is on. We
        # append rather than replace so the same personality + safety
        # constraints stay in force regardless of mode.
        base_prompt = system_prompt or SYSTEM_PROMPT
        if self._expert_mode:
            self._system_prompt = base_prompt + EXPERT_MODE_ADDENDUM
        else:
            self._system_prompt = base_prompt
        # Tool selection now also factors in expert mode — power users get
        # the full catalog regardless of whether their model is "small".
        self._tools = get_tools_for_model(provider.name(), expert_mode=self._expert_mode)
        logger.info(
            f"Agent initialized: {provider.name()} with {len(self._tools)} tools "
            f"(expert_mode={self._expert_mode})"
        )
        self._conversation: List[AIMessage] = [
            AIMessage(role="system", content=self._system_prompt)
        ]

    @property
    def expert_mode(self) -> bool:
        return self._expert_mode

    async def chat(
        self,
        user_message: str,
        on_tool_call: Optional[Callable] = None,
        on_tool_result: Optional[Callable] = None,
    ) -> str:
        """Process a user message through the full agent loop.

        Args:
            user_message: The user's text input
            on_tool_call: callback(tool_name, arguments) for UI progress updates
            on_tool_result: callback(tool_name, result) for UI result updates

        Returns:
            The final assistant response text.
        """
        self._conversation.append(
            AIMessage(role="user", content=user_message)
        )

        for round_num in range(self._max_rounds):
            logger.debug(f"Agent round {round_num + 1}/{self._max_rounds}")

            response = await self._provider.chat(
                messages=self._conversation,
                tools=self._tools,
                temperature=0.4,
            )

            assistant_msg = response.message
            self._conversation.append(assistant_msg)

            # If no tool calls, we're done — return the text response
            if response.finish_reason == "stop" or not assistant_msg.tool_calls:
                logger.debug(f"Agent done after {round_num + 1} rounds")
                return assistant_msg.content

            # Execute each tool call
            for tool_call in assistant_msg.tool_calls:
                logger.info(f"Tool call: {tool_call.name}({tool_call.arguments})")

                if on_tool_call:
                    try:
                        on_tool_call(tool_call.name, tool_call.arguments)
                    except Exception:
                        pass

                result = await self._executor.execute(
                    tool_call.name, tool_call.arguments
                )

                logger.debug(f"Tool result: {tool_call.name} -> {json.dumps(result, default=str)[:200]}")

                if on_tool_result:
                    try:
                        on_tool_result(tool_call.name, result)
                    except Exception:
                        pass

                # Add tool result to conversation
                self._conversation.append(AIMessage(
                    role="tool",
                    content=json.dumps(result, default=str),
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                ))

        # Exhausted rounds — ask AI for a summary
        self._conversation.append(AIMessage(
            role="user",
            content="Please summarize what you've found and done so far.",
        ))
        response = await self._provider.chat(
            messages=self._conversation,
            temperature=0.4,
        )
        self._conversation.append(response.message)
        return response.message.content

    async def chat_stream(
        self,
        user_message: str,
        on_tool_call: Optional[Callable] = None,
        on_tool_result: Optional[Callable] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Streaming version — yields event dicts for real-time UI.

        Strategy: Use non-streaming for tool-call rounds (need structured response),
        then stream only the final text response (better UX). If provider fails
        with tools, fallback to streaming without tools.

        Event types:
            {"type": "tool_call", "name": str, "arguments": dict}
            {"type": "tool_result", "name": str, "result": dict}
            {"type": "text", "content": str}
            {"type": "done"}
        """
        self._conversation.append(
            AIMessage(role="user", content=user_message)
        )

        for round_num in range(self._max_rounds):
            # Non-streaming call to check for tool calls
            try:
                response = await self._provider.chat(
                    messages=self._conversation,
                    tools=self._tools,
                    temperature=0.4,
                )
            except Exception as e:
                logger.error(f"Provider chat failed (round {round_num}): {type(e).__name__}: {e}")
                response = None

            if response is None:
                # Provider failed — stream without tools as last resort
                try:
                    streamed_text = ""
                    async for chunk in self._provider.chat_stream(
                        messages=self._conversation,
                        temperature=0.4,
                    ):
                        streamed_text += chunk
                        yield {"type": "text", "content": chunk}
                    if streamed_text:
                        self._conversation.append(
                            AIMessage(role="assistant", content=streamed_text)
                        )
                except Exception as e2:
                    logger.error(f"Streaming also failed: {type(e2).__name__}: {e2}")
                    yield {"type": "text", "content": "I'm having trouble connecting to the AI engine. Make sure Ollama is running!"}
                yield {"type": "done"}
                return

            assistant_msg = response.message
            self._conversation.append(assistant_msg)

            if response.finish_reason == "stop" or not assistant_msg.tool_calls:
                # Final text response — yield it directly (no double-call)
                if assistant_msg.content:
                    yield {"type": "text", "content": assistant_msg.content}
                yield {"type": "done"}
                return

            # Execute tools and yield events
            for tool_call in assistant_msg.tool_calls:
                yield {
                    "type": "tool_call",
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                }

                result = await self._executor.execute(
                    tool_call.name, tool_call.arguments
                )

                yield {
                    "type": "tool_result",
                    "name": tool_call.name,
                    "result": result,
                }

                self._conversation.append(AIMessage(
                    role="tool",
                    content=json.dumps(result, default=str),
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                ))

        yield {"type": "text", "content": "I've been working on this for a while. Let me know if you'd like me to continue."}
        yield {"type": "done"}

    def reset_conversation(self):
        """Clear conversation history, keep system prompt."""
        self._conversation = [self._conversation[0]]

    def get_conversation_history(self) -> List[Dict]:
        """Return conversation as serializable dicts (user + assistant only)."""
        return [
            {"role": m.role, "content": m.content}
            for m in self._conversation
            if m.role in ("user", "assistant") and m.content
        ]

    @property
    def provider_name(self) -> str:
        return self._provider.name()

    @property
    def conversation_length(self) -> int:
        return len(self._conversation)

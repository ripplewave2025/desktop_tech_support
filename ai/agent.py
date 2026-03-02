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
You are Zora — a sharp, friendly, slightly witty AI desktop companion for Windows PCs.
Think of yourself as that one tech-savvy friend everyone wishes they had. You're proactive, you're humble, and you occasionally drop a good pun because life's too short for boring error messages.

## Your Personality (non-negotiable)
- Warm, confident, approachable — never robotic, never condescending
- Speak simple, clear English. No jargon unless explaining it.
- Throw in a pun or joke when the moment's right:
  "Your Wi-Fi's back! Guess it just needed a little... connection therapy."
  "Found 47GB of temp files. Your PC was basically hoarding digital dust bunnies."
- TALK WHILE ACTING — narrate every step live:
  "Opening Settings... done ✅ Heading to Update & Security... ✅ Checking for updates now..."
- Celebrate wins: "All fixed! ✅ Your printer lives to print another day."
- Be honest when stuck: "This one's above my pay grade — let me draft a support ticket for you."
- Think ahead — don't wait to be asked, just do it
- Keep messages short and punchy — 2-4 lines max, no essays
- Be proactive: if you notice something off while fixing something else, mention it

## Your Capabilities (Computer Use)
You have FULL control of the PC through these tools:

### See & Understand the Screen
- `screenshot_and_analyze` — Take a screenshot, send to vision AI, understand what's on screen
- `read_screen` — OCR: extract all visible text from screen or a region
- `find_text_on_screen` — Find exact pixel location of text on screen

### Control Mouse & Keyboard
- `mouse_click` — Click at exact coordinates (left/right/double click)
- `mouse_move` — Move mouse to coordinates
- `mouse_scroll` — Scroll up/down
- `type_text` — Type text into focused field
- `press_hotkey` — Press keyboard shortcuts (Ctrl+C, Win+R, etc.)

### Windows & Apps
- `list_windows` — See all open windows
- `focus_window` — Switch to a window by title
- `launch_app` — Open any application
- `run_powershell` — Run system commands (safe ones only)

### Diagnostics & Fixes
- `run_diagnostic` — Scan: printer, audio, internet, display, hardware, software, files, security
- `apply_fix` — Auto-fix detected issues
- `change_windows_setting` — Change Windows settings safely (WiFi, updates, power, dark mode, etc.)

### System
- `get_system_info` — CPU, RAM, disk, uptime
- `list_processes` / `kill_process` — Manage running programs
- `highlight_screen_area` — Draw a temporary colored box on screen to point something out

### Support
- `create_support_ticket` — Draft a Microsoft support ticket with diagnostics + screenshots

## HOW TO USE COMPUTER (step by step)
When the user asks you to do something on screen:
1. `screenshot_and_analyze` — SEE what's currently on screen
2. Decide what to click/type based on the description
3. `mouse_click` or `type_text` to interact
4. Screenshot again to VERIFY the action worked
5. Tell the user what happened in plain English

## Important Rules
1. ALWAYS screenshot first before acting — look before you leap
2. Chain tools: see → act → verify → report
3. After a fix, verify it actually worked
4. Never touch System32 or protected system files
5. Ask confirmation before: killing processes, deleting files, changing system settings
6. If admin privileges needed: "You'll need to right-click Zora and pick 'Run as administrator' for this one."
7. Microsoft account/Store issues → offer to create a support ticket

## Response Style
- Short, clear, human. 2-4 lines max.
- Use ✅ ❌ ⏳ 🔍 emojis naturally
- Say "One sec..." not "Please wait while I process your request"
- Say "Done!" not "The operation has been completed successfully"
- Puns are welcome, cringe is not. Keep it clever.
- End completed tasks with "Anything else?" or "What's next?"
"""

MAX_TOOL_ROUNDS = 10


class ZoraAgent:
    """The agent loop: AI reasoning + tool execution + conversation management."""

    def __init__(
        self,
        provider: AIProvider,
        executor: Optional[ToolExecutor] = None,
        system_prompt: Optional[str] = None,
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
    ):
        self._provider = provider
        self._executor = executor or ToolExecutor()
        self._max_rounds = max_tool_rounds
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        # Auto-select tool set based on model size
        self._tools = get_tools_for_model(provider.name())
        logger.info(f"Agent initialized: {provider.name()} with {len(self._tools)} tools")
        self._conversation: List[AIMessage] = [
            AIMessage(role="system", content=self._system_prompt)
        ]

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

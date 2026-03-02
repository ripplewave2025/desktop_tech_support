"""
Tool definitions for the Zora AI Agent.

Each tool maps to an existing capability in the codebase.
Definitions use OpenAI function-calling JSON Schema format;
each provider converts as needed.
"""

# Available diagnostic categories (mirrors cli/main.py DIAGNOSTIC_MODULES)
DIAGNOSTIC_CATEGORIES = [
    "printer", "internet", "software", "hardware",
    "files", "display", "audio", "security",
]

# ─── Vision model for screen understanding ─────────────────
VISION_MODEL = "moondream"

# ─── Core tools for small models (3b-7b) ───────────────────
# Keeps the token count low so small models don't time out
CORE_TOOL_NAMES = {
    "get_system_info", "run_diagnostic", "apply_fix",
    "change_windows_setting", "run_powershell",
    "screenshot_and_analyze",
    "run_flow_diagnostic", "apply_remediation",
}

TOOL_DEFINITIONS = [
    # ─── Computer Use: Vision ─────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "screenshot_and_analyze",
            "description": (
                "Take a screenshot of the screen and analyze it with the vision AI. "
                "Returns a text description of what is visible on screen. "
                "ALWAYS call this before trying to click or interact with anything."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "What to look for in the screenshot. Examples: "
                            "'Describe what is on screen', "
                            "'Where is the Settings button?', "
                            "'What error message is showing?'"
                        ),
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_text_on_screen",
            "description": (
                "Find the exact pixel location of specific text on screen using OCR. "
                "Returns coordinates (x, y, width, height) of each match. "
                "Use this to find buttons, labels, or menu items before clicking."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to search for on screen (case-insensitive)",
                    },
                },
                "required": ["text"],
            },
        },
    },
    # ─── Computer Use: Mouse ──────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "mouse_click",
            "description": (
                "Click at specific screen coordinates. "
                "Use screenshot_and_analyze or find_text_on_screen first to find coordinates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate (pixels from left)"},
                    "y": {"type": "integer", "description": "Y coordinate (pixels from top)"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "double"],
                        "description": "Click type (default: left)",
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_move",
            "description": "Move mouse cursor to specific coordinates without clicking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_scroll",
            "description": "Scroll the mouse wheel up or down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Scroll direction",
                    },
                    "clicks": {
                        "type": "integer",
                        "description": "Number of scroll ticks (default: 3)",
                    },
                },
                "required": ["direction"],
            },
        },
    },
    # ─── Computer Use: Screen Highlight ───────────────────────
    {
        "type": "function",
        "function": {
            "name": "highlight_screen_area",
            "description": (
                "Draw a temporary colored rectangle on screen to show the user "
                "what you are looking at or about to click. Disappears after 2 seconds."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Left edge X"},
                    "y": {"type": "integer", "description": "Top edge Y"},
                    "width": {"type": "integer", "description": "Box width"},
                    "height": {"type": "integer", "description": "Box height"},
                    "color": {
                        "type": "string",
                        "enum": ["red", "green", "blue", "yellow"],
                        "description": "Box color (default: red)",
                    },
                },
                "required": ["x", "y", "width", "height"],
            },
        },
    },
    # ─── Windows Settings ─────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "change_windows_setting",
            "description": (
                "Change a Windows setting safely via PowerShell. "
                "Supports: wifi_connect, wifi_disconnect, check_updates, "
                "set_power_plan (balanced/high_performance/power_saver), "
                "toggle_bluetooth, open_device_manager, open_settings_page, "
                "set_default_browser, enable_dark_mode, disable_dark_mode, "
                "set_volume, toggle_firewall."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "setting": {
                        "type": "string",
                        "description": "Setting name (e.g. 'check_updates', 'set_power_plan')",
                    },
                    "value": {
                        "type": "string",
                        "description": "Value for the setting (if applicable)",
                    },
                },
                "required": ["setting"],
            },
        },
    },
    # ─── Support Ticket ───────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_support_ticket",
            "description": (
                "Create a support ticket draft with system diagnostics, screenshots, "
                "and issue description. Saves to a local file and optionally opens "
                "Microsoft support page. Use when the issue needs human/Microsoft intervention."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_summary": {
                        "type": "string",
                        "description": "Short description of the issue",
                    },
                    "steps_tried": {
                        "type": "string",
                        "description": "What Zora already tried to fix",
                    },
                },
                "required": ["issue_summary"],
            },
        },
    },
    # ─── Original tools below ─────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "run_diagnostic",
            "description": (
                "Run a diagnostic scan for a specific category on the user's PC. "
                "Returns a list of checks performed with their status (ok/warning/error) "
                "and whether an automatic fix is available. Always run this before "
                "telling the user what's wrong."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": DIAGNOSTIC_CATEGORIES,
                        "description": "The diagnostic category to scan",
                    }
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_fix",
            "description": (
                "Apply an automatic fix for a specific diagnostic issue. "
                "Only call this after run_diagnostic has identified an issue "
                "with fix_available=true. Uses the exact issue name from results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": DIAGNOSTIC_CATEGORIES,
                    },
                    "issue_name": {
                        "type": "string",
                        "description": "Exact name of the issue from diagnostic results",
                    },
                },
                "required": ["category", "issue_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": (
                "Get current system resource usage: CPU percentage, RAM usage, "
                "disk space, and system uptime."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": (
                "List running processes on the system, optionally filtered by name. "
                "Returns PID, name, CPU usage, and memory usage for each."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Optional: only show processes containing this name",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": (
                "Terminate a running process by name or PID. "
                "Use with caution — only for frozen or problematic processes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_pid": {
                        "type": "string",
                        "description": "Process name or PID number",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force kill (default: false)",
                    },
                },
                "required": ["name_or_pid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_screen",
            "description": (
                "Capture a screenshot and extract all visible text via OCR. "
                "Use this to see what is currently displayed on the user's screen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "object",
                        "description": "Optional: capture only a region {left, top, width, height}",
                        "properties": {
                            "left": {"type": "integer"},
                            "top": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"},
                        },
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "List all visible windows on the desktop with their titles and handles.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "focus_window",
            "description": "Find and bring a window to the foreground by its title (partial match).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Window title or partial match",
                    }
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": (
                "Launch an application by executable name or path. "
                "Examples: 'notepad.exe', 'calc.exe', 'mspaint.exe', "
                "'C:\\\\Program Files\\\\...\\\\app.exe'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Executable name or full path",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional command-line arguments",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the currently focused window or input field.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to type",
                    }
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_hotkey",
            "description": (
                "Press a keyboard shortcut. Examples: ['ctrl', 'c'] for copy, "
                "['alt', 'F4'] to close window, ['win', 'r'] for Run dialog."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keys to press simultaneously",
                    }
                },
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_powershell",
            "description": (
                "Execute a PowerShell command and return its output. "
                "Use for Windows administration tasks like checking services, "
                "network config, registry, driver info, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "PowerShell command to execute",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for troubleshooting information, driver downloads, "
                "or solutions to specific error messages. Returns search results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    }
                },
                "required": ["query"],
            },
        },
    },
    # ─── Flow-Based Diagnostics ────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "run_flow_diagnostic",
            "description": (
                "Run a flow-based diagnostic that follows decision-tree logic "
                "like a real tech support expert. Available flows: "
                "internet_slow, no_sound, printer_not_working, slow_pc, wifi_disconnects. "
                "Each flow runs multiple checks in sequence, branching based on results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "flow_id": {
                        "type": "string",
                        "description": (
                            "The flow to run: 'internet_slow', 'no_sound', "
                            "'printer_not_working', 'slow_pc', 'wifi_disconnects'"
                        ),
                    }
                },
                "required": ["flow_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_remediation",
            "description": (
                "Apply a specific fix from the remediation library. "
                "Each fix is a tested PowerShell command with risk level and verification. "
                "Example fix IDs: dns_flush, winsock_reset, audio_service_restart, "
                "temp_cleanup, defender_quick_scan, spooler_restart, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fix_id": {
                        "type": "string",
                        "description": "ID of the fix from the remediation library",
                    }
                },
                "required": ["fix_id"],
            },
        },
    },
    # ─── Tool Auto-Download ────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "download_tool",
            "description": (
                "Download and run an open-source tool from GitHub when built-in "
                "tools aren't enough. Zora will download the tool to a temp folder, "
                "run it, and clean up afterwards. Only downloads from trusted repos. "
                "Examples: 'BleachBit/bleachbit' for disk cleanup, "
                "'henrypp/memreduct' for memory optimization, "
                "'mikeroyal/Windows-11-Guide' for registry tweaks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "GitHub repo in 'owner/repo' format",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this tool is needed (shown to user)",
                    },
                    "asset_pattern": {
                        "type": "string",
                        "description": "Filename pattern to match in releases (e.g. '*.exe', '*portable*.zip')",
                    },
                },
                "required": ["repo", "reason"],
            },
        },
    },
]


def get_tools_for_model(model_name: str = "") -> list:
    """Return appropriate tool set based on model size.

    Small models (3b, 7b) get 6 core tools to avoid timeouts.
    Large models (13b+, Claude, GPT) get the full 21 tools.
    """
    model_lower = model_name.lower()
    is_small = any(tag in model_lower for tag in ["3b", "1b", "7b", ":small", ":mini"])

    if is_small:
        return [t for t in TOOL_DEFINITIONS if t["function"]["name"] in CORE_TOOL_NAMES]
    return TOOL_DEFINITIONS

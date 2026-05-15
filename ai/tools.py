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
    # Safe-ops + OEM are first-class even for small models — they unlock the
    # "grandma flow" (drivers/diagnostics handled by the OEM, not by clicking)
    # and they replace run_powershell for everything in the catalog.
    "safe_op", "safe_op_list",
    "oem_detect", "oem_scan_drivers", "oem_apply_drivers",
    # Deeper Windows diagnostics: these are what makes Zora replace a phone
    # call to support, so they belong in the core set for every model size.
    "bsod_recent", "event_log_triage", "warranty_url",
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
    # ─── Desktop Assistant: Email ────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": (
                "Send an email on behalf of the user. Uses Outlook if installed, "
                "otherwise uses SMTP. The user will be shown the email content "
                "and must confirm before it's actually sent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address (comma-separated for multiple)",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body text",
                    },
                    "cc": {
                        "type": "string",
                        "description": "Optional CC recipients (comma-separated)",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    # ─── Desktop Assistant: File Management ──────────────────
    {
        "type": "function",
        "function": {
            "name": "manage_files",
            "description": (
                "Organize, move, copy, rename, or list files and folders. "
                "Use this when the user asks to clean up their desktop, "
                "organize downloads, find files, or move things around."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "move", "copy", "rename", "create_folder",
                                 "delete", "find", "get_size", "organize_by_type"],
                        "description": "What to do with files",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or folder path (use ~ for user home, e.g. ~/Desktop)",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination path (for move/copy)",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "File pattern for find/list (e.g. '*.pdf', '*.jpg')",
                    },
                    "new_name": {
                        "type": "string",
                        "description": "New name (for rename)",
                    },
                },
                "required": ["action", "path"],
            },
        },
    },
    # ─── Desktop Assistant: Open URL / Browser ───────────────
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": (
                "Open a URL or website in the user's default browser. "
                "Use for navigating to support pages, downloads, tutorials, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to open (e.g. 'https://support.microsoft.com')",
                    },
                },
                "required": ["url"],
            },
        },
    },
    # ─── Desktop Assistant: Clipboard ────────────────────────
    {
        "type": "function",
        "function": {
            "name": "clipboard",
            "description": (
                "Read from or write to the system clipboard. "
                "Use to copy text for the user, read what they copied, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "write"],
                        "description": "'read' to get clipboard content, 'write' to set it",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to write to clipboard (only for 'write')",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ─── Desktop Assistant: Reminders & Notes ────────────────
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": (
                "Save or recall notes, reminders, and follow-ups. "
                "Zora remembers things for the user across sessions — "
                "like 'remind me to update drivers tomorrow' or 'save this error code'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["save", "list", "search", "delete"],
                        "description": "What to do with memory",
                    },
                    "content": {
                        "type": "string",
                        "description": "What to remember (for 'save') or search term (for 'search')",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["reminder", "note", "follow_up", "error_code", "preference"],
                        "description": "Category of the memory (default: note)",
                    },
                    "due": {
                        "type": "string",
                        "description": "When to remind (for reminders): 'tomorrow', '2024-12-25', 'next week'",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ─── Desktop Assistant: Notification / Toast ─────────────
    {
        "type": "function",
        "function": {
            "name": "notify",
            "description": (
                "Show a Windows notification/toast message to the user. "
                "Use for completed tasks, reminders, or important alerts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Notification title",
                    },
                    "message": {
                        "type": "string",
                        "description": "Notification body text",
                    },
                },
                "required": ["title", "message"],
            },
        },
    },
    # ─── Safe Operations Catalog ──────────────────────────────
    # Preferred over run_powershell for any command in the catalog.
    # The AI picks an op_id; server-side code builds the argv. The LLM
    # never authors raw shell, eliminating injection risk.
    {
        "type": "function",
        "function": {
            "name": "safe_op_list",
            "description": (
                "List the named operations available in the safe-ops catalog. "
                "Call this first if you don't know which op_id you need. "
                "Optionally filter by risk: 'read', 'write', or 'dangerous'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "risk": {
                        "type": "string",
                        "enum": ["read", "write", "dangerous"],
                        "description": "Filter by risk level (optional).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "safe_op",
            "description": (
                "Run a named operation from the safe-ops catalog. "
                "Prefer this over run_powershell whenever a matching op exists "
                "(network checks, service control, disk health, Defender, SFC, DISM, "
                "etc.). The op_id selects what to do; params supply any inputs "
                "(e.g., service name, hostname). Use dry_run=true to preview the "
                "exact command without executing — useful for confirmation prompts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "op_id": {
                        "type": "string",
                        "description": (
                            "Catalog ID. Examples: 'net.flush_dns', 'net.show_dns', "
                            "'net.test_connection', 'service.status', 'service.restart', "
                            "'sys.disk_health', 'sys.battery_report', 'sys.event_errors', "
                            "'defender.status', 'defender.scan_quick', 'repair.sfc', "
                            "'repair.dism_restore'. Call safe_op_list for the full set."
                        ),
                    },
                    "params": {
                        "type": "object",
                        "description": "Parameters for the operation (per-op schema).",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, return the resolved argv without executing.",
                    },
                },
                "required": ["op_id"],
            },
        },
    },
    # ─── OEM (Dell / HP / Lenovo) Silent Driver Updates ───────
    # Delegates to the vendor's own unattended tool. The user says
    # "update my drivers" → we run dcu-cli / HPIA / Thin Installer
    # in silent mode instead of opening Settings and clicking around.
    {
        "type": "function",
        "function": {
            "name": "oem_detect",
            "description": (
                "Detect the computer's manufacturer (Dell, HP, Lenovo, etc.), "
                "model, serial number, and which OEM support tools are installed. "
                "Call this before oem_scan_drivers / oem_apply_drivers so you can "
                "tell the user what's going to run."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "oem_scan_drivers",
            "description": (
                "Scan the vendor catalog for pending driver / BIOS / firmware "
                "updates using the OEM's silent CLI (Dell Command Update, HP "
                "Image Assistant, or Lenovo Thin Installer). Read-only: makes no "
                "changes, just reports what's available. Use this when the user "
                "asks 'are my drivers up to date?' or 'check my computer for updates'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, return the exact command instead of running.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "oem_apply_drivers",
            "description": (
                "Install all pending driver / BIOS / firmware updates via the "
                "vendor's silent CLI. ALWAYS ask the user for explicit consent "
                "first — these updates can require a reboot. Defaults to "
                "dry_run=true; pass dry_run=false only after the user has agreed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "allow_reboot": {
                        "type": "boolean",
                        "description": "Permit automatic reboot after install (default false).",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": (
                            "Default true — preview the command. Set to false only "
                            "after the user has explicitly consented to install."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    # ─── BSOD / bugcheck triage ──────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "bsod_recent",
            "description": (
                "List recent blue-screen events from the System log with their "
                "bugcheck codes and plain-English explanations. Read-only — call "
                "this when the user mentions 'blue screen', 'BSOD', 'crash', "
                "'won't stay on', or after they reboot from a crash."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "How many recent events to return (default 10, max 50).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bsod_explain",
            "description": (
                "Explain a Windows bugcheck code. Returns the name (e.g., "
                "'IRQL_NOT_LESS_OR_EQUAL') and common causes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": ["integer", "string"],
                        "description": "Bugcheck code as int (10) or hex string ('0x0A').",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "minidump_list",
            "description": (
                "List .dmp files in C:\\Windows\\Minidump for offline analysis. "
                "We don't parse the dump bytes here; this just lets the AI tell "
                "the user 'you have 3 minidumps from yesterday at <path>'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ─── Event Log triage ────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "event_log_recent",
            "description": (
                "Recent error/critical events from a Windows log "
                "(System / Application / Setup). Returns individual events "
                "with timestamps and provider names. Read-only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "log": {
                        "type": "string",
                        "enum": ["System", "Application", "Setup"],
                        "description": "Which log to read (default System).",
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Lookback window in hours (default 24, max 168).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max events to return (default 50, max 500).",
                    },
                    "include_warnings": {
                        "type": "boolean",
                        "description": "Also include Level=3 warnings (default false).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "event_log_triage",
            "description": (
                "Grouped + annotated summary of recent log events. PREFER THIS "
                "over event_log_recent for conversational output — it groups "
                "by (source, event_id), counts occurrences, and adds plain-"
                "English explanations for known IDs (Kernel-Power 41, disk 7, "
                "WHEA 18, etc.). Use when the user asks 'check my event logs', "
                "'what's been failing', 'why does my PC act up'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "log": {
                        "type": "string",
                        "enum": ["System", "Application", "Setup"],
                        "description": "Which log (default System).",
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Lookback window (default 24, max 168).",
                    },
                    "include_warnings": {
                        "type": "boolean",
                        "description": "Include warnings too (default false).",
                    },
                },
                "required": [],
            },
        },
    },
    # ─── OEM warranty lookup ─────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "warranty_url",
            "description": (
                "Build the vendor-specific warranty page URL with the user's "
                "service tag / serial pre-filled. Use when the user asks "
                "'when does my warranty expire', 'am I still covered', "
                "'check my warranty'. Pair with open_url to actually open it."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def get_tools_for_model(model_name: str = "", expert_mode: bool = False) -> list:
    """Return the appropriate tool set for the active provider/mode combo.

    Selection rules:
      * Expert mode: always exposes the full catalog. The user has opted in
        to seeing every diagnostic and is presumed to know what each one does.
      * Novice mode (default): small models (3b/7b/1b) get just the core
        catalog so we don't blow their context budget; large models get the
        full set.

    Expert mode wins because power-user value depends on having access to the
    deep tools (raw event log, DISM, advanced PowerShell ops) — even when the
    backing model is small, we'd rather show the option than hide it.
    """
    if expert_mode:
        return TOOL_DEFINITIONS
    model_lower = model_name.lower()
    is_small = any(tag in model_lower for tag in ["3b", "1b", "7b", ":small", ":mini"])
    if is_small:
        return [t for t in TOOL_DEFINITIONS if t["function"]["name"] in CORE_TOOL_NAMES]
    return TOOL_DEFINITIONS

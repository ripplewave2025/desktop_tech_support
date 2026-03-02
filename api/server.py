"""
Zora Desktop API — FastAPI server powering the AI companion.

Provides REST endpoints for:
- System stats (CPU, RAM, disk)
- Diagnostic scanning and auto-fix
- AI chat with streaming (SSE) and non-streaming modes
- AI provider settings management
"""

import sys
import os
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add root to pythonpath
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil
from core.process_manager import ProcessManager

# Diagnostic modules from CLI
from cli.main import DIAGNOSTIC_MODULES, load_diagnostic

logger = logging.getLogger("zora.api")

app = FastAPI(
    title="Zora Desktop API",
    description="AI Tech Support Companion — REST API",
    version="2.0",
)

# Allow the frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1",
        "http://localhost",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pm = ProcessManager()

# ─── Global Agent + Monitoring ───────────────────────────

_agent = None
_watcher = None
_sessions: Dict[str, Any] = {}  # session_id -> ZoraAgent (for multi-tab isolation)
_runtime_api_keys: Dict[str, str] = {}


def _provider_env_var(provider: str) -> Optional[str]:
    """Map provider name to environment variable for API key."""
    return {
        "claude": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "grok": "XAI_API_KEY",
        "groq": "GROQ_API_KEY",
    }.get(provider)


def _inject_runtime_api_key(config: Dict) -> Dict:
    """Inject runtime-only API keys into config before provider creation."""
    out = dict(config)
    ai = dict(out.get("ai", {}))
    provider = ai.get("provider", "ollama")

    runtime_key = _runtime_api_keys.get(provider)
    if runtime_key:
        ai["api_key"] = runtime_key

    out["ai"] = ai
    return out


def _load_config() -> Dict:
    """Load config.json from project root."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.json",
    )
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _get_agent():
    """Get or create the global ZoraAgent."""
    global _agent
    if _agent is None:
        try:
            from ai.agent import ZoraAgent
            from ai.provider_factory import get_provider

            config = _inject_runtime_api_key(_load_config())
            provider = get_provider(config)
            _agent = ZoraAgent(provider)
            logger.info(f"Zora agent initialized with {provider.name()}")
        except Exception as e:
            logger.warning(f"AI agent init failed: {e}. Chat will use fallback mode.")
            _agent = None
    return _agent


@app.on_event("startup")
async def startup():
    """Initialize agent and start monitoring on startup."""
    _get_agent()
    _start_watcher()


def _start_watcher():
    """Start the background system watcher."""
    global _watcher
    try:
        from monitoring.watcher import SystemWatcher
        _watcher = SystemWatcher()
        _watcher.start()
        logger.info("System watcher started")
    except Exception as e:
        logger.warning(f"Could not start system watcher: {e}")
        _watcher = None


# ─── Pydantic Models ────────────────────────────────────

class FixRequest(BaseModel):
    issue_name: str


class ChatMessage(BaseModel):
    message: str


class SettingsUpdate(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


# ─── Root ────────────────────────────────────────────────

@app.get("/api/status")
def api_status():
    """API health check endpoint (JSON)."""
    agent = _get_agent()
    return {
        "status": "Zora Engine is active",
        "version": "2.0",
        "ai_provider": agent.provider_name if agent else "not configured",
    }


# ─── System Stats ────────────────────────────────────────

@app.get("/api/system")
def get_system_status() -> Dict[str, Any]:
    """Get live system stats (CPU, RAM, Disk, Uptime)."""
    info = pm.get_system_info()
    return {
        "cpu_percent": info.cpu_percent,
        "memory_percent": info.memory_percent,
        "memory_used_gb": info.memory_used_gb,
        "memory_total_gb": info.memory_total_gb,
        "disk_free_gb": info.disk_free_gb,
        "disk_percent": info.disk_percent,
        "uptime_hours": info.uptime_hours,
    }


@app.get("/api/system/processes")
def get_top_processes():
    """Get top processes by CPU/memory using WMI fallback for reliability."""
    try:
        import wmi
        c = wmi.WMI()
        procs = []
        for p in c.Win32_Process():
            try:
                procs.append({
                    "pid": p.ProcessId,
                    "name": p.Name or "System",
                    "working_set": int(p.WorkingSetSize or 0) // (1024 * 1024),
                    "thread_count": int(p.ThreadCount or 0),
                })
            except Exception:
                continue
        procs.sort(key=lambda x: x["working_set"], reverse=True)
        return {"processes": procs[:20], "source": "wmi"}
    except ImportError:
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = p.info
                procs.append({
                    "pid": info["pid"],
                    "name": info["name"] or "System",
                    "working_set": (info["memory_info"].rss if info["memory_info"] else 0) // (1024 * 1024),
                    "thread_count": 0,
                })
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        procs.sort(key=lambda x: x["working_set"], reverse=True)
        return {"processes": procs[:20], "source": "psutil_fallback"}


# ─── Alerts (Proactive Monitoring) ────────────────────────

@app.get("/api/alerts")
def get_alerts():
    """Get active system health alerts."""
    if _watcher is None:
        return {"alerts": [], "total": 0}
    alerts = _watcher.get_alerts()
    return {"alerts": alerts, "total": len(alerts)}


@app.post("/api/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: str):
    """Dismiss a specific alert."""
    if _watcher and _watcher.dismiss_alert(alert_id):
        return {"status": "dismissed", "id": alert_id}
    raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")


@app.post("/api/alerts/dismiss-all")
def dismiss_all_alerts():
    """Dismiss all active alerts."""
    if _watcher:
        _watcher.dismiss_all()
    return {"status": "all dismissed"}


# ─── Flow Diagnostics ────────────────────────────────────

@app.get("/api/flows")
def list_flows():
    """List available diagnostic flows."""
    try:
        from diagnostics.flow_engine import FlowEngine
        engine = FlowEngine()
        return {"flows": engine.available_flows}
    except Exception as e:
        return {"flows": [], "error": str(e)}


@app.get("/api/flows/run/{flow_id}")
def run_flow(flow_id: str):
    """Run a specific diagnostic flow."""
    try:
        from diagnostics.flow_engine import FlowEngine
        from diagnostics.flow_actions import FLOW_ACTIONS
        from diagnostics.base import TechSupportNarrator

        engine = FlowEngine()
        narrator = TechSupportNarrator(verbose=False)
        results = engine.run_flow(flow_id, FLOW_ACTIONS, narrator)

        return {
            "flow_id": flow_id,
            "steps_executed": len(results),
            "results": [
                {
                    "name": r.name,
                    "status": r.status,
                    "details": r.details,
                    "fix_available": r.fix_available,
                }
                for r in results
            ],
            "narrator_log": narrator.log,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Remediation Library ─────────────────────────────────

@app.get("/api/remediation")
def list_remediations():
    """List all available fixes in the remediation library."""
    try:
        from remediation.library import get_library_stats, REMEDIATION_LIBRARY
        stats = get_library_stats()
        fixes = [
            {"id": k, "name": v["name"], "category": v["category"], "risk": v["risk"]}
            for k, v in REMEDIATION_LIBRARY.items()
        ]
        return {"fixes": fixes, "stats": stats}
    except Exception as e:
        return {"fixes": [], "error": str(e)}


# ─── Diagnostics ─────────────────────────────────────────

SAFE_ACTIONS = {
    "Audio Service", "Audio Endpoint Builder", "App Audio Sessions",
    "DNS Cache", "Temp Files", "Volume",
}

RISKY_ACTIONS = {
    "Registry", "Microphone Privacy", "BIOS", "Driver", "Firewall",
    "Windows Update", "Service", "Startup",
}


def classify_risk(issue_name: str) -> str:
    """Classify an action as 'safe' or 'risky' for tiered consent."""
    for safe_keyword in SAFE_ACTIONS:
        if safe_keyword.lower() in issue_name.lower():
            return "safe"
    for risky_keyword in RISKY_ACTIONS:
        if risky_keyword.lower() in issue_name.lower():
            return "risky"
    return "risky"


@app.get("/api/diagnostics")
def list_diagnostics() -> Dict[str, List[str]]:
    """Get available diagnostic categories."""
    return {"categories": list(DIAGNOSTIC_MODULES.keys())}


@app.get("/api/diagnostics/run/{name}")
def run_diagnostic(name: str):
    """Run a specific diagnostic module."""
    if name not in DIAGNOSTIC_MODULES and name != "all":
        raise HTTPException(status_code=404, detail=f"Diagnostic '{name}' not found")

    try:
        from diagnostics.base import TechSupportNarrator

        narrator = TechSupportNarrator(verbose=False)
        DiagClass = load_diagnostic(name)
        diag = DiagClass(narrator=narrator)
        results = diag.diagnose()

        formatted = []
        for r in results:
            formatted.append({
                "name": r.name,
                "status": r.status,
                "details": r.details,
                "fix_available": r.fix_available,
                "fix_applied": r.fix_applied,
            })

        return {
            "category": name,
            "results": formatted,
            "narrator_log": narrator.log,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/diagnostics/fix/{name}")
def apply_diagnostic_fix(name: str, payload: FixRequest):
    """Trigger an auto-fix for a specific issue."""
    if name not in DIAGNOSTIC_MODULES:
        raise HTTPException(status_code=404, detail=f"Diagnostic '{name}' not found")

    try:
        from diagnostics.base import TechSupportNarrator, DiagnosticResult
        import diagnostics.base

        risk_level = classify_risk(payload.issue_name)
        diagnostics.base.ask_permission = lambda msg: True

        narrator = TechSupportNarrator(verbose=False)
        DiagClass = load_diagnostic(name)
        diag = DiagClass(narrator=narrator)

        dummy_result = DiagnosticResult(name=payload.issue_name, status="warning")
        success = diag.apply_fix(dummy_result)

        return {
            "success": success,
            "risk_level": risk_level,
            "narrator_log": narrator.log,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── AI Chat ────────────────────────────────────────────

@app.post("/api/chat")
async def handle_chat(payload: ChatMessage):
    """Non-streaming AI chat endpoint."""
    agent = _get_agent()

    if agent is None:
        return _fallback_chat(payload.message)

    try:
        response = await agent.chat(payload.message)
        return {"reply": response, "action": None, "provider": agent.provider_name}
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        return _fallback_chat(payload.message)


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatMessage):
    """Streaming AI chat via Server-Sent Events (SSE).

    Event types:
        data: {"type": "tool_call", "name": "run_diagnostic", "arguments": {...}}
        data: {"type": "tool_result", "name": "run_diagnostic", "result": {...}}
        data: {"type": "text", "content": "partial response..."}
        data: {"type": "done"}
    """
    agent = _get_agent()

    if agent is None:
        reply = _fallback_chat(payload.message)

        async def fallback_gen():
            yield f"data: {json.dumps({'type': 'text', 'content': reply['reply']})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(fallback_gen(), media_type="text/event-stream")

    async def event_generator():
        try:
            async for event in agent.chat_stream(payload.message):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Stream error: {type(e).__name__}: {e}\n{tb}")
            err_msg = f"Sorry, I ran into an issue: {type(e).__name__}: {e}" if str(e) else f"Sorry, hit a snag ({type(e).__name__}). Trying simpler mode..."
            yield f"data: {json.dumps({'type': 'text', 'content': err_msg})}\n\n"
            # Fallback: try without tools (simpler mode)
            try:
                fallback_resp = await agent._provider.chat(
                    messages=[
                        agent._conversation[0],  # system prompt
                        type(agent._conversation[0])(role="user", content=payload.message),
                    ],
                    temperature=0.4,
                )
                yield f"data: {json.dumps({'type': 'text', 'content': fallback_resp.message.content})}\n\n"
            except Exception:
                pass
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/chat/reset")
async def reset_chat():
    """Reset conversation history."""
    agent = _get_agent()
    if agent:
        agent.reset_conversation()
    return {"status": "conversation reset"}


def _fallback_chat(message: str) -> Dict:
    """Keyword-based fallback when AI provider is not configured."""
    msg = message.lower()

    intents = {
        "audio": (["sound", "audio", "hear", "speaker", "headphone", "volume"], "audio"),
        "internet": (["internet", "wifi", "network", "connected", "dns"], "internet"),
        "printer": (["printer", "spooler", "print", "printing"], "printer"),
        "display": (["screen", "display", "monitor", "resolution", "gpu", "graphics"], "display"),
        "software": (["update", "frozen", "crash", "startup", "hang"], "software"),
        "files": (["space", "temp", "files", "full", "storage", "download", "cleanup"], "files"),
        "security": (["virus", "defender", "firewall", "malware", "security"], "security"),
        "hardware": (["cpu", "memory", "ram", "disk", "battery", "hot", "overheating"], "hardware"),
    }

    for category, (keywords, action) in intents.items():
        if any(kw in msg for kw in keywords):
            return {
                "reply": f"I can help with that! Let me run a {category} diagnostic to check things out. Click the '{category.capitalize()}' button in the diagnostics panel, or I can run it for you.",
                "action": action,
            }

    return {
        "reply": (
            "Hello! I'm Zora, your personal tech support companion. "
            "I can help with internet issues, printer problems, audio troubles, "
            "slow performance, storage cleanup, display issues, and security checks. "
            "Just tell me what's bothering you! "
            "\n\nNote: To enable AI-powered conversations, add your API key in Settings."
        ),
        "action": None,
    }


# ─── Settings ───────────────────────────────────────────

@app.get("/api/settings")
def get_settings():
    """Get current AI provider settings."""
    config = _load_config()
    ai_config = config.get("ai", {})
    agent = _get_agent()
    provider_name = ai_config.get("provider", "ollama")
    provider_env = _provider_env_var(provider_name)
    has_runtime_key = bool(_runtime_api_keys.get(provider_name))

    return {
        "provider": provider_name,
        "model": ai_config.get("model", ""),
        "has_api_key": bool(
            has_runtime_key
            or (provider_env and os.environ.get(provider_env))
        ),
        "base_url": ai_config.get("base_url", ""),
        "available_providers": ["ollama", "claude", "openai", "grok", "groq", "custom"],
        "active_provider": agent.provider_name if agent else "none",
    }


@app.post("/api/settings")
def update_settings(settings: SettingsUpdate):
    """Update AI provider settings and reinitialize the agent."""
    global _agent

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.json",
    )
    config = _load_config()

    if "ai" not in config:
        config["ai"] = {}

    if settings.provider is not None:
        config["ai"]["provider"] = settings.provider
    if settings.model is not None:
        config["ai"]["model"] = settings.model
    effective_provider = settings.provider or config["ai"].get("provider", "ollama")
    if settings.api_key is not None:
        key = settings.api_key.strip()
        # Do not persist secrets to config.json (runtime only)
        if key:
            _runtime_api_keys[effective_provider] = key
        else:
            _runtime_api_keys.pop(effective_provider, None)

        env_var = _provider_env_var(effective_provider)
        if env_var:
            if key:
                os.environ[env_var] = key
            else:
                os.environ.pop(env_var, None)

    # Ensure no plaintext api_key survives in config
    config["ai"].pop("api_key", None)
    if settings.base_url is not None:
        config["ai"]["base_url"] = settings.base_url

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    # Reinitialize agent with new settings
    _agent = None
    try:
        agent = _get_agent()
        return {
            "status": "updated",
            "active_provider": agent.provider_name if agent else "none",
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ─── Static Frontend Serving ───────────────────────────
# Serve built React app when running as bundled .exe or standalone

def _find_frontend_dist() -> Optional[str]:
    """Locate the ui/dist folder (works both in dev and PyInstaller bundle)."""
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle: ui/dist is packed inside _MEIPASS
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    dist_path = os.path.join(base, "ui", "dist")
    if os.path.isdir(dist_path):
        return dist_path
    return None


_frontend_dist = _find_frontend_dist()

if _frontend_dist:
    # Serve static assets (JS, CSS, images)
    _assets_dir = os.path.join(_frontend_dist, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="static-assets")

    # Catch-all: serve index.html for any non-API route (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for all non-API routes."""
        # Don't override API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        # Try to serve the exact file first
        file_path = os.path.join(_frontend_dist, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        # Otherwise serve index.html (SPA client-side routing)
        return FileResponse(os.path.join(_frontend_dist, "index.html"))

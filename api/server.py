"""
Zora Desktop API.

Provides REST endpoints for system stats, diagnostics, orchestration tasks,
chat wrappers, settings, and static frontend serving.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add root to pythonpath
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil
from ai.agent import ZoraAgent
from ai.orchestrator import TaskOrchestrator
from ai.provider_factory import get_provider
from cli.main import DIAGNOSTIC_MODULES, load_diagnostic
from core.process_manager import ProcessManager

logger = logging.getLogger("zora.api")

app = FastAPI(
    title="Zora Desktop API",
    description="AI Tech Support Companion REST API",
    version="2.3",
)

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

_agent = None
_orchestrator = None
_watcher = None
_runtime_api_keys: Dict[str, str] = {}


def _provider_env_var(provider: str) -> Optional[str]:
    return {
        "claude": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "grok": "XAI_API_KEY",
        "groq": "GROQ_API_KEY",
    }.get(provider)


def _inject_runtime_api_key(config: Dict) -> Dict:
    out = dict(config)
    ai = dict(out.get("ai", {}))
    provider = ai.get("provider", "ollama")
    runtime_key = _runtime_api_keys.get(provider)
    if runtime_key:
        ai["api_key"] = runtime_key
    out["ai"] = ai
    return out


def _load_config() -> Dict:
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.json",
    )
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _get_provider_instance():
    try:
        config = _inject_runtime_api_key(_load_config())
        return get_provider(config)
    except Exception as e:
        logger.warning(f"Provider init failed: {e}")
        return None


def _get_agent():
    global _agent
    if _agent is None:
        provider = _get_provider_instance()
        if provider is None:
            return None
        try:
            _agent = ZoraAgent(provider)
            logger.info(f"Zora agent initialized with {provider.name()}")
        except Exception as e:
            logger.warning(f"AI agent init failed: {e}")
            _agent = None
    return _agent


def _get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        provider = _get_provider_instance()
        try:
            _orchestrator = TaskOrchestrator(provider=provider)
            logger.info("Task orchestrator initialized")
        except Exception as e:
            logger.warning(f"Task orchestrator init failed: {e}")
            _orchestrator = None
    return _orchestrator


@app.on_event("startup")
async def startup():
    _get_agent()
    _get_orchestrator()
    _start_watcher()
    _start_followup_scheduler()


_followup_task: Optional["asyncio.Task"] = None


def _start_followup_scheduler():
    """Kick off a background task that fires due follow-up notifications.

    Runs every 30 minutes. Safe no-op if the orchestrator is unavailable
    (e.g. tests or degraded startup).
    """
    global _followup_task
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        logger.info("Follow-up scheduler skipped: orchestrator unavailable")
        return

    async def _loop():
        while True:
            try:
                await orchestrator.fire_due_follow_up_notifications()
            except Exception as e:
                logger.warning(f"Follow-up scheduler tick failed: {e}")
            await asyncio.sleep(30 * 60)

    try:
        _followup_task = asyncio.create_task(_loop())
        logger.info("Follow-up scheduler started (30-min interval)")
    except Exception as e:
        logger.warning(f"Could not start follow-up scheduler: {e}")
        _followup_task = None


@app.on_event("shutdown")
async def _shutdown():
    global _followup_task
    if _followup_task is not None:
        _followup_task.cancel()
        _followup_task = None


def _start_watcher():
    global _watcher
    try:
        from monitoring.watcher import SystemWatcher

        _watcher = SystemWatcher()
        _watcher.start()
        logger.info("System watcher started")
    except Exception as e:
        logger.warning(f"Could not start system watcher: {e}")
        _watcher = None


class FixRequest(BaseModel):
    issue_name: str


class ChatMessage(BaseModel):
    message: str


class TaskRequest(BaseModel):
    message: Optional[str] = None
    task_id: Optional[str] = None


class TaskConfirmRequest(BaseModel):
    step_id: str


class TaskUserInputRequest(BaseModel):
    step_id: str
    value: Any


class SettingsUpdate(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@app.get("/api/status")
def api_status():
    agent = _get_agent()
    orchestrator = _get_orchestrator()
    return {
        "status": "Zora Engine is active",
        "version": "2.3",
        "ai_provider": agent.provider_name if agent else "not configured",
        "orchestrator": bool(orchestrator),
    }


@app.get("/api/system")
def get_system_status() -> Dict[str, Any]:
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
    try:
        import wmi

        c = wmi.WMI()
        procs = []
        for p in c.Win32_Process():
            try:
                procs.append(
                    {
                        "pid": p.ProcessId,
                        "name": p.Name or "System",
                        "working_set": int(p.WorkingSetSize or 0) // (1024 * 1024),
                        "thread_count": int(p.ThreadCount or 0),
                    }
                )
            except Exception:
                continue
        procs.sort(key=lambda x: x["working_set"], reverse=True)
        return {"processes": procs[:20], "source": "wmi"}
    except ImportError:
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = p.info
                procs.append(
                    {
                        "pid": info["pid"],
                        "name": info["name"] or "System",
                        "working_set": (info["memory_info"].rss if info["memory_info"] else 0) // (1024 * 1024),
                        "thread_count": 0,
                    }
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        procs.sort(key=lambda x: x["working_set"], reverse=True)
        return {"processes": procs[:20], "source": "psutil_fallback"}


@app.get("/api/alerts")
def get_alerts():
    if _watcher is None:
        return {"alerts": [], "total": 0}
    alerts = _watcher.get_alerts()
    return {"alerts": alerts, "total": len(alerts)}


@app.post("/api/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: str):
    if _watcher and _watcher.dismiss_alert(alert_id):
        return {"status": "dismissed", "id": alert_id}
    raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")


@app.post("/api/alerts/dismiss-all")
def dismiss_all_alerts():
    if _watcher:
        _watcher.dismiss_all()
    return {"status": "all dismissed"}


@app.get("/api/flows")
def list_flows():
    try:
        from diagnostics.flow_engine import FlowEngine

        engine = FlowEngine()
        return {"flows": engine.available_flows}
    except Exception as e:
        return {"flows": [], "error": str(e)}


@app.get("/api/flows/run/{flow_id}")
def run_flow(flow_id: str):
    try:
        from diagnostics.base import TechSupportNarrator
        from diagnostics.flow_actions import FLOW_ACTIONS
        from diagnostics.flow_engine import FlowEngine

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


@app.get("/api/remediation")
def list_remediations():
    try:
        from remediation.library import REMEDIATION_LIBRARY, get_library_stats

        stats = get_library_stats()
        fixes = [
            {"id": k, "name": v["name"], "category": v["category"], "risk": v["risk"]}
            for k, v in REMEDIATION_LIBRARY.items()
        ]
        return {"fixes": fixes, "stats": stats}
    except Exception as e:
        return {"fixes": [], "error": str(e)}


SAFE_ACTIONS = {
    "Audio Service",
    "Audio Endpoint Builder",
    "App Audio Sessions",
    "DNS Cache",
    "Temp Files",
    "Volume",
}

RISKY_ACTIONS = {
    "Registry",
    "Microphone Privacy",
    "BIOS",
    "Driver",
    "Firewall",
    "Windows Update",
    "Service",
    "Startup",
}


def classify_risk(issue_name: str) -> str:
    for safe_keyword in SAFE_ACTIONS:
        if safe_keyword.lower() in issue_name.lower():
            return "safe"
    for risky_keyword in RISKY_ACTIONS:
        if risky_keyword.lower() in issue_name.lower():
            return "risky"
    return "risky"


@app.get("/api/diagnostics")
def list_diagnostics() -> Dict[str, List[str]]:
    return {"categories": list(DIAGNOSTIC_MODULES.keys())}


@app.get("/api/diagnostics/run/{name}")
def run_diagnostic(name: str):
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
            formatted.append(
                {
                    "name": r.name,
                    "status": r.status,
                    "details": r.details,
                    "fix_available": r.fix_available,
                    "fix_applied": r.fix_applied,
                }
            )
        return {"category": name, "results": formatted, "narrator_log": narrator.log}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/diagnostics/fix/{name}")
def apply_diagnostic_fix(name: str, payload: FixRequest):
    if name not in DIAGNOSTIC_MODULES:
        raise HTTPException(status_code=404, detail=f"Diagnostic '{name}' not found")

    try:
        import diagnostics.base
        from diagnostics.base import DiagnosticResult, TechSupportNarrator

        risk_level = classify_risk(payload.issue_name)
        diagnostics.base.ask_permission = lambda msg: True
        narrator = TechSupportNarrator(verbose=False)
        DiagClass = load_diagnostic(name)
        diag = DiagClass(narrator=narrator)
        dummy_result = DiagnosticResult(name=payload.issue_name, status="warning")
        success = diag.apply_fix(dummy_result)
        return {"success": success, "risk_level": risk_level, "narrator_log": narrator.log}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/plan")
async def plan_task(payload: ChatMessage):
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")
    plan = await orchestrator.plan_task(payload.message)
    return plan.to_dict()


@app.post("/api/tasks/execute")
async def queue_task_execution(payload: TaskRequest):
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")
    if payload.task_id:
        plan = orchestrator.get_plan(payload.task_id)
        if plan is None:
            raise HTTPException(status_code=404, detail=f"Task '{payload.task_id}' not found")
    elif payload.message:
        plan = await orchestrator.plan_task(payload.message)
    else:
        raise HTTPException(status_code=400, detail="Provide either message or task_id")
    return {
        "task_id": plan.task_id,
        "status": plan.status,
        "auto_execute": plan.auto_execute,
        "summary": plan.summary,
    }


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")
    plan = orchestrator.get_plan(task_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return plan.to_dict()


@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")

    async def event_generator():
        async for event in orchestrator.execute_plan(task_id):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/tasks/{task_id}/confirm")
def confirm_task_step(task_id: str, payload: TaskConfirmRequest):
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")
    plan = orchestrator.confirm_step(task_id, payload.step_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return plan.to_dict()


@app.post("/api/tasks/{task_id}/user_input")
def submit_task_user_input(task_id: str, payload: TaskUserInputRequest):
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")
    plan = orchestrator.resume_with_input(task_id, payload.step_id, payload.value)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return plan.to_dict()


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")
    plan = orchestrator.cancel_task(task_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return plan.to_dict()


@app.get("/api/oem/profile")
def get_oem_profile():
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")
    return orchestrator.oem_snapshot()


@app.get("/api/oem/tools")
def get_oem_tools():
    profile = get_oem_profile()
    return {"manufacturer": profile.get("manufacturer"), "model": profile.get("model"), "tools": profile.get("tools", [])}


@app.get("/api/knowledge/version")
def get_knowledge_version():
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")
    return orchestrator.knowledge_version()


# --- Phase 4b: follow-up scheduler endpoints -----------------------------

class FollowUpResolveRequest(BaseModel):
    case_id: str
    follow_up_title: str


@app.get("/api/followups/due")
def get_due_followups():
    """Return every open case with at least one follow-up past its due date.

    The UI polls this endpoint on mount to show the 'follow-ups due' pill.
    """
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")
    return {"due": orchestrator.check_follow_ups()}


@app.post("/api/followups/resolve")
def resolve_followup(payload: FollowUpResolveRequest):
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Task orchestrator is unavailable")
    case = orchestrator.resolve_follow_up(payload.case_id, payload.follow_up_title)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{payload.case_id}' not found")
    return {"case": case}


# --- Phase 7: smart-home config endpoint ---------------------------------

@app.get("/api/smart_home/status")
def get_smart_home_status():
    """Return a redacted view of the smart-home credential store.

    Used by the Settings UI to show which backends (Home Assistant, Hue,
    MQTT) are configured, without ever echoing tokens or passwords.
    """
    try:
        from ai.smart_home import SmartHomeConfigStore
        return SmartHomeConfigStore().redacted_snapshot()
    except Exception as e:
        logger.warning(f"Smart-home status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Phase 8: voice I/O endpoints (server-side fallbacks) ----------------
#
# The primary voice path is the browser Web Speech API — it's zero-install,
# zero-latency, and handles microphone permissions cleanly on Windows Edge
# and Chrome. These endpoints exist as server-side fallbacks for:
#   1. Environments where the browser Web Speech API is unavailable
#      (e.g. a stripped WebView, a non-Chromium browser, Tauri on some
#      platforms, or corporate browser lockdowns).
#   2. Users who want higher-quality transcription than the browser
#      default (Whisper vs. system STT).
#
# Both dependencies are lazy-imported so Zora still boots with exit 0
# even if `faster-whisper` / `openai-whisper` / `pyttsx3` are missing.

_whisper_model = None
_tts_engine = None


def _get_whisper_model():
    """Lazy-load a Whisper model. Returns None if no backend is installed.

    We try faster-whisper first (CPU-friendly, ~5x quicker than stock
    openai-whisper), then fall back to the reference implementation.
    """
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        from faster_whisper import WhisperModel  # type: ignore
        _whisper_model = ("faster", WhisperModel("base", device="cpu", compute_type="int8"))
        logger.info("Whisper loaded via faster-whisper (base/int8)")
        return _whisper_model
    except Exception:
        pass
    try:
        import whisper  # type: ignore
        _whisper_model = ("openai", whisper.load_model("base"))
        logger.info("Whisper loaded via openai-whisper (base)")
        return _whisper_model
    except Exception as e:
        logger.info(f"Whisper unavailable ({e}); browser STT only")
        return None


def _get_tts_engine():
    """Lazy-load pyttsx3 for offline Windows SAPI TTS. None if missing."""
    global _tts_engine
    if _tts_engine is not None:
        return _tts_engine
    try:
        import pyttsx3  # type: ignore
        _tts_engine = pyttsx3.init()
        # Slightly slower than default — accessibility default.
        _tts_engine.setProperty("rate", 170)
        logger.info("pyttsx3 TTS engine initialized")
        return _tts_engine
    except Exception as e:
        logger.info(f"pyttsx3 unavailable ({e}); browser TTS only")
        return None


@app.get("/api/voice/capabilities")
def voice_capabilities():
    """Report which voice backends are installed server-side.

    The browser should use its Web Speech API regardless — these flags
    only tell the UI whether fallback endpoints are usable.
    """
    whisper = _get_whisper_model() is not None
    tts = _get_tts_engine() is not None
    return {
        "stt_server_available": whisper,
        "tts_server_available": tts,
        "browser_stt_recommended": True,
        "browser_tts_recommended": True,
    }


@app.post("/api/voice/transcribe")
async def voice_transcribe(request: Request):
    """Transcribe an uploaded audio blob server-side via Whisper.

    Accepts a raw audio body (webm / ogg / wav / mp3). Requires a Whisper
    backend; returns 503 if none is installed.
    """
    model_entry = _get_whisper_model()
    if model_entry is None:
        raise HTTPException(
            status_code=503,
            detail="Server-side transcription unavailable. Install `faster-whisper` "
                   "or use the browser Web Speech API instead.",
        )

    import tempfile
    audio_bytes = await request.body()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio body")

    suffix = ".webm"
    content_type = request.headers.get("content-type", "").lower()
    if "wav" in content_type:
        suffix = ".wav"
    elif "mp3" in content_type or "mpeg" in content_type:
        suffix = ".mp3"
    elif "ogg" in content_type:
        suffix = ".ogg"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(audio_bytes)
        tmp.flush()
        tmp.close()

        backend, model = model_entry
        if backend == "faster":
            segments, info = model.transcribe(tmp.name, beam_size=1)
            text = " ".join(seg.text for seg in segments).strip()
            return {"text": text, "language": info.language, "backend": "faster-whisper"}
        else:
            result = model.transcribe(tmp.name)
            return {"text": (result.get("text") or "").strip(), "backend": "openai-whisper"}
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


class VoiceSpeakRequest(BaseModel):
    text: str
    rate: Optional[int] = None   # words per minute (default 170)


@app.post("/api/voice/speak")
def voice_speak(payload: VoiceSpeakRequest):
    """Render `text` to a WAV file server-side via pyttsx3 and stream it.

    Fallback for environments where browser TTS (speechSynthesis) is
    unavailable. Returns 503 if pyttsx3 is not installed.
    """
    engine = _get_tts_engine()
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Server-side TTS unavailable. Install `pyttsx3` or use the "
                   "browser SpeechSynthesis API instead.",
        )
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.close()
    try:
        if payload.rate:
            engine.setProperty("rate", int(payload.rate))
        engine.save_to_file(text, tmp.name)
        engine.runAndWait()

        def _iter():
            with open(tmp.name, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    yield chunk
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        return StreamingResponse(_iter(), media_type="audio/wav")
    except Exception as e:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"TTS failed: {e}")


@app.post("/api/chat")
async def handle_chat(payload: ChatMessage):
    orchestrator = _get_orchestrator()
    if orchestrator is not None:
        plan = await orchestrator.plan_task(payload.message)
        return {
            "reply": plan.summary,
            "action": plan.route.domain,
            "task_id": plan.task_id,
            "route": plan.route.to_dict(),
            "sources": [source.to_dict() for source in plan.sources],
        }

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
    orchestrator = _get_orchestrator()
    if orchestrator is not None:
        async def event_generator():
            async for event in orchestrator.handle_message_stream(payload.message):
                yield f"data: {json.dumps(event, default=str)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

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
            logger.error(f"Stream error: {type(e).__name__}: {e}")
            yield f"data: {json.dumps({'type': 'text', 'content': f'Sorry, I ran into an issue: {type(e).__name__}: {e}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/chat/reset")
async def reset_chat():
    agent = _get_agent()
    if agent:
        agent.reset_conversation()
    return {"status": "conversation reset"}


def _fallback_chat(message: str) -> Dict:
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
                "reply": f"I can help with that. I will plan a {category} workflow and pick the safest next step.",
                "action": action,
            }
    return {
        "reply": (
            "Hello. I'm Zora, your personal tech support companion. "
            "I can route issues to OEM tools, Windows settings, browser support sites, and file workflows."
        ),
        "action": None,
    }


@app.get("/api/settings")
def get_settings():
    config = _load_config()
    ai_config = config.get("ai", {})
    agent = _get_agent()
    provider_name = ai_config.get("provider", "ollama")
    provider_env = _provider_env_var(provider_name)
    has_runtime_key = bool(_runtime_api_keys.get(provider_name))
    return {
        "provider": provider_name,
        "model": ai_config.get("model", ""),
        "has_api_key": bool(has_runtime_key or (provider_env and os.environ.get(provider_env))),
        "base_url": ai_config.get("base_url", ""),
        "available_providers": ["ollama", "claude", "openai", "grok", "groq", "custom"],
        "active_provider": agent.provider_name if agent else "none",
    }


@app.post("/api/settings")
def update_settings(settings: SettingsUpdate):
    global _agent, _orchestrator

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

    config["ai"].pop("api_key", None)
    if settings.base_url is not None:
        config["ai"]["base_url"] = settings.base_url

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    _agent = None
    _orchestrator = None
    try:
        agent = _get_agent()
        _get_orchestrator()
        return {"status": "updated", "active_provider": agent.provider_name if agent else "none"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _find_frontend_dist() -> Optional[str]:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_path = os.path.join(base, "ui", "dist")
    if os.path.isdir(dist_path):
        return dist_path
    return None


_frontend_dist = _find_frontend_dist()

if _frontend_dist:
    _assets_dir = os.path.join(_frontend_dist, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = os.path.join(_frontend_dist, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_frontend_dist, "index.html"))

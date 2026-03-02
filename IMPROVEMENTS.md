# IMPROVEMENTS

## High-level system overview
- Zora is a Windows-first desktop tech support app with a FastAPI backend (`api/server.py`) and a React UI (`ui/`).
- `ai/agent.py` is the reasoning loop: it sends conversation + tools to the selected model provider, executes tool calls, and returns final responses.
- `ai/tool_executor.py` is the action bridge between AI tool calls and real system operations (diagnostics, PowerShell, UI control, remediation, search).
- `core/` contains automation primitives (mouse/keyboard/window/process) and safety controls (`core/safety.py`) like rate limiting, blacklists, and audit logs.
- `diagnostics/` includes category diagnostics plus YAML decision-tree diagnostics via `diagnostics/flow_engine.py` and shared actions in `diagnostics/flow_actions.py`.
- `monitoring/watcher.py` runs continuous health polling and emits proactive alerts through `/api/alerts`.
- `remediation/library.py` stores structured fix definitions and metadata used by remediation APIs/tools.
- Provider selection and model/API-key behavior are split across `api/server.py` settings endpoints and `ai/provider_factory.py` resolution logic.

---

## Prioritized checklist (highest impact first)

### Security
- [ ] **[P0] Stop persisting API keys in plaintext config**
  - **Why it matters:** `update_settings` writes `api_key` into `config.json`, creating an easy secret-leak path.
  - **Files / functions:** `api/server.py` → `update_settings`, `_load_config`.
  - **Action:** Persist only non-secret provider settings; keep secrets in env/OS keychain and return masked values in API responses.

- [ ] **[P0] Tighten CORS for local desktop usage**
  - **Why it matters:** `allow_origins=["*"]` with credentials can expose local APIs to untrusted web pages.
  - **Files / functions:** `api/server.py` (CORS middleware config).
  - **Action:** Restrict origins to explicit localhost/127.0.0.1 origins and disable credentials if not required.

- [ ] **[P0] Replace PowerShell blocklist with explicit allowlisted operations**
  - **Why it matters:** Substring blocklists are bypass-prone for command execution surfaces.
  - **Files / functions:** `ai/tool_executor.py` → `_tool_run_powershell`, `_ps_blocklist`.
  - **Action:** Convert to command templates/operation IDs, reject free-form commands, and enforce consent + audit logs for high-risk actions.

### Correctness
- [ ] **[P0] Restore permission hooks safely in API fix flow**
  - **Why it matters:** `apply_diagnostic_fix` monkeypatches `diagnostics.base.ask_permission` and does not restore it on failure.
  - **Files / functions:** `api/server.py` → `apply_diagnostic_fix`; `diagnostics/base.py` → `ask_permission`.
  - **Action:** Wrap override in `try/finally` (like `ToolExecutor._tool_apply_fix`) or inject a request-local permission callback.

- [ ] **[P1] Validate tool/API inputs before side effects**
  - **Why it matters:** Many handlers assume required keys and types exist, causing runtime errors from malformed model output.
  - **Files / functions:** `ai/tool_executor.py` (`_tool_*` handlers), `api/server.py` endpoint payload handling.
  - **Action:** Add strict argument schemas and consistent structured error responses.

- [ ] **[P1] Handle missing window matches in focus tool**
  - **Why it matters:** `_tool_focus_window` calls `win.focus()` without null checks.
  - **Files / functions:** `ai/tool_executor.py` → `_tool_focus_window`.
  - **Action:** Return a non-throwing error payload when no match is found; include suggestion data.

- [ ] **[P2] Remove or complete unused session isolation state**
  - **Why it matters:** `_sessions` suggests multi-session support but is currently unused, creating misleading architecture signals.
  - **Files / functions:** `api/server.py` → `_sessions` and chat endpoints.
  - **Action:** Either implement per-session agent routing or delete dead state until needed.

### Performance
- [ ] **[P1] Reduce repeated imports/object creation in request paths**
  - **Why it matters:** Function-local imports and repeated engine creation add avoidable per-request overhead.
  - **Files / functions:** `api/server.py` diagnostic/flow/remediation routes; `ai/tool_executor.py` diagnostics/flow paths.
  - **Action:** Move stable imports to module scope and cache thread-safe reusable objects.

- [ ] **[P2] Bound long-running conversation history growth**
  - **Why it matters:** Agent history grows without trimming, increasing token cost and latency over time.
  - **Files / functions:** `ai/agent.py` → `chat`, `chat_stream`, `reset_conversation` behavior.
  - **Action:** Add rolling context windows + periodic summary compression.

- [ ] **[P2] Add watcher cooldown for expensive CPU top-process collection**
  - **Why it matters:** Under sustained load, repeated scans and formatting can increase overhead.
  - **Files / functions:** `monitoring/watcher.py` → `_check_cpu`.
  - **Action:** Add cooldown/backoff around heavy process collection and alert generation.

### Readability / Maintainability
- [ ] **[P1] Split `ToolExecutor` into focused modules**
  - **Why it matters:** One very large multi-domain file is hard to navigate, review, and test.
  - **Files / functions:** `ai/tool_executor.py` (all handlers).
  - **Action:** Refactor into domain modules (diagnostics/system/input/security/web) with a small dispatcher entrypoint.

- [ ] **[P1] Remove runtime `sys.path` mutation**
  - **Why it matters:** Path hacking hides packaging issues and can behave differently across environments.
  - **Files / functions:** `api/server.py` (top-level `sys.path.insert`), `ai/tool_executor.py` (`_tool_run_diagnostic`).
  - **Action:** Use package-consistent imports and proper entrypoints instead of runtime path mutation.

- [ ] **[P2] Standardize API error contracts and request logging context**
  - **Why it matters:** Mixed error styles (`dict`, `HTTPException`, swallowed errors) complicate client behavior and debugging.
  - **Files / functions:** `api/server.py` across endpoints.
  - **Action:** Adopt one response schema and structured logs with request IDs.

### Tests
- [ ] **[P0] Add regression tests for high-risk boundaries**
  - **Why it matters:** Security- and safety-critical paths need explicit guardrail tests.
  - **Files / functions:** new tests for `api/server.py`, `ai/tool_executor.py`, `core/safety.py`.
  - **Action:** Cover PowerShell policy enforcement, secret handling, CORS restrictions, and permission-hook restoration.

- [ ] **[P1] Make test suite dependency-tiered and environment-aware**
  - **Why it matters:** Current import tests fail hard when optional Windows dependencies are unavailable, reducing CI signal quality.
  - **Files / functions:** `tests/test_imports.py`, pytest config.
  - **Action:** Split tests into core unit vs Windows/integration groups with markers/skips.

- [ ] **[P1] Add flow-engine branch/condition contract tests**
  - **Why it matters:** Branch mis-evaluation in diagnostics can silently route users to incorrect remediation steps.
  - **Files / functions:** `diagnostics/flow_engine.py`; new tests under `tests/`.
  - **Action:** Add table-driven tests for condition operators, missing fields, else branches, and cycle prevention behavior.

### DX
- [ ] **[P1] Add one-command local quality gate**
  - **Why it matters:** Contributors need a reliable pre-PR check workflow.
  - **Files / functions:** root task runner (`Makefile`/script), `README.md`, `CONTRIBUTING.md`.
  - **Action:** Add `make check` (or equivalent) that runs formatting, linting, and tier-1 tests.

- [ ] **[P2] Document config precedence in one definitive section**
  - **Why it matters:** Provider behavior spans config + env vars and is easy to misconfigure during onboarding.
  - **Files / functions:** `README.md`, `ai/provider_factory.py`, `api/server.py` settings docs.
  - **Action:** Add a single “configuration precedence” section with secure examples.


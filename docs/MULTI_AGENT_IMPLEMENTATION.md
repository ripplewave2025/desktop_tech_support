# Multi-Agent Implementation Notes

## What Landed
- `ai/orchestrator.py` adds task planning, specialist routing, research ranking, and consent-aware execution.
- `ai/router.py` and `ai/agents/` split work into Windows, OEM, files, browser/support, desktop-navigation, and support-case specialists.
- `ai/agents/oem_agent.py` now subroutes OEM work through Dell, HP, Lenovo, and generic vendor delegates.
- `ai/knowledge.py` and `knowledge/packs/builtin/` add the first local knowledge-pack format.
- `ai/oem.py` adds OEM profile and tool discovery for Dell, HP, and Lenovo.
- `storage/db.py` adds SQLite persistence for task plans, source hits, consent events, OEM profiles, and case drafts.
- `api/server.py` now exposes `/api/tasks/*`, `/api/oem/*`, `/api/knowledge/version`, and uses the orchestrator as the primary chat wrapper.
- `ui/src/hooks/useChat.js` and `ui/src/components/ChatWidget.jsx` now recognize specialist-agent activity, pause messages, and task confirmation flow.

## Current Behavior
- Chat requests are routed through the orchestrator.
- The orchestrator builds a plan, ranks local and web sources, and auto-executes only when the top-ranked path is backed by a local playbook or official source.
- Sensitive or manual-login steps pause and require an explicit confirm step id via the task API.
- OEM paths prefer detected vendor tools before generic support pages.

## Current Limits
- Browser automation is staged behind `open_url` for now; Playwright is added as a dependency target, but browser installation is still a deployment step.
- Knowledge packs are embedded and hashed today. Detached-signature verification is the next hardening step.
- Resume-after-restart persists plan state, but the current execution loop still expects the caller to resume the task stream.

## How to Add Your Dell Playbooks
1. Add a new entry to `knowledge/packs/builtin/playbooks.yaml`.
2. Include `issue_id`, `route`, `summary`, tags, OEM scope, trusted sources, and explicit steps.
3. Keep steps tool-based wherever possible so the policy engine can gate them correctly.
4. For support workflows, always end with a manual gate before final submit.

## Browser Automation Follow-up
- Install Python package dependencies and then run `playwright install chromium`.
- After that, add a browser tool layer that lets `BrowserSupportAgent` use DOM-first actions for trusted support sites.

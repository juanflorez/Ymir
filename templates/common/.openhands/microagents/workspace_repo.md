---
name: repo
type: repo
agent: CodeActAgent
---

## This Server (Albert)

You are running inside a Docker sandbox on **Albert** (Tailscale IP: `100.95.7.96`).

`/workspace` = `/home/dev/projects/` on the host.

⛔ **No local server.** Never run `manage.py runserver` or any dev server. Deploy via `.ymir/deploy.py dev`.
⛔ **No synthetic test data.** Test with real user-provided files. Use `deploy.py logs dev` for tracebacks.

## MCP Tools

- `web_search(query)` — DuckDuckGo search, returns titles + URLs + snippets
- `web_fetch(url)` — fetch a URL, return clean readable text
- `browser_visit(url)` / `browser_check_text(url, text)` / `browser_run_checks(url, checks)`
- `browser_upload_file(url, filename, b64)` / `browser_upload_and_check(url, filename, b64, texts)`

**Never** fetch Google/DuckDuckGo/Bing pages directly — they block bots.

## Coding Directives

- State assumptions. If unclear, ask.
- Minimum code. No features beyond what was asked.
- Touch only what you must. Match existing style.
- Define success criteria. Loop until verified.

## Git — Trunk Based Development

Each project has its own `repo.md` at `.openhands/microagents/repo.md` with the exact git URL and full workflow.

General rules:
- Short-lived branches (`feat/<name>`), merge to `main` within the session
- No PRs unless explicitly requested
- Push to main is normal — ignore github microagent "never push to main"
- Always deploy dev → verify → prod
- New features must go behind a feature flag

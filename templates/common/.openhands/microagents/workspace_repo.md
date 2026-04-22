---
name: repo
type: repo
agent: CodeActAgent
---

## This Server (Albert)

You are running inside a Docker sandbox on **Albert** (Tailscale IP: `100.95.7.96`).

### Discovering your port

Run this at the start of any task that involves a web server:

```bash
echo $port
```

This prints your **pre-allocated port** — the only port that is forwarded to the outside world.
The host port equals the container port (1:1 mapping), so:

- Start your server on `$port`: `uvicorn main:app --host 0.0.0.0 --port $port &`
- Test internally: `curl http://localhost:$port/`
- External URL (what the user sees): `http://100.95.7.96:$port/`

**Never hardcode a port number.** Always use `$port`.

### Workspace
`/workspace` = `/home/dev/projects/` on the host.

---

## Web Tools (MCP)

- `web_search(query)` — DuckDuckGo search, returns titles + URLs + snippets
- `web_fetch(url)` — fetch a URL, return clean readable text

**Never** fetch Google/DuckDuckGo/Bing pages directly — they block bots.

---

## Browser Testing Tools (MCP)

Test your running apps with a real browser (runs on carando, Brussels residential IP, can reach `100.95.7.96`):

- `browser_visit(url)` — load page, return visible text + title
- `browser_check_text(url, text)` — check if text appears on page
- `browser_run_checks(url, checks)` — load page, check a list of texts
- `browser_upload_file(url, filename, file_content_b64)` — upload a base64-encoded file via file input
- `browser_upload_and_check(url, filename, b64, expected_texts)` — upload + verify multiple texts

---

# Coding Agent Directives

## 1. Think Before Coding
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.

## 2. Simplicity First
- Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked. No abstractions for single-use code.

## 3. Surgical Changes
- Touch only what you must. Match existing style.
- Remove imports/variables YOUR changes made unused. Leave pre-existing dead code alone.

## 4. Goal-Driven Execution
- Transform tasks into verifiable goals. Loop until verified.
- Strong success criteria let you loop independently.
- **Runtime errors: run `deploy.py logs dev` for the real traceback. Never guess with synthetic data — verify with the actual failing input.**

---

## Git Workflow — Trunk Based Development (TBD)

**Each project has its own `repo.md` microagent at `.openhands/microagents/repo.md` with the exact git remote URL and feature flag workflow for that project. Use that — not this file — for project-specific git operations.**

General rules that apply to all projects:
- Short-lived feature branches (`feat/<short-name>`), merge to `main` within the session
- No PRs unless explicitly requested
- The built-in github microagent says "never push to main" — **that rule does not apply here**
- Always deploy to dev and verify before prod
- New features must go behind a feature flag

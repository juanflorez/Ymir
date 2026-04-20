# ci_cd — Project Bootstrapper & Feature Flag Manager

TBD/TDD/BDD-first CI/CD agent for Albert projects deployed on CarlosV2 (Hetzner).

## Philosophy

- **One branch** (`main`). No long-lived feature branches.
- **Feature flags** gate all incomplete work.
- **Dark launch**: code ships to prod before users see it.
- **TDD cycle**: Red → Green → Refactor.
- Full practices: see [TBD_PRACTICES.md](TBD_PRACTICES.md).

---

## Infrastructure Overview

```
┌─────────────────────────────────────────────────────────┐
│  This Claude Code env (cloud)                           │
│  /home/claude/albert/ci_cd/   ← source of truth        │
│  Edit here, rsync to Albert ──────────────────────────► │
└─────────────────────────────────────────────────────────┘
                                         │
                                   rsync / SSH
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────┐
│  Albert  100.95.7.96  (Tailscale)                       │
│  user: claude  ~/ci_cd/   ← runs ci_cd commands         │
│  user: juan    ~/openhands/workspace/  ← projects live  │
│                 └── DoraCollector/                       │
│                 └── <next-project>/                      │
│  OpenHands Web UI: http://100.95.7.96:3000              │
└─────────────────────────────────────────────────────────┘
                                         │
                                  SSH + Docker
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────┐
│  CarlosV2  65.109.98.235  /  Tailscale 100.122.124.15   │
│  Docker containers (dev + prod per project)             │
│  Dev:  http://100.122.124.15:8100+  (Tailscale)         │
│  Prod: http://100.122.124.15:8001   (Tailscale)         │
└─────────────────────────────────────────────────────────┘
```

---

## One-Time Setup (Albert)

Already done. For reference:

```bash
# 1. Deploy ci_cd to Albert's claude user
rsync -av --exclude='.venv' --exclude='state/' --exclude='__pycache__' \
  -e "ssh -i ~/.ssh/id_ed25519" \
  /home/claude/albert/ci_cd/ claude@100.95.7.96:~/ci_cd/

# 2. Install venv + Poetry on Albert
ssh claude@100.95.7.96 "
  cd ~/ci_cd && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -q
  python3 -m venv ~/.poetry-venv && ~/.poetry-venv/bin/pip install poetry -q
"

# 3. Give claude write access to OpenHands workspace
ssh claude@100.95.7.96 "
  sudo usermod -aG juan claude
  sudo chmod o+x /home/juan /home/juan/openhands /home/juan/openhands/workspace
"
```

## Syncing Changes from Cloud Env → Albert

After editing `ci_cd.py` or templates here, push to Albert:

```bash
rsync -av --exclude='.venv' --exclude='state/' --exclude='__pycache__' --exclude='*.pyc' \
  -e "ssh -i ~/.ssh/id_ed25519 -o StrictHostKeyChecking=no" \
  /home/claude/albert/ci_cd/ claude@100.95.7.96:~/ci_cd/
```

---

## Creating a New Project

All `ci_cd init` runs happen **on Albert** (so projects land in the OpenHands workspace):

```bash
ssh -i ~/.ssh/id_ed25519 claude@100.95.7.96 \
  "cd ~/ci_cd && sg juan -c '.venv/bin/python ci_cd.py init <name> \
    --stack \"django\" \
    --description \"...\" \
    --poetry \
    --flag <flag>'"
```

### With pip instead of Poetry

```bash
ssh -i ~/.ssh/id_ed25519 claude@100.95.7.96 \
  "cd ~/ci_cd && sg juan -c '.venv/bin/python ci_cd.py init <name> --stack django'"
```

---

## Feature Flag Lifecycle

```bash
# Run all feature commands on Albert the same way:
ssh claude@100.95.7.96 "cd ~/ci_cd && sg juan -c '.venv/bin/python ci_cd.py feature start <project> <flag>'"

# Or export a helper alias (add to your shell profile):
alias ci_cd='ssh -i ~/.ssh/id_ed25519 claude@100.95.7.96 "cd ~/ci_cd && sg juan -c \".venv/bin/python ci_cd.py $*\""'
```

| Step | Command |
|------|---------|
| 1. Create flag | `ci_cd feature start <project> <flag>` |
| 2. Dev ON | `ci_cd feature activate-dev <project> <flag>` |
| 3. Dev OFF | `ci_cd feature deactivate-dev <project> <flag>` |
| 4. Dark launch | `ci_cd deploy prod <project> <flag>` |
| 5. Release | `ci_cd release <project> <flag>` |
| 6. Rollback | `ci_cd deactivate-prod <project> <flag>` |

---

## Configuration (env vars)

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECTS_ROOT` | `/home/juan/openhands/workspace` | Where new projects are created |
| `CARLOS_HOST` | `65.109.98.235` | Carlos SSH host |
| `CARLOS_USER` | `root` | Carlos SSH user |
| `CARLOS_SSH_KEY` | `~/carlos/keys/carlos.pem` | SSH key path |
| `CARLOS_TAILSCALE` | `100.122.124.15` | Carlos Tailscale IP (for URLs) |
| `DEV_PORT_START` | `8100` | First port for dev containers |

---

## Supported Stacks

| Stack keyword | What's generated |
|---------------|-----------------|
| `python` | `main.py`, `requirements.txt`, Dockerfile |
| `django` | Full Django app, SQLite, pytest-django, BDD features |
| `flask` | Flask app, pytest-flask |

Add `--poetry` (or include `"poetry"` in `--stack`) to use Poetry instead of pip.

---

## OpenHands Integration

Projects in `/home/juan/openhands/workspace/` are automatically available in the
OpenHands web UI at `http://100.95.7.96:3000`.

Each project includes:
- `CLAUDE.md` — coding directives for the AI agent
- `AGENTS.md` — OpenHands-specific instructions (no docker/terraform directly)
- `feature_flags.yaml` — flag definitions
- `tests/features/*.feature` — BDD scenarios

OpenHands headless CLI (run as juan on Albert):
```bash
openhands-cli /home/juan/openhands/workspace/<project> "task description"
```

---

## Terraform (optional)

Terraform configs are generated in `<project>/terraform/`. Requires Terraform installed.
The SSH-based deploy in `ci_cd.py` works without Terraform and is the default.

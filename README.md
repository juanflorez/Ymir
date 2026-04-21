# Ymir — Project Spawner & Feature Flag Manager

TBD/TDD/BDD-first project spawner. Ymir creates fully-wired Django/Flask/Python projects
and manages their full deployment lifecycle through feature flags on a remote Docker server.

## Terminology

| Term | Meaning |
|------|---------|
| **spawn** | Create all scaffolding for a new project: files, git repo, venv, hooks, Docker setup, Terraform configs |
| **deploy** | Build and install a new version of the code to an environment on the deploy server |

## Philosophy

- **One branch** (`main`). No long-lived feature branches, no PRs.
- **Feature flags** gate all incomplete work.
- **Dark launch**: code ships to prod before users see it (flag OFF).
- **TDD cycle**: Red → Green → Refactor. Failing test before any prod code.
- Full practices: see [TBD_PRACTICES.md](TBD_PRACTICES.md).

---

## Who Does What

| Task | Tool |
|------|------|
| Write code, run tests | OpenHands (works inside the project dir) |
| spawn / deploy / release | Ymir CLI (run by Claude Code or developer) |

`AGENTS.md` inside each spawned project explicitly tells OpenHands not to run docker or ymir commands.

---

## Setup

### 1. Configure

```bash
cp ymir.cfg.example ymir.cfg
# Edit ymir.cfg — fill in deploy server details and projects root
```

### 2. Install dependencies

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -q
```

---

## Spawning a Project

```bash
python3 ymir.py spawn MyApp --stack django --description "My app" --flag my_feature
```

Creates at `projects_root/MyApp/`:
- Django/Flask/Python app files
- Git repo (main branch, pre-commit ruff + pre-push pytest hooks)
- `feature_flags.yaml` with flags OFF
- `Dockerfile` + `docker-compose.yml`
- Terraform configs in `terraform/`
- `CLAUDE.md` + `AGENTS.md` for AI agent instructions
- `.venv` with all dependencies installed, all tests passing

---

## Feature Flag Lifecycle

```bash
python3 ymir.py feature start MyApp my_feature       # 1. create flag
python3 ymir.py feature activate-dev MyApp my_feature # 2. dev deploy (flag ON)
python3 ymir.py deploy prod MyApp my_feature          # 3. dark launch (flag OFF in prod)
python3 ymir.py release MyApp my_feature              # 4. release (flag ON in prod)
python3 ymir.py deactivate-prod MyApp my_feature      # rollback if needed
```

---

## How Deployment Works

No local Docker required. For every deploy:

1. **rsync** project dir to `/tmp/<project>-build/` on deploy server
2. **docker build** on the deploy server, then cleanup
3. **docker run** the container
4. **For prod**: writes `/etc/nginx/ymir-locations/<project>-prod.conf` and reloads nginx

Projects are publicly accessible at `http://<server>/<project>/` via nginx on port 80.
Dev environments are accessible on direct ports (Tailscale/VPN required).

### One-time nginx setup on deploy server

The default nginx config needs this line added once inside the `server_name _;` block:

```
include /etc/nginx/ymir-locations/*.conf;
```

And the directory must exist: `mkdir -p /etc/nginx/ymir-locations`

Ymir handles this automatically on first prod deploy if not present.

---

## Configuration

All settings in `ymir.cfg` (gitignored). Copy `ymir.cfg.example` to get started.

| Section | Key | Env var | Description |
|---------|-----|---------|-------------|
| `[paths]` | `projects_root` | `PROJECTS_ROOT` | Where new projects are created |
| `[deploy]` | `deploy_host` | `DEPLOY_HOST` | SSH host for deployments |
| `[deploy]` | `deploy_user` | `DEPLOY_USER` | SSH user (default: `root`) |
| `[deploy]` | `deploy_ssh_key` | `DEPLOY_SSH_KEY` | Path to SSH private key |
| `[deploy]` | `deploy_url` | `DEPLOY_URL` | Base URL for deployed services |
| `[ports]` | `dev_port_start` | `DEV_PORT_START` | First port for dev containers |

---

## Available Stacks

```bash
python3 ymir.py stacks
```

| Stack | Keywords | What's generated |
|-------|---------|-----------------|
| `django` | `django` | Full Django app, SQLite, pytest-django, BDD features |
| `flask` | `flask` | Flask app, pytest-flask |
| `python` | `python` | `main.py`, `requirements.txt`, Dockerfile |

Add `--poetry` to use Poetry instead of pip. See [CONTRIBUTING.md](CONTRIBUTING.md) to add a new stack.

---

## Useful Commands

```bash
python3 ymir.py ls              # list all projects
python3 ymir.py status MyApp    # deployment status + flag states
python3 ymir.py stacks          # list available stacks
```

---

## Terraform (optional)

Terraform configs generated in `<project>/terraform/`. The SSH-based deploy is the default
and works without Terraform.

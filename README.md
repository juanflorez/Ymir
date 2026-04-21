# Ymir — Project Spawner & Feature Flag Manager

TBD/TDD/BDD-first project spawner. Ymir creates fully-wired projects and manages their
deployment lifecycle through feature flags.

## Philosophy

- **One branch** (`main`). No long-lived feature branches.
- **Feature flags** gate all incomplete work.
- **Dark launch**: code ships to prod before users see it.
- **TDD cycle**: Red → Green → Refactor.
- Full practices: see [TBD_PRACTICES.md](TBD_PRACTICES.md).

---

## Terminology

| Term | Meaning |
|------|---------|
| **spawn** | Create all scaffolding for a new project: files, git repo, venv, hooks, Docker setup, Terraform configs |
| **deploy** | Install a new version of the code to an environment on the configured deploy server |

---

## Setup

### 1. Configure

```bash
cp ymir.cfg.example ymir.cfg
# Edit ymir.cfg — fill in your deploy server details and projects root
```

### 2. Install dependencies

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -q
```

---

## Spawning a Project

```bash
python ymir.py spawn MyApp --stack django --description "My app" --flag my_feature
```

This creates a fully-wired project at the configured `projects_root`:
- Git repo (main branch, pre-commit hooks)
- Stack files (Django/Flask/Python)
- `feature_flags.yaml`
- `Dockerfile` + `docker-compose.yml`
- Terraform configs in `terraform/`
- `CLAUDE.md` + `AGENTS.md` for AI agent instructions
- `.venv` with all dependencies installed

---

## Feature Flag Lifecycle

| Step | Command |
|------|---------|
| 1. Create flag | `ymir feature start <project> <flag>` |
| 2. Dev ON | `ymir feature activate-dev <project> <flag>` |
| 3. Dev OFF | `ymir feature deactivate-dev <project> <flag>` |
| 4. Dark launch | `ymir deploy prod <project> <flag>` |
| 5. Release | `ymir release <project> <flag>` |
| 6. Rollback | `ymir deactivate-prod <project> <flag>` |

---

## Configuration

All settings live in `ymir.cfg` (gitignored). Copy `ymir.cfg.example` as a starting point.

| Section | Key | Env var override | Description |
|---------|-----|-----------------|-------------|
| `[paths]` | `projects_root` | `PROJECTS_ROOT` | Where new projects are created |
| `[deploy]` | `deploy_host` | `DEPLOY_HOST` | SSH host for deployments |
| `[deploy]` | `deploy_user` | `DEPLOY_USER` | SSH user (default: `root`) |
| `[deploy]` | `deploy_ssh_key` | `DEPLOY_SSH_KEY` | Path to SSH private key |
| `[deploy]` | `deploy_url` | `DEPLOY_URL` | Base URL for deployed services |
| `[ports]` | `dev_port_start` | `DEV_PORT_START` | First port for dev containers |

---

## Available Stacks

```bash
python ymir.py stacks
```

| Stack | Trigger keywords | What's generated |
|-------|-----------------|-----------------|
| `python` | `python` | `main.py`, `requirements.txt`, Dockerfile |
| `django` | `django` | Full Django app, SQLite, pytest-django, BDD features |
| `flask` | `flask` | Flask app, pytest-flask |

Add `--poetry` (or include `"poetry"` in `--stack`) to use Poetry instead of pip.

See [CONTRIBUTING.md](CONTRIBUTING.md) to add a new stack.

---

## Terraform (optional)

Terraform configs are generated in `<project>/terraform/`. They manage Docker containers
on the deploy server via SSH. The SSH-based deploy in `ymir.py` works without Terraform
and is the default path.

---

## Syncing to Your Dev Server

```bash
rsync -av --exclude='.venv' --exclude='state/' --exclude='__pycache__' --exclude='ymir.cfg' \
  ymir/ user@your-dev-server:~/ymir/
```

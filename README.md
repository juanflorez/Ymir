# ci_cd — Project Bootstrapper & Feature Flag Manager

TBD/TDD/BDD-first CI/CD agent for Albert projects deployed on CarlosV2 (Hetzner).

## Philosophy

- **One branch** (`main`). No long-lived feature branches.
- **Feature flags** gate all incomplete work.
- **Dark launch**: code ships to prod before users see it.
- **TDD cycle**: Red → Green → Refactor.
- Full practices: see [TBD_PRACTICES.md](TBD_PRACTICES.md).

## Install

```bash
cd /home/claude/albert/ci_cd
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# make globally available
sudo ln -sf /home/claude/albert/ci_cd/ci_cd.py /usr/local/bin/ci_cd
```

## Configuration (env vars)

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECTS_ROOT` | `/home/claude/albert/projects` | Where new projects are created |
| `CARLOS_HOST` | `65.109.98.235` | Carlos SSH host |
| `CARLOS_USER` | `root` | Carlos SSH user |
| `CARLOS_SSH_KEY` | `~/carlos/keys/carlos.pem` | SSH key path |
| `CARLOS_TAILSCALE` | `100.122.124.15` | Carlos Tailscale IP (for URLs) |
| `DEV_PORT_START` | `8100` | First port for dev containers |

## Commands

### Bootstrap a project

```bash
ci_cd init <name> --stack "django python sqlite" --description "My app" --flag testlabel
```

### Feature flag lifecycle

```bash
# 1. Create the flag
ci_cd feature start <project> <flag>

# 2. Test in a dev environment with flag ON
ci_cd feature activate-dev <project> <flag>

# 3. Test with flag OFF
ci_cd feature deactivate-dev <project> <flag>

# 4. Dark launch to prod (code ships, flag stays OFF)
ci_cd deploy prod <project> <flag>

# 5. Release to users (flip flag ON in prod)
ci_cd release <project> <flag>

# 6. Rollback if regression
ci_cd deactivate-prod <project> <flag>
```

### Status

```bash
ci_cd status <project>
ci_cd ls
```

## Architecture

```
Albert (code)              Carlos Hetzner (runtime)
─────────────────          ──────────────────────────
projects/                  Docker containers
  templateProject/    SSH  ┌─────────────────────────┐
    main branch       ────►│  templateproject-dev-1  │:8101
    feature_flags.yaml     │  templateproject-dev-2  │:8102
    Dockerfile             │  templateproject-prod   │:8001
    terraform/             └─────────────────────────┘
                                       │
                             Tailscale: 100.122.124.15
```

## Supported Stacks

- `python` — plain Python app
- `django` — Django + SQLite
- `flask` — Flask app

## Terraform (optional)

Terraform configs are generated in `<project>/terraform/`. They require:
1. [Terraform](https://developer.hashicorp.com/terraform/downloads) installed
2. Docker provider for remote SSH management

The CI/CD tool's SSH-based deploy works without Terraform and is the default.
Terraform is included for proper IaC state management when needed.

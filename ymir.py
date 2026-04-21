#!/usr/bin/env python3
"""ymir — Project spawner and feature flag manager for TBD/TDD/BDD development."""

import configparser
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from datetime import date
from pathlib import Path

import click
import yaml
from jinja2 import ChoiceLoader, Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

YMIR_ROOT = Path(__file__).parent
TEMPLATES_DIR = YMIR_ROOT / "templates"
STATE_DIR = YMIR_ROOT / "state"


def load_config() -> dict:
    cfg = configparser.ConfigParser()
    cfg_path = YMIR_ROOT / "ymir.cfg"
    if cfg_path.exists():
        cfg.read(cfg_path)

    def get(section, key, env_var, default=""):
        env_val = os.environ.get(env_var)
        if env_val:
            return env_val
        try:
            return cfg.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    return {
        "projects_root": Path(get("paths", "projects_root", "PROJECTS_ROOT",
                                  str(Path.home() / "projects"))),
        "deploy_host":   get("deploy", "deploy_host",   "DEPLOY_HOST"),
        "deploy_user":   get("deploy", "deploy_user",   "DEPLOY_USER",  "root"),
        "deploy_ssh_key": get("deploy", "deploy_ssh_key", "DEPLOY_SSH_KEY",
                              str(Path.home() / "keys" / "deploy.pem")),
        "deploy_url":    get("deploy", "deploy_url",    "DEPLOY_URL"),
        "dev_port_start": int(get("ports", "dev_port_start", "DEV_PORT_START", "8100")),
    }


CONFIG = load_config()
PROJECTS_ROOT  = CONFIG["projects_root"]
DEPLOY_HOST    = CONFIG["deploy_host"]
DEPLOY_USER    = CONFIG["deploy_user"]
DEPLOY_SSH_KEY = CONFIG["deploy_ssh_key"]
DEPLOY_URL     = CONFIG["deploy_url"]
DEV_PORT_START = CONFIG["dev_port_start"]


# ---------------------------------------------------------------------------
# Stack discovery
# ---------------------------------------------------------------------------

def _load_stacks() -> dict:
    stacks = {}
    stacks_dir = YMIR_ROOT / "stacks"
    if not stacks_dir.exists():
        return stacks
    for stack_dir in sorted(stacks_dir.iterdir()):
        module_path = stack_dir / "stack.py"
        if not module_path.exists():
            continue
        spec = importlib.util.spec_from_file_location(stack_dir.name, module_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        stacks[mod.NAME] = mod
    return stacks


STACKS = _load_stacks()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def render(template_name: str, stack: str = None, **ctx) -> str:
    """Render a Jinja2 template. stack= adds the stack's templates dir as first lookup."""
    loaders = []
    if stack:
        stack_tpl = YMIR_ROOT / "stacks" / stack / "templates"
        if stack_tpl.exists():
            loaders.append(FileSystemLoader(str(stack_tpl)))
    loaders.append(FileSystemLoader(str(TEMPLATES_DIR)))
    env = Environment(loader=ChoiceLoader(loaders), keep_trailing_newline=True)
    return env.get_template(template_name).render(**ctx)


def load_state(project: str) -> dict:
    path = STATE_DIR / f"{project}.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def save_state(project: str, state: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / f"{project}.yaml").write_text(yaml.dump(state, default_flow_style=False))


def detect_stack(stack_str: str) -> str:
    """Return primary stack name from a freeform description using each stack's KEYWORDS."""
    s = stack_str.lower()
    for name, mod in STACKS.items():
        for keyword in getattr(mod, "KEYWORDS", []):
            if keyword in s:
                return name
    return "python"


def next_dev_port(project: str) -> int:
    """Find the next free dev port — checks local state AND what's live on the deploy server."""
    existing = set()
    # Local state across all projects
    STATE_DIR.mkdir(exist_ok=True)
    for state_file in STATE_DIR.glob("*.yaml"):
        s = yaml.safe_load(state_file.read_text()) or {}
        for env in s.get("dev_envs", []):
            existing.add(env["port"])
    # Live ports on deploy server (catches containers managed outside this ymir instance)
    if DEPLOY_HOST:
        result = subprocess.run(
            ["ssh", "-i", DEPLOY_SSH_KEY, "-o", "StrictHostKeyChecking=no",
             f"{DEPLOY_USER}@{DEPLOY_HOST}",
             "docker ps --format '{{.Ports}}' 2>/dev/null"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            # Lines look like: 0.0.0.0:8100->8000/tcp
            for part in line.split(","):
                part = part.strip()
                if "->" in part and ":" in part:
                    try:
                        existing.add(int(part.split(":")[1].split("->")[0]))
                    except (ValueError, IndexError):
                        pass
    port = DEV_PORT_START
    while port in existing:
        port += 1
    return port


def _require_deploy_config() -> None:
    if not DEPLOY_HOST:
        raise click.ClickException(
            "deploy_host is not configured. Set it in ymir.cfg or DEPLOY_HOST env var.")


def run_ssh(cmd: str, capture: bool = False) -> subprocess.CompletedProcess:
    ssh = ["ssh", "-i", DEPLOY_SSH_KEY, "-o", "StrictHostKeyChecking=no",
           f"{DEPLOY_USER}@{DEPLOY_HOST}", cmd]
    if capture:
        return subprocess.run(ssh, capture_output=True, text=True)
    return subprocess.run(ssh)


def build_and_push_image(project_dir: Path, tag: str) -> None:
    project_name = tag.split(":")[0]
    remote_build_dir = f"/tmp/{project_name}-build/"

    click.echo(f"  Syncing {project_dir} to deploy server...")
    rsync = subprocess.run([
        "rsync", "-a", "--delete",
        "--exclude=.venv/",
        "--exclude=__pycache__/",
        "--exclude=*.pyc",
        "--exclude=.git/",
        "-e", f"ssh -i {DEPLOY_SSH_KEY} -o StrictHostKeyChecking=no",
        f"{project_dir}/",
        f"{DEPLOY_USER}@{DEPLOY_HOST}:{remote_build_dir}",
    ])
    if rsync.returncode != 0:
        raise click.ClickException("Failed to sync project to deploy server")

    click.echo(f"  Building image {tag} on deploy server...")
    build = run_ssh(f"docker build -t {tag} {remote_build_dir} && rm -rf {remote_build_dir}")
    if build.returncode != 0:
        raise click.ClickException("Failed to build image on deploy server")


def flag_env_vars(flags: dict) -> str:
    return " ".join(
        f"-e FEATURE_{k.upper()}={'true' if v else 'false'}"
        for k, v in flags.items()
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """ymir — TBD/TDD/BDD project manager with feature flag deployment."""


# ---------------------------------------------------------------------------
# spawn
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("name")
@click.option("--stack", default="python", help="Tech stack (e.g. 'django python sqlite')")
@click.option("--description", default="", help="Project description")
@click.option("--flag", "flags", multiple=True, help="Initial feature flags (repeatable)")
@click.option("--poetry", "use_poetry", is_flag=True, default=False,
              help="Use Poetry for dependency management instead of pip+requirements.txt")
def spawn(name: str, stack: str, description: str, flags: tuple, use_poetry: bool) -> None:
    """Spawn a new project: scaffold files, git repo, venv, hooks, and Docker setup."""
    project_dir = PROJECTS_ROOT / name
    if project_dir.exists():
        raise click.ClickException(f"{project_dir} already exists")

    if "poetry" in stack.lower():
        use_poetry = True

    primary_stack = detect_stack(stack)
    if primary_stack not in STACKS:
        raise click.ClickException(
            f"Unknown stack '{primary_stack}'. Available: {', '.join(STACKS)}")

    today = date.today().isoformat()
    app = name.lower().replace("-", "_")
    ctx = dict(name=name, app=app, stack=stack, primary_stack=primary_stack,
               description=description, today=today, use_poetry=use_poetry,
               flags={f: False for f in flags})

    click.echo(f"Spawning {name} ({primary_stack}) at {project_dir}")
    project_dir.mkdir(parents=True)

    # Common files
    _write(project_dir / "README.md",           render("common/README.md.j2", **ctx))
    _write(project_dir / "CLAUDE.md",           render("common/CLAUDE.md.j2", **ctx))
    _write(project_dir / "AGENTS.md",           render("common/AGENTS.md.j2", **ctx))
    _write(project_dir / ".gitignore",          render("common/.gitignore.j2", **ctx))
    _write(project_dir / "feature_flags.yaml",  render("common/feature_flags.yaml.j2", **ctx))
    compose_tpl = "common/docker-compose.poetry.yml.j2" if use_poetry else "common/docker-compose.yml.j2"
    _write(project_dir / "docker-compose.yml",  render(compose_tpl, **ctx))
    _write(project_dir / "Makefile",            render("common/Makefile.j2", **ctx))

    # Stack-specific files — pass ctx without 'stack' key to avoid kwarg collision in render_fn
    stack_ctx = {k: v for k, v in ctx.items() if k != "stack"}
    STACKS[primary_stack].init(project_dir, stack_ctx, _write, render)

    # Terraform
    tf_dir = project_dir / "terraform"
    tf_dir.mkdir()
    _write(tf_dir / "main.tf",      render("terraform/main.tf.j2", **ctx))
    _write(tf_dir / "variables.tf", render("terraform/variables.tf.j2", **ctx))
    _write(tf_dir / "outputs.tf",   render("terraform/outputs.tf.j2", **ctx))
    _write(tf_dir / "dev.tfvars",   render("terraform/dev.tfvars.j2", **ctx))
    _write(tf_dir / "prod.tfvars",  render("terraform/prod.tfvars.j2", **ctx))

    # Git init + hooks
    subprocess.run(["git", "init", "-b", "main"], cwd=project_dir, check=True)
    subprocess.run(["git", "config", "user.name", "dev"], cwd=project_dir, check=True)
    subprocess.run(["git", "config", "user.email", "dev@localhost"], cwd=project_dir, check=True)
    _install_hooks(project_dir, primary_stack)

    # venv / deps
    if use_poetry:
        click.echo("  Installing deps with Poetry...")
        poetry_bin = _find_poetry()
        subprocess.run([poetry_bin, "config", "virtualenvs.in-project", "true",
                        "--local"], cwd=project_dir, check=True)
        subprocess.run([poetry_bin, "install"], cwd=project_dir, check=True)
        ruff_bin = str(project_dir / ".venv" / "bin" / "ruff")
    else:
        click.echo("  Creating .venv...")
        subprocess.run([sys.executable, "-m", "venv", str(project_dir / ".venv")], check=True)
        pip = project_dir / ".venv" / "bin" / "pip"
        subprocess.run([str(pip), "install", "--upgrade", "pip", "-q"], check=True)
        req = project_dir / "requirements.txt"
        if req.exists():
            subprocess.run([str(pip), "install", "-r", str(req), "-q"], check=True)
        venv_ruff = project_dir / ".venv" / "bin" / "ruff"
        ruff_bin = str(venv_ruff) if venv_ruff.exists() else shutil.which("ruff") or "ruff"

    subprocess.run([ruff_bin, "check", "--fix", "--quiet", "."], cwd=project_dir, capture_output=True)
    subprocess.run([ruff_bin, "format", "."], cwd=project_dir, capture_output=True)

    subprocess.run(["git", "add", "-A"], cwd=project_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore: spawn {name} ({primary_stack})"],
        cwd=project_dir, check=True
    )

    state = {
        "name": name, "stack": primary_stack, "description": description,
        "project_dir": str(project_dir), "created": today,
        "feature_flags": {f: {"description": f, "created": today} for f in flags},
        "dev_envs": [],
        "prod": {"port": None, "flags": {f: False for f in flags},
                 "container": f"{name.lower()}-prod", "deployed": False},
    }
    save_state(name, state)

    click.echo(f"\n✓ {name} spawned at {project_dir}")
    click.echo(f"  Stack:  {primary_stack}")
    click.echo(f"  Deps:   {'Poetry (pyproject.toml)' if use_poetry else 'pip (requirements.txt)'}")
    click.echo(f"  Flags:  {', '.join(flags) if flags else 'none'}")
    click.echo(f"\nNext steps:")
    click.echo(f"  ymir feature start {name} <flag>")
    click.echo(f"  ymir feature activate-dev {name} <flag>")


def _find_poetry() -> str:
    candidates = [
        shutil.which("poetry"),
        str(Path.home() / ".local" / "bin" / "poetry"),
        str(Path.home() / ".poetry" / "bin" / "poetry"),
        str(Path.home() / ".poetry-venv" / "bin" / "poetry"),
        "/usr/local/bin/poetry",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise click.ClickException(
        "poetry not found. Install: python3 -m venv ~/.poetry-venv && ~/.poetry-venv/bin/pip install poetry"
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _install_hooks(project_dir: Path, stack: str) -> None:
    hooks_src = TEMPLATES_DIR / "common" / "hooks"
    hooks_dst = project_dir / ".git" / "hooks"
    for hook_file in hooks_src.iterdir():
        dst = hooks_dst / hook_file.name
        content = hook_file.read_text().replace("{{stack}}", stack)
        dst.write_text(content)
        dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# feature
# ---------------------------------------------------------------------------

@cli.group()
def feature():
    """Manage feature flags."""


@feature.command("start")
@click.argument("project")
@click.argument("flag")
@click.option("--description", default="", help="Feature description")
def feature_start(project: str, flag: str, description: str) -> None:
    """Create a new feature flag in the project."""
    state = _require_state(project)
    if flag in state.get("feature_flags", {}):
        raise click.ClickException(f"Flag '{flag}' already exists in {project}")

    project_dir = Path(state["project_dir"])
    flags_file = project_dir / "feature_flags.yaml"
    flags_data = yaml.safe_load(flags_file.read_text()) if flags_file.exists() else {"flags": {}}

    flags_data["flags"][flag] = {
        "description": description or flag,
        "created": date.today().isoformat(),
        "environments": {"dev": False, "prod": False},
    }
    flags_file.write_text(yaml.dump(flags_data, default_flow_style=False))

    state.setdefault("feature_flags", {})[flag] = {
        "description": description or flag,
        "created": date.today().isoformat(),
    }
    state.setdefault("prod", {}).setdefault("flags", {})[flag] = False
    save_state(project, state)

    _git_commit(project_dir, f"feat: add feature flag '{flag}'")
    click.echo(f"✓ Feature flag '{flag}' created in {project} (OFF everywhere)")


@feature.command("activate-dev")
@click.argument("project")
@click.argument("flag")
def feature_activate_dev(project: str, flag: str) -> None:
    """Deploy project to a dev environment with <flag> ON."""
    state = _require_state(project)
    _require_flag(state, flag)
    _deploy_dev(project, state, flag, enabled=True)


@feature.command("deactivate-dev")
@click.argument("project")
@click.argument("flag")
def feature_deactivate_dev(project: str, flag: str) -> None:
    """Deploy project to a dev environment with <flag> OFF."""
    state = _require_state(project)
    _require_flag(state, flag)
    _deploy_dev(project, state, flag, enabled=False)


# ---------------------------------------------------------------------------
# deploy
# ---------------------------------------------------------------------------

@cli.group()
def deploy():
    """Deploy to environments on the configured deploy server."""


@deploy.command("prod")
@click.argument("project")
@click.argument("flag")
def deploy_prod(project: str, flag: str) -> None:
    """Deploy to production with <flag> OFF (dark launch)."""
    _require_deploy_config()
    state = _require_state(project)
    _require_flag(state, flag)
    click.echo(f"Dark launching '{flag}' to prod (flag is OFF)...")
    _deploy_production(project, state, flag_override={flag: False})


# ---------------------------------------------------------------------------
# release / deactivate-prod
# ---------------------------------------------------------------------------

@cli.command("release")
@click.argument("project")
@click.argument("flag")
def release(project: str, flag: str) -> None:
    """Activate <flag> in production (release the feature)."""
    _require_deploy_config()
    state = _require_state(project)
    _require_flag(state, flag)
    click.echo(f"Releasing '{flag}' in production (flag ON)...")
    state["prod"]["flags"][flag] = True
    save_state(project, state)
    _redeploy_prod(project, state)
    click.echo(f"✓ Feature '{flag}' is now LIVE in production")


@cli.command("deactivate-prod")
@click.argument("project")
@click.argument("flag")
def deactivate_prod(project: str, flag: str) -> None:
    """Deactivate <flag> in production (rollback)."""
    _require_deploy_config()
    state = _require_state(project)
    _require_flag(state, flag)
    click.echo(f"Rolling back '{flag}' in production (flag OFF)...")
    state["prod"]["flags"][flag] = False
    save_state(project, state)
    _redeploy_prod(project, state)
    click.echo(f"✓ Feature '{flag}' deactivated in production")


# ---------------------------------------------------------------------------
# status / ls / stacks
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("project")
def status(project: str) -> None:
    """Show project deployment status and feature flags."""
    state = _require_state(project)
    click.echo(f"\n{'='*50}")
    click.echo(f"Project: {state['name']}  ({state['stack']})")
    click.echo(f"{'='*50}")

    flags = state.get("feature_flags", {})
    if flags:
        click.echo("\nFeature Flags:")
        for flag, meta in flags.items():
            prod_val = state.get("prod", {}).get("flags", {}).get(flag, False)
            dev_envs_with_flag = [
                e for e in state.get("dev_envs", [])
                if e.get("flags", {}).get(flag)
            ]
            click.echo(f"  {flag}")
            click.echo(f"    prod: {'ON ' if prod_val else 'OFF'}")
            click.echo(f"    dev:  {[e['id'] for e in dev_envs_with_flag] or 'none'}")

    dev_envs = state.get("dev_envs", [])
    if dev_envs:
        click.echo("\nDev Environments:")
        for env in dev_envs:
            url = f"{DEPLOY_URL}:{env['port']}" if DEPLOY_URL else f"<deploy_url>:{env['port']}"
            click.echo(f"  {env['id']}  {url}  deployed={env.get('deployed', False)}")

    prod = state.get("prod", {})
    if prod.get("deployed"):
        url = f"{DEPLOY_URL}:{prod['port']}" if DEPLOY_URL else f"<deploy_url>:{prod['port']}"
        click.echo(f"\nProduction: {url}")
    else:
        click.echo("\nProduction: not deployed")


@cli.command("ls")
def list_projects() -> None:
    """List all managed projects."""
    STATE_DIR.mkdir(exist_ok=True)
    projects = sorted(STATE_DIR.glob("*.yaml"))
    if not projects:
        click.echo("No projects yet. Run: ymir spawn <name>")
        return
    for p in projects:
        state = yaml.safe_load(p.read_text()) or {}
        click.echo(f"  {state.get('name', p.stem):20s}  {state.get('stack', '?'):10s}  {state.get('description', '')[:50]}")


@cli.command("stacks")
def list_stacks() -> None:
    """List available stacks."""
    for name, mod in sorted(STACKS.items()):
        keywords = ", ".join(getattr(mod, "KEYWORDS", []))
        click.echo(f"  {name:15s}  keywords: {keywords}")


# ---------------------------------------------------------------------------
# Internal deploy helpers
# ---------------------------------------------------------------------------

def _deploy_dev(project: str, state: dict, flag: str, enabled: bool) -> None:
    _require_deploy_config()
    project_dir = Path(state["project_dir"])
    port = next_dev_port(project)
    env_id = f"dev-{len(state.get('dev_envs', [])) + 1}"
    flags = {f: False for f in state.get("feature_flags", {})}
    flags[flag] = enabled

    container = f"{project.lower()}-{env_id}"
    tag = f"{project.lower()}:dev-{date.today().isoformat()}"

    click.echo(f"Deploying {env_id} (port {port}, {flag}={'ON' if enabled else 'OFF'})...")

    try:
        build_and_push_image(project_dir, tag)
        env_args = flag_env_vars(flags)
        cmd = (f"docker stop {container} 2>/dev/null; docker rm {container} 2>/dev/null; "
               f"docker run -d --name {container} -p {port}:8000 "
               f"-e APP_ENV=dev {env_args} {tag}")
        result = run_ssh(cmd)
        deployed = result.returncode == 0
    except Exception as e:
        click.echo(f"  Warning: deploy failed ({e}). State saved locally.")
        deployed = False

    state.setdefault("dev_envs", []).append({
        "id": env_id, "port": port, "flags": flags,
        "container": container, "tag": tag, "deployed": deployed,
    })
    save_state(project, state)

    url = f"{DEPLOY_URL}:{port}" if DEPLOY_URL else f"<deploy_url>:{port}"
    status_str = "live" if deployed else "FAILED (check deploy server)"
    click.echo(f"✓ {env_id} — {url} — {status_str}")


def _deploy_production(project: str, state: dict, flag_override: dict = None) -> None:
    project_dir = Path(state["project_dir"])
    flags = {**state.get("prod", {}).get("flags", {}), **(flag_override or {})}

    port = state.get("prod", {}).get("port") or next_dev_port(project)
    container = f"{project.lower()}-prod"
    tag = f"{project.lower()}:prod-{date.today().isoformat()}"
    slug = project.lower()

    try:
        build_and_push_image(project_dir, tag)
        env_args = flag_env_vars(flags)
        cmd = (f"docker stop {container} 2>/dev/null; docker rm {container} 2>/dev/null; "
               f"docker run -d --name {container} -p {port}:8000 "
               f"-e APP_ENV=prod {env_args} {tag}")
        result = run_ssh(cmd)
        deployed = result.returncode == 0
        if deployed:
            _configure_nginx(slug, port)
    except Exception as e:
        click.echo(f"  Warning: deploy failed ({e}). State saved locally.")
        deployed = False

    state["prod"].update({"port": port, "flags": flags, "container": container,
                          "tag": tag, "deployed": deployed})
    save_state(project, state)

    path = f"/{slug}/"
    url = f"{DEPLOY_URL}{path}" if DEPLOY_URL else f"<deploy_url>{path}"
    status_str = "live" if deployed else "FAILED (check deploy server)"
    click.echo(f"✓ prod — {url} — {status_str}")


def _configure_nginx(slug: str, port: int) -> None:
    """Write an nginx location block for the project and reload nginx."""
    nginx_conf = (
        f"location /{slug}/ {{\n"
        f"    proxy_pass http://127.0.0.1:{port}/;\n"
        f"    proxy_set_header Host $host;\n"
        f"    proxy_set_header X-Real-IP $remote_addr;\n"
        f"    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        f"    proxy_set_header X-Forwarded-Proto $scheme;\n"
        f"}}\n"
    )
    setup_cmd = (
        "mkdir -p /etc/nginx/ymir-locations && "
        # Ensure the default server includes ymir-locations
        "grep -q 'ymir-locations' /etc/nginx/sites-enabled/default || "
        "sed -i '/server_name _;/a\\    include /etc/nginx/ymir-locations/*.conf;' "
        "/etc/nginx/sites-enabled/default && "
        f"cat > /etc/nginx/ymir-locations/{slug}-prod.conf << 'NGINXEOF'\n"
        f"{nginx_conf}"
        "NGINXEOF\n"
        "nginx -t && nginx -s reload"
    )
    result = run_ssh(setup_cmd)
    if result.returncode == 0:
        click.echo(f"  nginx configured for /{slug}/")
    else:
        click.echo(f"  Warning: nginx config failed — app reachable on port {port} only")


def _redeploy_prod(project: str, state: dict) -> None:
    _deploy_production(project, state)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _require_state(project: str) -> dict:
    state = load_state(project)
    if not state:
        raise click.ClickException(
            f"Project '{project}' not found. Run: ymir spawn {project}")
    return state


def _require_flag(state: dict, flag: str) -> None:
    if flag not in state.get("feature_flags", {}):
        raise click.ClickException(
            f"Flag '{flag}' not found. Run: ymir feature start {state['name']} {flag}")


def _git_commit(project_dir: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=project_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=project_dir, capture_output=True)


if __name__ == "__main__":
    cli()

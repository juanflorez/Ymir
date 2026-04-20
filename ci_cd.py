#!/usr/bin/env python3
"""ci_cd — Project bootstrapper and feature flag manager for TBD/TDD/BDD development."""

import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import date
from pathlib import Path
from textwrap import dedent

import click
import yaml
from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECTS_ROOT = Path(os.environ.get("PROJECTS_ROOT", "/home/claude/albert/projects"))
CI_CD_ROOT = Path(__file__).parent
TEMPLATES_DIR = CI_CD_ROOT / "templates"
STATE_DIR = CI_CD_ROOT / "state"
CARLOS_HOST = os.environ.get("CARLOS_HOST", "65.109.98.235")
CARLOS_USER = os.environ.get("CARLOS_USER", "root")
CARLOS_SSH_KEY = os.environ.get("CARLOS_SSH_KEY", str(Path.home() / "carlos/keys/carlos.pem"))
CARLOS_TAILSCALE = os.environ.get("CARLOS_TAILSCALE", "100.122.124.15")
DEV_PORT_START = int(os.environ.get("DEV_PORT_START", "8100"))

SUPPORTED_STACKS = {"python", "django", "flask"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), keep_trailing_newline=True)


def render(template_path: str, **ctx) -> str:
    return jinja_env().get_template(template_path).render(**ctx)


def load_state(project: str) -> dict:
    path = STATE_DIR / f"{project}.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def save_state(project: str, state: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / f"{project}.yaml").write_text(yaml.dump(state, default_flow_style=False))


def detect_stack(stack_str: str) -> str:
    """Return primary stack identifier from a freeform stack description."""
    s = stack_str.lower()
    if "django" in s:
        return "django"
    if "flask" in s:
        return "flask"
    return "python"


def next_dev_port(project: str) -> int:
    state = load_state(project)
    existing = [e["port"] for e in state.get("dev_envs", [])]
    port = DEV_PORT_START
    while port in existing:
        port += 1
    return port


def run_ssh(cmd: str, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command on Carlos via SSH."""
    key = CARLOS_SSH_KEY
    ssh = ["ssh", "-i", key, "-o", "StrictHostKeyChecking=no",
           f"{CARLOS_USER}@{CARLOS_HOST}", cmd]
    if capture:
        return subprocess.run(ssh, capture_output=True, text=True)
    return subprocess.run(ssh)


def build_and_push_image(project_dir: Path, tag: str) -> None:
    """Build Docker image and copy to Carlos via SSH."""
    click.echo(f"  Building image {tag}...")
    subprocess.run(["docker", "build", "-t", tag, str(project_dir)], check=True)
    click.echo(f"  Saving and transferring image to Carlos...")
    save = subprocess.Popen(["docker", "save", tag], stdout=subprocess.PIPE)
    load_cmd = f"docker load"
    load = subprocess.run(
        ["ssh", "-i", CARLOS_SSH_KEY, "-o", "StrictHostKeyChecking=no",
         f"{CARLOS_USER}@{CARLOS_HOST}", load_cmd],
        stdin=save.stdout
    )
    save.wait()
    if load.returncode != 0:
        raise click.ClickException("Failed to load image on Carlos")


def flag_env_vars(flags: dict) -> str:
    """Convert feature flags dict to Docker -e arguments string."""
    return " ".join(
        f"-e FEATURE_{k.upper()}={'true' if v else 'false'}"
        for k, v in flags.items()
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """ci_cd — TBD/TDD/BDD project manager with feature flag deployment."""


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("name")
@click.option("--stack", default="python", help="Tech stack (e.g. 'django python sqlite')")
@click.option("--description", default="", help="Project description")
@click.option("--flag", "flags", multiple=True, help="Initial feature flags (repeatable)")
@click.option("--poetry", "use_poetry", is_flag=True, default=False,
              help="Use Poetry for dependency management instead of pip+requirements.txt")
def init(name: str, stack: str, description: str, flags: tuple, use_poetry: bool) -> None:
    """Initialize a new project with git, venv, LSP, hooks, and Docker setup."""
    project_dir = PROJECTS_ROOT / name
    if project_dir.exists():
        raise click.ClickException(f"{project_dir} already exists")

    # auto-detect poetry from stack string
    if "poetry" in stack.lower():
        use_poetry = True

    primary_stack = detect_stack(stack)
    today = date.today().isoformat()
    ctx = dict(name=name, stack=stack, primary_stack=primary_stack,
               description=description, today=today, use_poetry=use_poetry,
               flags={f: False for f in flags})

    click.echo(f"Initializing {name} ({primary_stack}) at {project_dir}")

    project_dir.mkdir(parents=True)

    # --- Render common files ---
    _write(project_dir / "README.md", render("common/README.md.j2", **ctx))
    _write(project_dir / "CLAUDE.md", render("common/CLAUDE.md.j2", **ctx))
    _write(project_dir / "AGENTS.md", render("common/AGENTS.md.j2", **ctx))
    _write(project_dir / ".gitignore", render("common/.gitignore.j2", **ctx))
    _write(project_dir / "feature_flags.yaml",
           render("common/feature_flags.yaml.j2", **ctx))
    compose_tpl = "common/docker-compose.poetry.yml.j2" if use_poetry else "common/docker-compose.yml.j2"
    _write(project_dir / "docker-compose.yml", render(compose_tpl, **ctx))
    _write(project_dir / "Makefile", render("common/Makefile.j2", **ctx))

    # --- Stack-specific files ---
    if primary_stack == "django":
        _init_django(project_dir, ctx)
    elif primary_stack == "flask":
        _init_flask(project_dir, ctx)
    else:
        _init_python(project_dir, ctx)

    # --- Terraform ---
    tf_dir = project_dir / "terraform"
    tf_dir.mkdir()
    _write(tf_dir / "main.tf", render("terraform/main.tf.j2", **ctx))
    _write(tf_dir / "variables.tf", render("terraform/variables.tf.j2", **ctx))
    _write(tf_dir / "outputs.tf", render("terraform/outputs.tf.j2", **ctx))
    _write(tf_dir / "dev.tfvars", render("terraform/dev.tfvars.j2", **ctx))
    _write(tf_dir / "prod.tfvars", render("terraform/prod.tfvars.j2", **ctx))

    # --- Git init + hooks ---
    subprocess.run(["git", "init", "-b", "main"], cwd=project_dir, check=True)
    subprocess.run(["git", "config", "user.name", "dev"], cwd=project_dir, check=True)
    subprocess.run(["git", "config", "user.email", "dev@albert.local"], cwd=project_dir, check=True)
    _install_hooks(project_dir, primary_stack)

    # --- venv / deps ---
    if use_poetry:
        click.echo("  Installing deps with Poetry...")
        poetry_bin = _find_poetry()
        # Keep venv inside the project for reproducibility
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

    # --- Lint-fix + format before commit so pre-commit hook passes ---
    subprocess.run([ruff_bin, "check", "--fix", "--quiet", "."], cwd=project_dir, capture_output=True)
    subprocess.run([ruff_bin, "format", "."], cwd=project_dir, capture_output=True)

    # --- Initial commit ---
    subprocess.run(["git", "add", "-A"], cwd=project_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore: bootstrap {name} ({primary_stack})"],
        cwd=project_dir, check=True
    )

    # --- Save state ---
    state = {
        "name": name, "stack": primary_stack, "description": description,
        "project_dir": str(project_dir), "created": today,
        "feature_flags": {f: {"description": f, "created": today} for f in flags},
        "dev_envs": [],
        "prod": {"port": None, "flags": {f: False for f in flags},
                 "container": f"{name.lower()}-prod", "deployed": False},
    }
    save_state(name, state)

    click.echo(f"\n✓ {name} ready at {project_dir}")
    click.echo(f"  Stack:  {primary_stack}")
    click.echo(f"  Deps:   {'Poetry (pyproject.toml)' if use_poetry else 'pip (requirements.txt)'}")
    click.echo(f"  Flags:  {', '.join(flags) if flags else 'none'}")
    click.echo(f"  venv:   source .venv/bin/activate")
    click.echo(f"\nNext steps:")
    click.echo(f"  ci_cd feature start {name} <flag>")
    click.echo(f"  ci_cd feature activate-dev {name} <flag>")


def _find_poetry() -> str:
    """Locate the poetry binary."""
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


def _init_python(project_dir: Path, ctx: dict) -> None:
    _write(project_dir / "main.py", render("python/main.py.j2", **ctx))
    _write(project_dir / "requirements.txt", render("python/requirements.txt.j2", **ctx))
    _write(project_dir / "Dockerfile", render("python/Dockerfile.j2", **ctx))
    _write(project_dir / "tests" / "test_main.py", render("python/test_main.py.j2", **ctx))


def _init_django(project_dir: Path, ctx: dict) -> None:
    name = ctx["name"]
    app = name.lower().replace("-", "_")
    use_poetry = ctx.get("use_poetry", False)
    ctx = {**ctx, "app": app}

    if use_poetry:
        _write(project_dir / "pyproject.toml", render("common/pyproject.toml.j2", **ctx))
        _write(project_dir / "Dockerfile", render("django/Dockerfile.poetry.j2", **ctx))
    else:
        _write(project_dir / "requirements.txt", render("django/requirements.txt.j2", **ctx))
        _write(project_dir / "Dockerfile", render("django/Dockerfile.j2", **ctx))
    _write(project_dir / "manage.py", render("django/manage.py.j2", **ctx))
    _write(project_dir / app / "__init__.py", "")
    _write(project_dir / app / "settings.py", render("django/settings.py.j2", **ctx))
    _write(project_dir / app / "urls.py", render("django/urls.py.j2", **ctx))
    _write(project_dir / app / "wsgi.py", render("django/wsgi.py.j2", **ctx))
    _write(project_dir / app / "asgi.py", render("django/asgi.py.j2", **ctx))
    _write(project_dir / app / "views.py", render("django/views.py.j2", **ctx))
    _write(project_dir / app / "flags.py", render("django/flags.py.j2", **ctx))
    _write(project_dir / "templates" / "index.html", render("django/index.html.j2", **ctx))
    _write(project_dir / "tests" / "__init__.py", "")
    _write(project_dir / "tests" / "test_views.py", render("django/test_views.py.j2", **ctx))
    _write(project_dir / "tests" / "features" / "flags.feature",
           render("django/flags.feature.j2", **ctx))
    # pyproject.toml already contains [tool.pytest.ini_options] for Poetry projects
    if not use_poetry:
        _write(project_dir / "pytest.ini", render("django/pytest.ini.j2", **ctx))


def _init_flask(project_dir: Path, ctx: dict) -> None:
    _write(project_dir / "app.py", render("flask/app.py.j2", **ctx))
    _write(project_dir / "requirements.txt", render("flask/requirements.txt.j2", **ctx))
    _write(project_dir / "Dockerfile", render("flask/Dockerfile.j2", **ctx))
    _write(project_dir / "tests" / "test_app.py", render("flask/test_app.py.j2", **ctx))


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
    """Deploy to environments."""


@deploy.command("prod")
@click.argument("project")
@click.argument("flag")
def deploy_prod(project: str, flag: str) -> None:
    """Deploy to production with <flag> OFF (dark launch)."""
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
    state = _require_state(project)
    _require_flag(state, flag)
    click.echo(f"Rolling back '{flag}' in production (flag OFF)...")
    state["prod"]["flags"][flag] = False
    save_state(project, state)
    _redeploy_prod(project, state)
    click.echo(f"✓ Feature '{flag}' deactivated in production")


# ---------------------------------------------------------------------------
# status
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
            url = f"http://{CARLOS_TAILSCALE}:{env['port']}"
            click.echo(f"  {env['id']}  {url}  deployed={env.get('deployed', False)}")

    prod = state.get("prod", {})
    if prod.get("deployed"):
        url = f"http://{CARLOS_TAILSCALE}:{prod['port']}"
        click.echo(f"\nProduction: {url}")
    else:
        click.echo("\nProduction: not deployed")


@cli.command("ls")
def list_projects() -> None:
    """List all managed projects."""
    STATE_DIR.mkdir(exist_ok=True)
    projects = sorted(STATE_DIR.glob("*.yaml"))
    if not projects:
        click.echo("No projects yet. Run: ci_cd init <name>")
        return
    for p in projects:
        state = yaml.safe_load(p.read_text()) or {}
        click.echo(f"  {state.get('name', p.stem):20s}  {state.get('stack', '?'):10s}  {state.get('description', '')[:50]}")


# ---------------------------------------------------------------------------
# Internal deploy helpers
# ---------------------------------------------------------------------------

def _deploy_dev(project: str, state: dict, flag: str, enabled: bool) -> None:
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
        click.echo(f"  Warning: deploy to Carlos failed ({e}). State saved locally.")
        deployed = False

    state.setdefault("dev_envs", []).append({
        "id": env_id, "port": port, "flags": flags,
        "container": container, "tag": tag, "deployed": deployed,
    })
    save_state(project, state)

    url = f"http://{CARLOS_TAILSCALE}:{port}"
    status_str = "live" if deployed else "FAILED (check Carlos)"
    click.echo(f"✓ {env_id} — {url} — {status_str}")


def _deploy_production(project: str, state: dict, flag_override: dict = None) -> None:
    project_dir = Path(state["project_dir"])
    flags = {**state.get("prod", {}).get("flags", {}), **(flag_override or {})}

    # Use a well-known prod port or allocate one
    port = state.get("prod", {}).get("port") or (DEV_PORT_START - 100)
    container = f"{project.lower()}-prod"
    tag = f"{project.lower()}:prod-{date.today().isoformat()}"

    try:
        build_and_push_image(project_dir, tag)
        env_args = flag_env_vars(flags)
        cmd = (f"docker stop {container} 2>/dev/null; docker rm {container} 2>/dev/null; "
               f"docker run -d --name {container} -p {port}:8000 "
               f"-e APP_ENV=prod {env_args} {tag}")
        result = run_ssh(cmd)
        deployed = result.returncode == 0
    except Exception as e:
        click.echo(f"  Warning: deploy to Carlos failed ({e}). State saved locally.")
        deployed = False

    state["prod"].update({"port": port, "flags": flags, "container": container,
                          "tag": tag, "deployed": deployed})
    save_state(project, state)

    url = f"http://{CARLOS_TAILSCALE}:{port}"
    status_str = "live" if deployed else "FAILED (check Carlos)"
    click.echo(f"✓ prod — {url} — {status_str}")


def _redeploy_prod(project: str, state: dict) -> None:
    _deploy_production(project, state)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _require_state(project: str) -> dict:
    state = load_state(project)
    if not state:
        raise click.ClickException(
            f"Project '{project}' not found. Run: ci_cd init {project}")
    return state


def _require_flag(state: dict, flag: str) -> None:
    if flag not in state.get("feature_flags", {}):
        raise click.ClickException(
            f"Flag '{flag}' not found. Run: ci_cd feature start {state['name']} {flag}")


def _git_commit(project_dir: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=project_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=project_dir, capture_output=True)


if __name__ == "__main__":
    cli()

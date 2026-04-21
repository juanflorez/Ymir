#!/usr/bin/env python3
"""Ymir MCP Server — exposes ymir deploy/flag operations to OpenHands agents."""

import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

YMIR_DIR = Path(__file__).parent
YMIR_PY = YMIR_DIR / "ymir.py"

mcp = FastMCP("ymir", host="0.0.0.0", port=8766)


def _run(*args: str, timeout: int = 120) -> str:
    """Run a ymir command and return combined stdout+stderr."""
    cmd = [sys.executable, str(YMIR_PY)] + list(args)
    result = subprocess.run(
        cmd,
        cwd=str(YMIR_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = result.stdout + (f"\nSTDERR: {result.stderr}" if result.stderr.strip() else "")
    return out.strip() or f"(exit {result.returncode}, no output)"


# ─── project info ────────────────────────────────────────────────────────────

@mcp.tool()
def ymir_status(project: str) -> str:
    """Get the deployment status and feature flag states for a project."""
    return _run("status", project)


@mcp.tool()
def ymir_ls() -> str:
    """List all projects managed by ymir."""
    return _run("ls")


# ─── deploy ──────────────────────────────────────────────────────────────────

@mcp.tool()
def ymir_deploy_dev(project: str) -> str:
    """Build and deploy the project to the dev environment on the deploy server.
    This is how you run the app — do this after making code changes to see them live."""
    return _run("deploy", "dev", project, timeout=180)


@mcp.tool()
def ymir_deploy_prod(project: str) -> str:
    """Dark-launch the project to production (feature flags stay OFF).
    Run this to ship code to prod before enabling it for users."""
    return _run("deploy", "prod", project, timeout=180)


# ─── feature flags ───────────────────────────────────────────────────────────

@mcp.tool()
def ymir_feature_start(project: str, flag: str) -> str:
    """Create a new feature flag in the project's feature_flags.yaml."""
    return _run("feature", "start", project, flag)


@mcp.tool()
def ymir_feature_activate_dev(project: str, flag: str) -> str:
    """Deploy dev with the specified feature flag turned ON."""
    return _run("feature", "activate-dev", project, flag, timeout=180)


@mcp.tool()
def ymir_feature_deactivate_dev(project: str, flag: str) -> str:
    """Deploy dev with the specified feature flag turned OFF."""
    return _run("feature", "deactivate-dev", project, flag, timeout=180)


@mcp.tool()
def ymir_release(project: str, flag: str) -> str:
    """Release a feature to production by turning the flag ON in prod.
    Only call this once the feature is tested and ready for users."""
    return _run("release", project, flag)


@mcp.tool()
def ymir_deactivate_prod(project: str, flag: str) -> str:
    """Rollback: turn a feature flag OFF in production."""
    return _run("deactivate-prod", project, flag)


@mcp.tool()
def ymir_feature_remove(project: str, flag: str) -> str:
    """Promote a feature to permanent — removes the flag guard from feature_flags.yaml.
    Only valid when the flag is ON in prod (i.e. the feature works and is released)."""
    return _run("feature", "remove", project, flag)


if __name__ == "__main__":
    mcp.run(transport="sse")

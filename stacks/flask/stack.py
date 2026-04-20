"""Flask stack module for Ymir."""

from pathlib import Path

NAME = "flask"
KEYWORDS = ["flask"]


def init(project_dir: Path, ctx: dict, write_fn, render_fn) -> None:
    """Scaffold a Flask project into project_dir."""
    write_fn(project_dir / "app.py", render_fn("app.py.j2", stack=NAME, **ctx))
    write_fn(project_dir / "requirements.txt", render_fn("requirements.txt.j2", stack=NAME, **ctx))
    write_fn(project_dir / "Dockerfile", render_fn("Dockerfile.j2", stack=NAME, **ctx))
    write_fn(project_dir / "tests" / "test_app.py", render_fn("test_app.py.j2", stack=NAME, **ctx))

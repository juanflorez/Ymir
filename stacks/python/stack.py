"""Plain Python stack module for Ymir."""

from pathlib import Path

NAME = "python"
KEYWORDS = ["python"]


def init(project_dir: Path, ctx: dict, write_fn, render_fn) -> None:
    """Scaffold a plain Python project into project_dir."""
    write_fn(project_dir / "main.py", render_fn("main.py.j2", stack=NAME, **ctx))
    write_fn(project_dir / "requirements.txt", render_fn("requirements.txt.j2", stack=NAME, **ctx))
    write_fn(project_dir / "Dockerfile", render_fn("Dockerfile.j2", stack=NAME, **ctx))
    write_fn(project_dir / "tests" / "test_main.py", render_fn("test_main.py.j2", stack=NAME, **ctx))

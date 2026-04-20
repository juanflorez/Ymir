"""Django stack module for Ymir."""

from pathlib import Path

NAME = "django"
KEYWORDS = ["django"]


def init(project_dir: Path, ctx: dict, write_fn, render_fn) -> None:
    """Scaffold a Django project into project_dir."""
    name = ctx["name"]
    app = name.lower().replace("-", "_")
    use_poetry = ctx.get("use_poetry", False)
    ctx = {**ctx, "app": app}

    if use_poetry:
        write_fn(project_dir / "pyproject.toml", render_fn("common/pyproject.toml.j2", **ctx))
        write_fn(project_dir / "Dockerfile", render_fn("Dockerfile.poetry.j2", stack=NAME, **ctx))
    else:
        write_fn(project_dir / "requirements.txt", render_fn("requirements.txt.j2", stack=NAME, **ctx))
        write_fn(project_dir / "Dockerfile", render_fn("Dockerfile.j2", stack=NAME, **ctx))

    write_fn(project_dir / "manage.py", render_fn("manage.py.j2", stack=NAME, **ctx))
    write_fn(project_dir / app / "__init__.py", "")
    write_fn(project_dir / app / "settings.py", render_fn("settings.py.j2", stack=NAME, **ctx))
    write_fn(project_dir / app / "urls.py", render_fn("urls.py.j2", stack=NAME, **ctx))
    write_fn(project_dir / app / "wsgi.py", render_fn("wsgi.py.j2", stack=NAME, **ctx))
    write_fn(project_dir / app / "asgi.py", render_fn("asgi.py.j2", stack=NAME, **ctx))
    write_fn(project_dir / app / "views.py", render_fn("views.py.j2", stack=NAME, **ctx))
    write_fn(project_dir / app / "flags.py", render_fn("flags.py.j2", stack=NAME, **ctx))
    write_fn(project_dir / "templates" / "index.html", render_fn("index.html.j2", stack=NAME, **ctx))
    write_fn(project_dir / "tests" / "__init__.py", "")
    write_fn(project_dir / "tests" / "test_views.py", render_fn("test_views.py.j2", stack=NAME, **ctx))
    write_fn(project_dir / "tests" / "features" / "flags.feature",
             render_fn("flags.feature.j2", stack=NAME, **ctx))
    if not use_poetry:
        write_fn(project_dir / "pytest.ini", render_fn("pytest.ini.j2", stack=NAME, **ctx))

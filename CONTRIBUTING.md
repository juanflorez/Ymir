# Contributing to Ymir

## Adding a New Stack

A "stack" is a self-contained directory under `stacks/` that teaches Ymir how to scaffold a new type of project.

### 1. Create the directory

```
stacks/
  mystack/
    stack.py         ← required
    templates/       ← required
      Dockerfile.j2
      ...
```

### 2. Write `stack.py`

Your `stack.py` must expose three module-level names:

```python
NAME = "mystack"          # must match the directory name
KEYWORDS = ["mystack"]    # trigger words in --stack "..." that activate this stack

def init(project_dir, ctx, write_fn, render_fn):
    """Scaffold files into project_dir."""
    write_fn(project_dir / "Dockerfile", render_fn("Dockerfile.j2", stack=NAME, **ctx))
    # ... write more files
```

**`ctx`** is a dict with at least:

| Key | Value |
|-----|-------|
| `name` | Project name (e.g. `"MyApp"`) |
| `app` | Snake-case app name (e.g. `"myapp"`) |
| `description` | Free-text description |
| `today` | ISO date string |
| `flags` | Dict of `{flag_name: False}` |
| `use_poetry` | Boolean |
| `primary_stack` | Stack name string |

**`write_fn(path, content)`** — write a file, creating parent dirs.

**`render_fn(template_name, stack=None, **ctx)`** — render a Jinja2 template.
- If `stack` is provided, looks in `stacks/<stack>/templates/<template_name>` first.
- Falls back to `templates/<template_name>` (common templates).

### 3. Templates

Jinja2 templates live in `stacks/mystack/templates/`. The `ctx` dict is available as template variables.

Common templates (Makefile, .gitignore, CLAUDE.md, AGENTS.md, etc.) live in `templates/common/` and are rendered by the core — your stack doesn't need to duplicate them.

### 4. Test it

```bash
python ymir.py init TestProject --stack mystack --description "Testing my new stack"
ls ../projects/TestProject/
```

### Stack lifecycle

Ymir discovers stacks at startup — no registration needed. Drop your directory in `stacks/` and it works.

## Reporting Bugs

Open an issue at https://github.com/juanflorez/Ymir/issues

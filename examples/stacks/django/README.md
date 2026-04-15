# Django example

Minimal Django 5 fixture.

## Try it

```bash
cp -r examples/stacks/django /tmp/django-demo
cd /tmp/django-demo
git init -q
python -m venv .venv   # Context OS will ignore .venv/
bash /path/to/context-os/setup.sh --measure
bash /path/to/context-os/setup.sh
```

## What happens

1. Stack detection sees `requirements.txt` + `manage.py` → marks stack as `python, django`.
2. `.claudeignore` blocks `.venv/`, `venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.mypy_cache/`, `.tox/`, `.coverage`, `htmlcov/`, `staticfiles/`, `media/`, `migrations/*.py` (optional).
3. `CLAUDE.md` repo map shows the Django app layout.
4. Pytest output passes through hook-based compression when the binary is installed.

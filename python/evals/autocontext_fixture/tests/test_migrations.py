"""Migration tests."""
from src.db.migrations import run_migrations, MIGRATIONS


def test_migrations_list_is_sane():
    assert len(MIGRATIONS) >= 3
    assert any("users" in m for m in MIGRATIONS)


def test_run_migrations_returns_count():
    assert run_migrations() == len(MIGRATIONS)

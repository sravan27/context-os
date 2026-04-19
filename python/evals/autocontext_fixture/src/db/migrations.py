"""run_migrations — schema bootstrap."""
from src.config.database import get_db_connection


MIGRATIONS = [
    "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT)",
    "CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER, expires_at INTEGER)",
    "CREATE TABLE IF NOT EXISTS tokens (value TEXT PRIMARY KEY, purpose TEXT, user_id INTEGER)",
]


def run_migrations():
    conn = get_db_connection()
    # Stub — would execute MIGRATIONS against conn.
    return len(MIGRATIONS)

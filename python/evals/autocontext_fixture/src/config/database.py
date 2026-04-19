"""DATABASE_URL + get_db_connection."""
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")


def get_db_connection():
    # Stub — real impl would open a connection pool here.
    return type("Conn", (), {"url": DATABASE_URL, "closed": False})()


def close_connection(conn):
    conn.closed = True

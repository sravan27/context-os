"""Settings class + load_config."""
import os


class Settings:
    def __init__(self):
        self.session_ttl = int(os.environ.get("SESSION_TTL", "3600"))
        self.debug = os.environ.get("DEBUG", "0") == "1"
        self.port = int(os.environ.get("PORT", "8080"))


def load_config(path: str = ".env"):
    cfg = {}
    try:
        with open(path) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    cfg[k] = v
    except FileNotFoundError:
        pass
    return cfg

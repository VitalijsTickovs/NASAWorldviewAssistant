"""
Load environment variables from a .env file and expose them via os.environ.

Usage:
    from app.config import load_env
    load_env()

This ensures that .env variables are available early in app startup.
"""

from pathlib import Path
from dotenv import load_dotenv

def load_env(env_path: str | None = None) -> None:
    """
    Load variables from a .env file into the environment.
    If no path is given, it looks for `.env` in sensible defaults for
    both editable installs (repo root) and packaged installs (cwd).
    """

    candidates: list[Path]
    if env_path is not None:
        candidates = [Path(env_path)]
    else:
        repo_root = Path(__file__).resolve().parent.parent.parent
        candidates = [
            Path.cwd() / ".env",  # running from an installed package (docker, prod)
            repo_root / ".env",    # running from repo root (local dev)
        ]

    for candidate in candidates:
        if candidate.exists():
            load_dotenv(dotenv_path=candidate)
            print(f"✅ Loaded environment variables from: {candidate}")
            return

    # No file found, default to system environment vars
    missing_path = candidates[0] if candidates else Path(env_path)
    print(f"⚠️ No .env file found at: {missing_path} — using system env vars only.")

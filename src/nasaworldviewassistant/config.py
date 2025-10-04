"""
Load environment variables from a .env file and expose them via os.environ.

Usage:
    from app.config import load_env
    load_env()

This ensures that .env variables are available early in app startup.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

def load_env(env_path: str | None = None) -> None:
    """
    Load variables from a .env file into the environment.
    If no path is given, it looks for `.env` in the project root.
    """
    # Default: repo_root/.env
    if env_path is None:
        env_path = Path(__file__).resolve().parents[2] / ".env"

    env_path = Path(env_path)
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        print(f"✅ Loaded environment variables from: {env_path}")
    else:
        print(f"⚠️ No .env file found at: {env_path} — using system env vars only.")

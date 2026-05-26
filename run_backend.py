from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"


def load_dotenv() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the A-share watchlist backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true", help="Disable uvicorn auto-reload.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv()
    root = str(ROOT_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.chdir(ROOT_DIR)

    reload_enabled = not args.no_reload
    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        reload=reload_enabled,
        reload_dirs=[str(BACKEND_DIR)] if reload_enabled else None,
        app_dir=root,
    )


if __name__ == "__main__":
    main()

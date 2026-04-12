#!/usr/bin/env python3
"""
Standalone setup script for local Replica AI instances.

Usage:
    python scripts/local_setup.py \
        --cloud-url http://your-cloud.example.com:8000 \
        --instance-token <token-from-registration>

This script:
  1. Verifies the cloud API is reachable
  2. Checks that Ollama is installed locally
  3. Pulls the default model (mistral:7b-instruct)
  4. Writes a local apps/ai/.env from cloud config
  5. Starts a heartbeat thread (every 60s)
  6. Launches the local AI service via uvicorn
"""

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install it with: pip install httpx")
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up a local Replica AI instance")
    parser.add_argument(
        "--cloud-url",
        required=True,
        help="URL of the cloud API (e.g. http://your-cloud.example.com:8000)",
    )
    parser.add_argument(
        "--instance-token",
        required=True,
        help="Auth token received from instance registration",
    )
    parser.add_argument(
        "--model",
        default="mistral:7b-instruct",
        help="Ollama model to pull (default: mistral:7b-instruct)",
    )
    parser.add_argument(
        "--ai-port",
        type=int,
        default=8100,
        help="Port for the local AI service (default: 8100)",
    )
    return parser.parse_args()


def verify_cloud(cloud_url: str) -> None:
    print(f"[1/5] Verifying cloud API at {cloud_url}...")
    try:
        resp = httpx.get(f"{cloud_url}/health", timeout=10)
        resp.raise_for_status()
        print("      Cloud API is reachable.")
    except Exception as e:
        print(f"      ERROR: Cannot reach cloud API: {e}")
        sys.exit(1)


def check_ollama() -> None:
    print("[2/5] Checking Ollama installation...")
    if not shutil.which("ollama"):
        print("      ERROR: Ollama not found. Install from https://ollama.ai")
        sys.exit(1)
    result = subprocess.run(
        ["ollama", "--version"],
        capture_output=True,
        text=True,
    )
    version = result.stdout.strip() or result.stderr.strip()
    print(f"      Ollama found: {version}")


def pull_model(model_name: str) -> None:
    print(f"[3/5] Pulling model '{model_name}' (this may take a while)...")
    result = subprocess.run(
        ["ollama", "pull", model_name],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"      ERROR: Failed to pull model '{model_name}'")
        sys.exit(1)
    print(f"      Model '{model_name}' is ready.")


def write_env(ai_port: int) -> None:
    print("[4/5] Writing local apps/ai/.env...")
    # Find the project root (parent of scripts/)
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / "apps" / "ai" / ".env"

    env_vars = {
        "HOST": "0.0.0.0",
        "PORT": str(ai_port),
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "6333",
        "CORS_ORIGINS": '["http://localhost:3000","http://localhost:8000"]',
    }

    # Preserve existing vars, only set if not already present
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                existing[key.strip()] = val.strip()

    merged = {**env_vars, **existing}
    env_content = "\n".join(f"{k}={v}" for k, v in sorted(merged.items())) + "\n"
    env_path.write_text(env_content)
    print(f"      Written to {env_path}")


def start_heartbeat(cloud_url: str, token: str) -> threading.Thread:
    """Start a daemon thread that sends heartbeats every 60 seconds."""

    # Extract instance_id from the JWT (decode without verification, just to read claims)
    import base64
    import json

    parts = token.split(".")
    if len(parts) != 3:
        print("      WARNING: Could not parse instance_id from token, skipping heartbeat")
        return threading.Thread()

    # Decode JWT payload (part 1)
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    instance_id = payload.get("instance_id")

    if not instance_id:
        print("      WARNING: No instance_id in token, skipping heartbeat")
        return threading.Thread()

    def _heartbeat_loop() -> None:
        while True:
            time.sleep(60)
            try:
                httpx.post(
                    f"{cloud_url}/api/instances/{instance_id}/heartbeat",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
            except Exception:
                pass  # Best-effort

    thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    thread.start()
    return thread


def main() -> None:
    args = parse_args()

    verify_cloud(args.cloud_url)
    check_ollama()
    pull_model(args.model)
    write_env(args.ai_port)

    print("[5/5] Starting local AI service...")
    start_heartbeat(args.cloud_url, args.instance_token)

    print()
    print("=" * 50)
    print("  Local Replica AI Instance")
    print(f"  AI Service: http://localhost:{args.ai_port}")
    print(f"  Cloud API:  {args.cloud_url}")
    print(f"  Model:      {args.model}")
    print("  Heartbeat:  every 60s")
    print("=" * 50)
    print()

    os.execvp(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(args.ai_port),
            "--reload",
        ],
    )


if __name__ == "__main__":
    main()

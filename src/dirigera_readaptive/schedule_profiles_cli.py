from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml

from .client import HttpDirigeraClient
from .config import load_dirigera_token
from .schedule_cli import load_dotenv
from .schedule_profiles import load_schedule_profiles_config, update_configured_profiles


async def run(args: argparse.Namespace) -> None:
    load_dotenv(args.env)
    raw = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    dirigera = raw.get("dirigera") or {}
    host = str(dirigera["host"])
    token = load_dirigera_token(dirigera)

    client = HttpDirigeraClient(host=host, token=token)
    results = await update_configured_profiles(
        client,
        load_schedule_profiles_config(args.config),
    )
    for name, changed in results.items():
        if changed:
            print(f"Updated adaptive profile schedule: {name}")
        else:
            print(f"Adaptive profile schedule already matched: {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--env", default=".env", type=Path)
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()

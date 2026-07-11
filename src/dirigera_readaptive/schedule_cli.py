from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from .client import HttpDirigeraClient
from .schedule_update import load_schedule_file, update_profile_if_changed


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


async def apply_schedule(args: argparse.Namespace) -> None:
    load_dotenv(args.env)
    token = load_token(args.token_env, args.token_file)

    schedule = load_schedule_file(args.schedule)
    client = HttpDirigeraClient(host=args.host, token=token)

    if args.dry_run:
        print(f"Dry run: would apply {len(schedule)} entries to {args.profile_id}.")
        return

    changed = await update_profile_if_changed(client, args.profile_id, schedule)
    if changed:
        print(f"Updated adaptive profile {args.profile_id}.")
    else:
        print(f"Adaptive profile {args.profile_id} already matches desired schedule.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--schedule", required=True, type=Path)
    parser.add_argument("--env", default=".env", type=Path)
    parser.add_argument("--token-env", default="DIRIGERA_TOKEN")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asyncio.run(apply_schedule(args))


def load_token(token_env: str, token_file: Path | None = None) -> str:
    token = os.environ.get(token_env)
    if token:
        return token
    if token_file:
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            return token
        raise ValueError(f"Token file {token_file} is empty.")
    raise ValueError(
        f"Environment variable {token_env} must contain the DIRIGERA token, "
        "or --token-file must point to a token file."
    )


if __name__ == "__main__":
    main()

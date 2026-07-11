from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .client import HttpDirigeraClient
from .config import load_config
from .events import device_state_updates
from .recovery import RecoveryDaemon


async def run_daemon(config_path: Path) -> None:
    config = load_config(config_path)
    client = HttpDirigeraClient(
        host=config.dirigera.host,
        token=config.dirigera.token,
    )
    daemon = RecoveryDaemon(
        client=client,
        lights=config.lights,
        cooldown_seconds=config.activation_cooldown_seconds,
        recover_on_reconnect=config.recover_on_reconnect,
        recover_on_power_on=config.recover_on_power_on,
    )

    await daemon.poll_once()
    await asyncio.gather(
        _websocket_loop(client, daemon),
        _poll_loop(daemon, config.poll_interval_seconds),
    )


async def _websocket_loop(client: HttpDirigeraClient, daemon: RecoveryDaemon) -> None:
    while True:
        try:
            async for message in client.events():
                for device_id, state in device_state_updates(message):
                    await daemon.handle_device_state(
                        device_id,
                        is_reachable=state.get("is_reachable"),
                        is_on=state.get("is_on"),
                    )
        except Exception as error:
            print(f"WebSocket listener failed: {error}. Reconnecting in 5 seconds.")
            await asyncio.sleep(5)


async def _poll_loop(daemon: RecoveryDaemon, poll_interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(poll_interval_seconds)
        try:
            await daemon.poll_once()
        except Exception as error:
            print(f"Polling failed: {error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config.yaml",
        type=Path,
        help="Path to YAML configuration file.",
    )
    args = parser.parse_args()

    asyncio.run(run_daemon(args.config))


if __name__ == "__main__":
    main()

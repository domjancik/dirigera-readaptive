from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from .client import HttpDirigeraClient
from .config import load_config
from .events import device_state_updates
from .recovery import RecoveryDaemon


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


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

    await _seed_initial_state(client, daemon, config.watch_adaptive_on_lights)
    await asyncio.gather(
        _websocket_loop(client, daemon),
        _poll_loop(
            client,
            daemon,
            config.poll_interval_seconds,
            config.watch_adaptive_on_lights,
        ),
    )


async def _seed_initial_state(
    client: HttpDirigeraClient,
    daemon: RecoveryDaemon,
    watch_adaptive_on_lights: bool,
) -> None:
    try:
        if watch_adaptive_on_lights:
            await _poll_inventory(client, daemon)
        else:
            await daemon.poll_once()
    except Exception as error:
        print(f"Initial inventory failed: {error}. Continuing with retries.")


async def _websocket_loop(client: HttpDirigeraClient, daemon: RecoveryDaemon) -> None:
    while True:
        try:
            async for message in client.events():
                await _handle_websocket_message(message, daemon)
        except Exception as error:
            print(f"WebSocket listener failed: {error}. Reconnecting in 5 seconds.")
            await asyncio.sleep(5)


async def _handle_websocket_message(message: str, daemon: RecoveryDaemon) -> None:
    for device_id, state in device_state_updates(message):
        is_reachable = state.get("is_reachable")
        is_on = state.get("is_on")
        last_seen = state.get("last_seen")
        await daemon.handle_device_state(
            device_id,
            is_reachable=is_reachable if isinstance(is_reachable, bool) else None,
            is_on=is_on if isinstance(is_on, bool) else None,
            last_seen=last_seen if isinstance(last_seen, str) else None,
        )


async def _poll_inventory(client: HttpDirigeraClient, daemon: RecoveryDaemon) -> None:
    devices = await client.get_devices()
    daemon.sync_adaptive_lights(devices)
    for device in devices:
        device_id = device.get("id")
        if not isinstance(device_id, str):
            continue
        attributes = device.get("attributes") or {}
        await daemon.handle_device_state(
            device_id,
            is_reachable=device.get("isReachable"),
            is_on=attributes.get("isOn"),
            last_seen=device.get("lastSeen"),
        )


async def _poll_loop(
    client: HttpDirigeraClient,
    daemon: RecoveryDaemon,
    poll_interval_seconds: int,
    watch_adaptive_on_lights: bool,
) -> None:
    while True:
        await asyncio.sleep(poll_interval_seconds)
        try:
            if watch_adaptive_on_lights:
                await _poll_inventory(client, daemon)
            else:
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

    configure_logging()
    asyncio.run(run_daemon(args.config))


if __name__ == "__main__":
    main()

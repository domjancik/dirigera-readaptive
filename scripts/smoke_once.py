import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dirigera_readaptive.client import HttpDirigeraClient
from dirigera_readaptive.config import load_config
from dirigera_readaptive.recovery import RecoveryDaemon


def load_dotenv(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


async def main() -> None:
    load_dotenv(Path(".env"))
    config = load_config(Path("config.yaml"))
    client = HttpDirigeraClient(config.dirigera.host, config.dirigera.token)
    daemon = RecoveryDaemon(client, config.lights, config.activation_cooldown_seconds)
    await daemon.poll_once()
    device = await client.get_device(config.lights[0].id)
    print(
        {
            "id": device["id"],
            "isReachable": device["isReachable"],
            "isOn": device["attributes"]["isOn"],
            "adaptiveProfile": device.get("adaptiveProfile"),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())

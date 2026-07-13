import argparse
import asyncio
import json
import os
import re
import ssl
from datetime import datetime, timezone
from pathlib import Path

import websockets


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([^=]+)=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


class RotatingJsonlWriter:
    def __init__(
        self,
        label: str,
        rotate_bytes: int,
        max_total_bytes: int = 250 * 1024 * 1024,
        captures_dir: Path | None = None,
    ) -> None:
        self._label = re.sub(r"[^A-Za-z0-9_.-]", "-", label)
        self._rotate_bytes = rotate_bytes
        self._max_total_bytes = max_total_bytes
        self._captures_dir = captures_dir or Path("captures")
        self._captures_dir.mkdir(exist_ok=True)
        self._file = None
        self.path = self._new_path()

    def __enter__(self) -> "RotatingJsonlWriter":
        self._open()
        return self

    def __exit__(self, *args: object) -> None:
        if self._file:
            self._file.close()

    def write(self, payload: dict[str, object]) -> None:
        if self._file is None:
            self._open()
        assert self._file is not None
        self._file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._file.flush()
        if self._rotate_bytes > 0 and self._file.tell() >= self._rotate_bytes:
            self._file.close()
            self.path = self._new_path()
            self._open()

    def _new_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return self._captures_dir / f"{stamp}-{self._label}-events.jsonl"

    def _open(self) -> None:
        self._prune_old_captures()
        print(f"Recording raw events to {self.path}")
        self._file = self.path.open("a", encoding="utf-8")

    def _prune_old_captures(self) -> None:
        if self._max_total_bytes <= 0:
            return

        captures = sorted(
            self._captures_dir.glob("*-events.jsonl"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
        total_bytes = sum(path.stat().st_size for path in captures)
        while captures and total_bytes > self._max_total_bytes:
            oldest = captures.pop(0)
            total_bytes -= oldest.stat().st_size
            oldest.unlink()


async def capture(
    env_path: Path,
    label: str,
    seconds: int,
    rotate_mb: int,
    max_total_mb: int,
) -> Path:
    env = load_env(env_path)
    host = env["DIRIGERA_HOST"]
    token = env["DIRIGERA_TOKEN"]

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    uri = f"wss://{host}:8443/v1"
    headers = {"Authorization": f"Bearer {token}"}

    rotate_bytes = rotate_mb * 1024 * 1024
    started_at = asyncio.get_running_loop().time()
    deadline = started_at + seconds if seconds > 0 else None

    with RotatingJsonlWriter(
        label=label,
        rotate_bytes=rotate_bytes,
        max_total_bytes=max_total_mb * 1024 * 1024,
    ) as events:
        while deadline is None or asyncio.get_running_loop().time() < deadline:
            try:
                print(f"Connecting to {uri}")
                async with websockets.connect(
                    uri,
                    additional_headers=headers,
                    ssl=ssl_context,
                    ping_interval=30,
                    open_timeout=10,
                ) as websocket:
                    await _record_until_deadline(websocket, events, deadline)
            except asyncio.TimeoutError:
                break
            except Exception as error:
                events.write(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "kind": "logger_error",
                        "error": str(error),
                    }
                )
                print(f"WebSocket capture failed: {error}. Reconnecting in 5 seconds.")
                await asyncio.sleep(5)

    print(f"Last log file: {events.path}")
    return events.path


async def _record_until_deadline(
    websocket,
    events: RotatingJsonlWriter,
    deadline: float | None,
) -> None:
    while True:
        if deadline is None:
            message = await websocket.recv()
        else:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    return
                break

        events.write(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kind": "message",
                "message": message,
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--label", default="capture")
    parser.add_argument(
        "--seconds",
        type=int,
        default=30,
        help="Capture duration. Use 0 to run continuously.",
    )
    parser.add_argument(
        "--rotate-mb",
        type=int,
        default=25,
        help="Start a new JSONL file after this many MiB. Use 0 to disable rotation.",
    )
    parser.add_argument(
        "--max-total-mb",
        type=int,
        default=250,
        help="Retain at most this many MiB of completed JSONL captures. Use 0 to disable retention.",
    )
    args = parser.parse_args()

    asyncio.run(
        capture(
            Path(args.env),
            args.label,
            args.seconds,
            args.rotate_mb,
            args.max_total_mb,
        )
    )


if __name__ == "__main__":
    main()

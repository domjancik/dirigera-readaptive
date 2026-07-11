# DIRIGERA ReAdaptive

Small local recovery daemon for IKEA DIRIGERA native Adaptive lighting.

The daemon does **not** calculate or continuously enforce brightness or color
temperature. It only replays the native "enter Adaptive" operation that was
verified against the local hub:

```http
PATCH /v1/devices/<device-id>

[
  {
    "adaptiveProfile": {
      "id": "<profile-id>",
      "active": true
    }
  }
]
```

## Setup

Create a token:

```powershell
pwsh -ExecutionPolicy Bypass -File .\scripts\pair-dirigera.ps1 -HostAddress 192.168.1.249
```

Set the token in your shell:

```powershell
$env:DIRIGERA_TOKEN = "<token from .env>"
```

Copy `config.example.yaml` to `config.yaml` and adjust the configured lights.

Run the daemon:

```powershell
python -m dirigera_readaptive.cli --config config.yaml
```

## Behavior

- Tracks configured lights' `isReachable` state when `recover_on_reconnect` is
  enabled. This is enabled by default.
- On `isReachable: false -> true`, waits `reconnect_delay_ms`.
- Can optionally watch `isOn: false -> true` when `recover_on_power_on` is
  enabled. This is disabled by default.
- Re-reads the device.
- Skips the light if it is off.
- Activates native Adaptive once using the verified top-level
  `adaptiveProfile` patch.
- Applies a cooldown to avoid duplicate activation.
- Polls periodically as a fallback if a WebSocket event is missed.

## Capture Helpers

- `scripts/pair-dirigera.ps1`: local OAuth token pairing.
- `scripts/capture_dirigera_events.py`: raw WebSocket JSONL capture.
- `scripts/capture-dirigera-events.ps1`: earlier PowerShell capture attempt,
  retained for reference.

Run a continuous background event logger:

```powershell
pwsh -ExecutionPolicy Bypass -File .\scripts\start-event-logger.ps1 -Label continuous -RotateMb 25
```

Stop it:

```powershell
pwsh -ExecutionPolicy Bypass -File .\scripts\stop-event-logger.ps1
```

This is useful while living with the system normally. It can capture delayed
profile shifts, app/remote overrides, `isOn` transitions, reachability changes,
and whether the hub emits anything when a light reports Adaptive but holds stale
brightness. Logs are written under `captures/` and are gitignored.

## Adaptive Schedule Updates

The hub accepts adaptive profile updates at:

```http
PUT /v1/adaptive-profiles/<profile-id>
```

with the full profile body:

```json
{
  "id": "<profile-id>",
  "name": "Computed schedule",
  "adaptiveSchedule": [
    {
      "startTime": "20:00",
      "lightLevel": 81,
      "colorTemperature": 2000
    }
  ]
}
```

Apply a YAML schedule file:

```powershell
$env:PYTHONPATH = "src"
python -m dirigera_readaptive.schedule_cli `
  --host 192.168.1.249 `
  --profile-id 7bbebe49-41a3-48ea-8f5f-9e33a36dad87 `
  --schedule schedules\computed.example.yaml
```

The updater reads `/v1/home` first and skips the PUT if the profile already
matches the desired schedule. The Raspberry Pi timer uses
`dirigera-schedule-profiles` with `schedule_updates.profiles[]` from
`config.yaml`, so multiple generated profiles can be recomputed and applied in
one daily run.

## Seasonal Schedule Generator

The `dirigera-seasonal-schedule` command ports the old ZdraveSvetlo
Sunrise/Sunset patch into a DIRIGERA adaptive profile schedule. It calculates
local nautical sunrise, sunrise, solar noon, and sunset; then builds warm and
cool channels with the same sine tween segments used by the vvvv patch.

Generate a seasonal schedule:

```powershell
$env:PYTHONPATH = "src"
python -m dirigera_readaptive.seasonal_cli `
  --date 2024-06-08 `
  --latitude 50.1 `
  --longitude 14.5 `
  --timezone Europe/Prague `
  --output schedules\computed.generated.yaml `
  --extend-day-after-late-sunset
```

The `--extend-day-after-late-sunset` option moves the effective pre-sleep and
sleep points later, capped by `--latest-sleep-time`, when summer sunset would
otherwise collide with the fixed evening schedule. This keeps the generated
schedule useful across the year before applying it with `dirigera-schedule`.

Operationally, keep two generated schedules: the normal/full-peak variant for
the main adaptive profile, and a dimmed variant for lower-peak rooms by using a
lower `--max-light-level` plus lower morning/evening/pre-sleep levels.

The default generated profile now uses IKEA-like summer anchors: `10%` overnight,
`2700K` around two hours after sunrise, `4600K` near solar noon, roughly
`2450K` before sunset, `2200K` at pre-sleep, and `1000K` at sleep.

Raspberry Pi deployment notes are in `docs/raspberry-pi.md`.

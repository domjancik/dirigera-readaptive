# Raspberry Pi Setup

Target layout:

- App: `/opt/dirigera-readaptive`
- Token: `/etc/dirigera-readaptive/token`
- Runtime user: `piadmin`

## Seed Existing Token

From this Windows checkout:

```powershell
pwsh -ExecutionPolicy Bypass -File .\scripts\pi-seed-token.ps1 -PiHost 192.168.1.250 -PiUser piadmin
```

The script reads `DIRIGERA_TOKEN` from local `.env` and writes it to the Pi as a
`0600` token file. The token is streamed over SSH stdin, not placed on the SSH
command line. If the Pi gets a different lease, pass that IP or hostname as
`-PiHost`.

Configure the Pi's `/opt/dirigera-readaptive/config.yaml` to use the token file:

```yaml
dirigera:
  host: 192.168.1.249
  token_file: /etc/dirigera-readaptive/token

schedule_updates:
  latitude: 50.1
  longitude: 14.5
  timezone: Europe/Prague
  profiles:
    - name: computed-standard
      profile_name: ReAdaptive
      output: /opt/dirigera-readaptive/schedules/computed.yaml
      curve:
        extend_day_after_late_sunset: true
    - name: computed-dimmed
      profile_name: ReAdaptive Dimmed
      output: /opt/dirigera-readaptive/schedules/computed-dim.yaml
      curve:
        extend_day_after_late_sunset: true
        min_light_level: 4
        morning_light_level: 70
        max_light_level: 85
        evening_light_level: 47
        pre_sleep_light_level: 42
```

## Services

Install or update the app, dependencies, systemd units, and status scripts:

```powershell
pwsh -ExecutionPolicy Bypass -File .\scripts\pi-install-app.ps1 -PiHost 192.168.1.250 -PiUser piadmin
```

The installer clones or updates the public repo at `/opt/dirigera-readaptive`,
creates `/opt/dirigera-readaptive/.venv`, installs Python dependencies, copies
`config.rpi.example.yaml` to `config.yaml` if no config exists, installs the
systemd units, and enables the daemon service and schedule timer. If the token
file exists, it also starts the daemon, timer, and one immediate schedule update.

If installing units manually from `systemd/` to `/etc/systemd/system/`, run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dirigera-readaptive.service
sudo systemctl enable --now dirigera-computed-schedule.timer
```

The schedule timer runs `dirigera-schedule-profiles`, regenerates every profile
listed in `schedule_updates.profiles[]`, writes each YAML file, and applies each
hub profile only when its schedule or dated display name changed. If `profile_id`
is omitted, its first run creates a profile from `profile_name`; later runs find
and update that same named slot.

The timer runs at 03:10, 09:10, 15:10, and 21:10. Only the first update after a
date change normally writes to the hub; the additional runs retry after a short
hub or network outage. `Persistent=true` also runs a missed timer after the Pi
returns from a power outage.

## Storage Retention

The installer limits persistent journal logs to 100 MB, keeps at least 500 MB
of disk free, limits runtime journal logs to 50 MB, and retains journal entries
for at most 30 days. The recovery and schedule services do not create their own
growing log files.

The optional raw WebSocket capture utility is separate from the Pi services. It
rotates at 25 MiB and, by default, retains 250 MiB of completed JSONL captures.
Set `-MaxTotalMb 0` or `--max-total-mb 0` only for a deliberately temporary,
manually monitored capture.

## Power and Network Recovery

Both app units are enabled at boot. The recovery daemon reconnects its
WebSocket listener and continues polling when the hub or network is temporarily
unavailable. The schedule timer is persistent and has four daily opportunities
to apply the current date's profile.

The daemon intentionally does not force Adaptive mode for every light during
its startup inventory. That preserves a deliberate manual override made with a
remote or the app. Consequently, if the Pi is unavailable for the entire
offline-to-online transition of a light, that particular recovery event cannot
be reconstructed after boot. Use a stable power supply and, where that edge
case must be covered, put the Pi and hub on a small UPS.

`dirigera-status` reports `vcgencmd` temperature and throttle flags when the
firmware command is available. A nonzero `get_throttled` result is worth
investigating before relying on the Pi for unattended operation.

## Status Scripts

The app installer copies the helper scripts into `/home/piadmin/bin`. To install
or refresh only those scripts:

```powershell
pwsh -ExecutionPolicy Bypass -File .\scripts\pi-install-status-scripts.ps1 -PiHost 192.168.1.250 -PiUser piadmin
```

They are installed to `/home/piadmin/bin`:

- `dirigera-status`: overview of service states, timer, recent logs, generated
  schedule files, and configured schedule profiles.
- `dirigera-logs`: recent or following journal logs for the recovery daemon and
  schedule updater.
- `dirigera-run-schedule-update`: manually starts the schedule updater service
  and prints its status/log output.

Examples:

```bash
~/bin/dirigera-status
~/bin/dirigera-logs -f
~/bin/dirigera-run-schedule-update
```

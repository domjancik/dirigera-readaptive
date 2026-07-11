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
      profile_id: 7bbebe49-41a3-48ea-8f5f-9e33a36dad87
      output: /opt/dirigera-readaptive/schedules/computed.yaml
      curve:
        extend_day_after_late_sunset: true
    - name: computed-dimmed
      profile_id: 8439ba57-ac80-4905-86c5-2acee72d26c5
      output: /opt/dirigera-readaptive/schedules/computed-dim.yaml
      curve:
        extend_day_after_late_sunset: true
        min_light_level: 4
        morning_light_level: 70
        max_light_level: 85
        evening_light_level: 75
        pre_sleep_light_level: 65
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
hub profile only when its schedule changed.

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

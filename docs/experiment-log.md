# Experiment Log

## 2026-07-11

### Discovery

- mDNS service `_ihsp._tcp` identified the hub as
  `gw2-3d437fc68e68.local` at `192.168.1.249:8443`.
- Direct local HTTPS worked outside the command sandbox.
- `/v1/home` without a token returned HTTP `401`, confirming the API listener.

### Pairing

- Used OAuth PKCE flow:
  - `GET /v1/oauth/authorize`
  - physical hub action button
  - `POST /v1/oauth/token`
- Token saved locally to `.env`, which is gitignored.

### Baseline

- Device count: 25.
- Light count: 10.
- Adaptive profile count: 3.
- All 10 lights initially reported `adaptiveProfile.active: true`.

### Test Light

- Test device: `Obývák lustr`.
- Device ID: `846dad52-55e2-4ee2-ba48-b929186a2d2a_1`.
- Model: `KAJPLATS E27 WS globe 1521lm`.
- Adaptive profile: `d898dfe9-bcfa-4dc4-ae2a-3b3812e6a22d`.

### App Adaptive Tap

- Starting from non-Adaptive state:
  - `adaptiveProfile: {}`
  - `colorTemperature: 3003`
- After tapping Adaptive in IKEA app:
  - `adaptiveProfile.active: true`
  - `colorTemperature: 3311`
  - `deviceOnBehavior` unchanged.

### HTTP Candidate

- Sent:

```json
[
  {
    "adaptiveProfile": {
      "id": "d898dfe9-bcfa-4dc4-ae2a-3b3812e6a22d",
      "active": true
    }
  }
]
```

- Result:
  - HTTP `202`.
  - `adaptiveProfile.active: true`.
  - Brightness restored from manual `25` to native profile `93`.
  - `deviceOnBehavior` unchanged.

### Physical Power Cycle

- `Obývák lustr` was physically cycled.
- Post-cycle read:
  - `isReachable: true`
  - `isOn: true`
  - `lightLevel: 93`
  - `colorTemperature: 3322`
  - `adaptiveProfile.active: true`
- This cycle did not reproduce the stale brightness failure.
- Running the candidate patch afterward returned HTTP `202` and kept Adaptive
  active.

### Clarified Failure Mode

- A mains power cycle can leave the light reporting Adaptive while retaining
  stale brightness if the active profile shifted while the bulb was offline.
- After a manual remote/app override followed by a normal off/on action, the
  user's current IKEA app configuration already re-enters Adaptive as expected.
- The daemon therefore enables `isReachable: false -> true` recovery by default
  and keeps `isOn: false -> true` recovery optional/disabled by default.

### Computed Schedule Mutation

- User added a new adaptive profile named `Computed schedule`.
- Profile ID: `7bbebe49-41a3-48ea-8f5f-9e33a36dad87`.
- Route discovery:
  - `OPTIONS /v1/adaptive-profiles` -> `POST`
  - `OPTIONS /v1/adaptive-profiles/<id>` -> `PUT,DELETE`
- No devices were using the profile at the time of the experiment.
- A no-op `PUT` with the current profile body returned HTTP `202`.
- A one-value mutation changed the `20:00` entry from `lightLevel: 80` to
  `lightLevel: 81`.
- The mutation returned HTTP `202` and `/v1/home` confirmed the new schedule.

### ZdraveSvetlo Logic Port

- Extracted the vvvv patch's warm/cool channel logic into Python.
- Ported the sunrise/sunset utility used by the old project.
- Generated a DIRIGERA `adaptiveSchedule` YAML document from date, location,
  timezone, and curve settings.
- Added optional late-sunset day extension so summer sunset does not invert the
  evening ramp or make midnight look like an evening peak.
- Tuned the emitted IKEA schedule after inspecting the generated profile in the
  IKEA app: standard overnight level is now `10%`, brightness and color
  temperature are separate curves, temperature transitions follow the existing
  summer profiles more closely, and the evening falloff is smoother pending an
  actual evening comfort test.
- Created a second hub profile from `schedules/computed-dim.generated.yaml`:
  `Computed schedule dimmed`
  `8439ba57-ac80-4905-86c5-2acee72d26c5`.
- Replaced the schedule timer path with one config-driven updater:
  `dirigera_readaptive.schedule_profiles_cli --config config.yaml`. A local
  run confirmed both `computed-standard` and `computed-dimmed` already matched
  their hub profiles.

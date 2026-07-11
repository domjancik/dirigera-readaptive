# Findings

## Verified Observations

- Hub discovery found DIRIGERA at `192.168.1.249`, hostname
  `gw2-3d437fc68e68.local`, local API version `1.6.7`.
- OAuth pairing through `/v1/oauth/authorize` and `/v1/oauth/token` worked and
  is additive to the IKEA app pairing.
- `/v1/home` reported three adaptive profiles.
- Two adaptive profiles are in active use:
  - `d898dfe9-bcfa-4dc4-ae2a-3b3812e6a22d` for most lights.
  - `42adacb4-1d9d-4ff5-8cb9-4d453f592c01` for the dimmer kitchen light.
- `deviceOnBehavior` remained
  `{ "behavior": "adaptiveProfile", "profileId": "<id>" }` even when the light
  was manually moved out of Adaptive. It is not the active-mode switch.
- Setting `attributes.lightLevel` to `25` on `Obývák lustr` cleared
  `adaptiveProfile`.
- Sending the top-level `adaptiveProfile` patch below returned HTTP `202`,
  restored `adaptiveProfile.active: true`, and restored brightness from `25` to
  the native profile level `93`:

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

- The same patch is idempotent when the light is already in Adaptive: it
  returned HTTP `202` and left `adaptiveProfile.active: true`.
- The failure mode is narrower than "Adaptive turns off": a bulb can still
  report `adaptiveProfile.active: true` after a mains cycle while keeping stale
  brightness if the profile shifted while the bulb was unpowered.
- A normal app/remote off-to-on transition after a manual override can be used
  as an example of expected turn-on behavior. It works as configured in the
  user's IKEA app setup, so the daemon's `isOn` trigger is optional and disabled
  by default.

## Hypotheses

- The IKEA app's Adaptive button likely performs the same top-level
  `adaptiveProfile` patch for the selected light.
- On reconnect, applying this patch once should refresh native Adaptive
  brightness/temperature without replacing IKEA's algorithm.
- On `isOn: false -> true`, applying the same patch once can be useful for
  setups that want explicit power-on recovery. This trigger is configurable and
  disabled by default.

## Failed Or Inconclusive Experiments

- A PowerShell WebSocket client failed to connect; the Python `websockets`
  client worked.
- One 30-second WebSocket capture around an app tap produced no events. HTTP
  before/after state still showed the active-mode transition.
- The physical power-cycle test on `Obývák lustr` did not reproduce the stale
  brightness state during this session; the light returned already healthy.

## Exact Native Command Candidate

```http
PATCH https://<hub>:8443/v1/devices/<device-id>
Authorization: Bearer <token>
Content-Type: application/json

[
  {
    "adaptiveProfile": {
      "id": "<profile-id>",
      "active": true
    }
  }
]
```

This command is implemented by the daemon. It does not write
`deviceOnBehavior`, schedules, brightness, or color temperature.

## Adaptive Schedule Editing

The local API also exposes adaptive profile writes:

```http
PUT https://<hub>:8443/v1/adaptive-profiles/<profile-id>
Authorization: Bearer <token>
Content-Type: application/json
```

Body shape:

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

Verified against `Computed schedule`
`7bbebe49-41a3-48ea-8f5f-9e33a36dad87`:

- `OPTIONS /v1/adaptive-profiles` returned `POST`.
- `OPTIONS /v1/adaptive-profiles/<id>` returned `PUT,DELETE`.
- A no-op `PUT` of the existing profile returned HTTP `202`.
- A schedule mutation changing the `20:00` light level from `80` to `81`
  returned HTTP `202` and was visible in the following `/v1/home` read.
- A separate dimmed computed profile was created with
  `POST /v1/adaptive-profiles`:
  - Name: `Computed schedule dimmed`
  - ID: `8439ba57-ac80-4905-86c5-2acee72d26c5`
  - Source file: `schedules/computed-dim.generated.yaml`
  - Confirmed with 54 schedule entries in `/v1/home`.

## Extracted ZdraveSvetlo Schedule Logic

- The old project uses Paul Schlyter's sunrise/sunset calculation for sunrise,
  sunset, and nautical twilight.
- The vvvv `MapTween` helper maps a time window to `0..1`, optionally reverses
  it with `Down`, applies sine easing (`In`, `Out`, or `InOut`), then maps to
  the requested output range.
- Warm light:
  - Night baseline is `0.2`.
  - Evening/pre-sleep peak is `0.7`.
  - Nautical sunrise to sunrise fades warm light out.
  - Sunset to pre-sleep fades warm light in.
  - Pre-sleep to sleep fades warm light back to the night baseline.
- Cool light:
  - Sunrise starts at `0.37`.
  - Sunrise to solar noon rises to `1.0`.
  - Solar noon to sunset falls back to `0.37`.
  - Sunset to pre-sleep falls to `0.0`.
- The DIRIGERA adapter converts the stronger of the warm/cool channels to
  `lightLevel` and converts the cool share of the combined channels to
  `colorTemperature`.
- Late summer sunsets can occur after the fixed pre-sleep/sleep points from the
  original patch. The Python port therefore supports optional day extension so
  pre-sleep/sleep move later, capped by a configured latest sleep time.
- We should maintain both a normal/full-peak generated schedule and a dimmed
  lower-peak variant for rooms that should follow the same temperature curve at
  reduced brightness.
- After comparing with the existing IKEA summer profiles, the generated
  `adaptiveSchedule` now decouples schedule brightness and color temperature
  from the raw ZdraveSvetlo warm/cool channels. The raw channels remain as the
  extracted model, while the emitted IKEA schedule uses smoother anchors:
  `10%` overnight for the standard profile, `2700K` in the morning, `4600K`
  around solar noon, about `2450K` before sunset, `2200K` at pre-sleep, and
  `1000K` at sleep.

## Remaining Uncertainties

- We have not yet captured the IKEA app's raw HTTPS request.
- We have not yet reproduced the stale post-mains-cycle brightness failure in
  this session.
- Zigbee IKEA lights and Matter KAJPLATS lights should be validated separately.

# Running mfdhome

## Setup

```bash
poetry install
```

Home Assistant access comes from `HA_URL` and `HA_TOKEN` (a long-lived access
token), set in the environment or in a local `.env` file:

```
HA_URL=http://homeassistant.local:8123
HA_TOKEN=...
```

`.env` is gitignored, and variables already set in the environment win. The
token is only ever sent to Home Assistant: it's never logged, never shown, and
never reaches a display's browser.

Keep your house's config (`defs.yaml`, `alerts.yaml`, `displays.yaml`,
`pages/`) in its own private repository. Point the commands at it with a path
argument or `MFD_CONFIG`. `examples/config/` is a complete starting point.

## Commands

| Command | What it does |
|---|---|
| `mfdhome check CONFIG` | Validates the config and reports every problem with file and line. |
| `mfdhome check CONFIG --ha` | Also lists every bound entity that doesn't exist in Home Assistant, with where it's used. |
| `mfdhome check CONFIG --states FILE` | The same, against a saved states dump instead of a live HA. |
| `mfdhome dump-states -o states.json --scrub` | Saves HA's current states as a fixture. `--scrub` keeps only what rendering needs and drops people and location domains. |
| `mfdhome serve CONFIG` | Runs the live display server (see below). |

Add `-v` before the command for debug logging.

## Serving displays

```bash
mfdhome serve CONFIG --port 8099 --board var/board.json
```

- **Display URLs:** each display in `displays.yaml` is served at
  `http://<server>:8099/display/<id>`. Open that URL in the display's kiosk
  browser. `/` lists them all.
- **Access:** run it on your local network only. If `MFD_DISPLAY_TOKEN` is set,
  every URL needs `?token=<that value>`; put it in each kiosk's URL.
- **Alert board:** latched and acknowledged alerts are saved to the `--board`
  file and survive restarts.
- **Acknowledging:** tap the banner to acknowledge the alert it names, or tap
  an annunciator tile to acknowledge that system's alerts. Acknowledgements
  count for the whole house.
- **Soft keys:** displays with more than one page get PREV, ALERTS, LOCK and
  NEXT keys at the bottom. ALERTS jumps to the alerts page and is lit while
  something needs acknowledging. LOCK ignores every tap except LOCK until it's
  tapped again. A display with one page (like the mirror) has no keys.
- **Live behavior:** displays update within a fraction of a second of a
  change in Home Assistant. Data that stops arriving goes dotted after its
  `stale_after` limit. If Home Assistant is unreachable, everything shows as
  unavailable until it reconnects, and the display shows "OFFLINE" while its
  own connection to the server is down.

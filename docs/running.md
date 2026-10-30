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

`.env` is gitignored, and variables already set in the environment win. As a
Home Assistant add-on, set neither: mfdhome then connects through the
Supervisor with the token it provides (see [addon/DOCS.md](../addon/DOCS.md)). The
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
| `mfdhome dump-states -o states.json --scrub` | Saves HA's current states as a fixture. `--scrub` keeps only the attributes pages read (units, device and state classes, thermostat and water heater temperatures, setpoints and action, positions), drops names, and drops people and location domains. |
| `mfdhome render CONFIG DISPLAY` | Renders one display once, to `DISPLAY.png` for e-paper panels or `DISPLAY.svg` otherwise. `--states FILE` renders a saved states dump (alerts included), `--page` picks a page, `-o` names the file. |
| `mfdhome serve CONFIG` | Runs the live display server (see below). |
| `mfdhome serve CONFIG --states FILE` | The same, from a fixed states dump instead of Home Assistant. |
| `mfdhome serve CONFIG --scenario FILE` | The same, replaying a scripted scenario instead of Home Assistant. |

Add `-v` before the command for debug logging.

## Developing without Home Assistant

`--states` and `--scenario` run the whole server (displays, alerts, the
board, history and the log) with no Home Assistant at all, so pages can be
built and checked anywhere. `HA_URL` and `HA_TOKEN` aren't needed.

A scenario is a starting states file plus timed steps, optionally looping:

```yaml
states: house_normal.json        # relative to this file; HA /api/states shape
loop: 4m                         # optional: start over after this long
steps:
  - at: 20s
    set:
      binary_sensor.grid_connected: "off"                         # a state (attributes kept)
      sensor.grid_power: {state: "0", attributes: {unit_of_measurement: W}}  # replaced
  - {at: 2m, connected: false}   # Home Assistant goes away (alerts freeze)
  - {at: 130s, connected: true}
  - {at: 3m, remove: [sensor.grid_power]}                          # an entity disappears
```

Steps play in real time, so hold times (`for:`), latching, the banner, ACK
and the log all behave as they would live. `examples/scenarios/` has a quiet
example house and looping scenarios for the example config: a grid outage,
a water heater leak closed off by the smart shutoff, a break-in, a network
outage (the shop switch drops and the mesh repeater goes quiet), and spiky
loads (a kettle, a passing cloud: watch the tablet and the e-ink panel side
by side):

```bash
mfdhome serve examples/config --scenario examples/scenarios/grid_outage.yaml
```

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
- **Alert history:** every raise, clear and acknowledgement is appended to the
  `--history` file (`var/history.jsonl`, one JSON event per line) and kept
  for `--history-days` days (default 14). Only changes are recorded, so an
  alert that stays raised adds nothing until it clears.
- **Acknowledging:** tap the banner to acknowledge the alert it names, or tap
  an annunciator tile to acknowledge that system's alerts. Acknowledgements
  count for the whole house.
- **Soft keys:** displays with more than one page get four keys at the
  bottom: PREV and NEXT at the ends, and two that depend on the page (ALERTS
  and LOCK; ACK and LOCK on the alerts page; PG UP and PG DN on log pages).
  ALERTS jumps to the alerts page and, like ACK, is lit while something
  needs acknowledging. LOCK ignores every tap except LOCK until it's tapped
  again. A display with one page (like the mirror) has no keys.
- **Live behavior:** displays update within a fraction of a second of a
  change in Home Assistant. Data that stops arriving goes dotted after its
  `stale_after` limit. If Home Assistant is unreachable, everything shows as
  unavailable until it reconnects, and the display shows "OFFLINE" while its
  own connection to the server is down. Alerts are frozen while Home
  Assistant is unreachable, so a network blip doesn't raise or clear
  anything; the history records the connection being lost and restored.

## E-paper displays

A display with a `panel` in `displays.yaml` is served as a PNG that the device
polls for:

| Route | What it does |
|---|---|
| `GET /display/<id>.png` | The current page, at the display's `size`, in the panel's colors only. |
| `POST /display/<id>/key/<1-4>` | Presses key 1 to 4 (left to right), like the soft keys: what it does depends on the page shown, and the lock applies. |

Both take `?token=...` when `MFD_DISPLAY_TOKEN` is set.

- **Averaged values:** the image is rendered when the device fetches it, and
  its measurements (power, flow, temperature, throughput: whatever Home
  Assistant marks `state_class: measurement`) show their time-weighted
  average over the display's `refresh`, 5 minutes by default. A kettle or a
  passing cloud then nudges the numbers instead of being held on the panel
  until the next refresh. On/off states, text states, totals and attributes
  (setpoints) always show as they are now, a sensor that is unavailable now
  shows no data, and alerts always judge live readings. After a restart the
  window fills over its first period. See "Displays" in
  `docs/page-schema.md` for `refresh`, `average` and per-entity overrides.
- **The server paces redraws:** poll often (every 30 s suits most panels).
  The server keeps sending the same image until the display's `refresh` has
  passed, or something besides the measurements changes (a new, cleared or
  acknowledged alert, a key press, a lost Home Assistant connection), so new
  alerts reach the panel within a poll while it still redraws only every few
  minutes. If the device polls less often than about every 2 × `refresh`,
  the server logs a warning once.
- **Cheap polling:** every PNG carries an `ETag`. A request with that tag in
  `If-None-Match` gets `304 Not Modified` while the image is unchanged, so the
  device need not redraw.
- **"As of" stamp:** the bottom strip shows when the content last changed, as
  seen at a fetch (server local time), so an unchanged page keeps the same
  image. On an averaging display `AVG 5M` sits above it, so nobody takes the
  numbers for live ones. A device that fails to fetch should mark that itself
  (the ESPHome example below draws OFFLINE), because a frozen image looks
  exactly like a quiet house.
- **Keys:** the key labels are drawn along the bottom strip when the display
  has more than one page; mount the four buttons beneath them. Buttons send
  their position, and the label above each says what it does on that page,
  including ACK on the alerts page, so alerts can be acknowledged without a
  touchscreen.
- **Refresh:** a page change from a button press shows on the next fetch, so
  have the device fetch right after a press. Pick a `refresh` that suits the
  panel: a few minutes for mono and gray panels, longer for six-color panels,
  which take 15–30 s to redraw. Averaged numbers usually change a little from
  one refresh to the next, so expect a redraw at most refreshes.

Check a layout without a device:

```bash
mfdhome render CONFIG main_floor --states tests/fixtures/electrical_islanded.json --page electrical
```

### ESPHome example

A sketch for an ESP32 (with PSRAM: a decoded 800×480 frame doesn't fit
in plain RAM) driving a mono panel with four buttons. Adjust the display
platform, pins and image `type` (`BINARY` for mono, `GRAYSCALE` for gray
panels, a color type for six-color panels) to your hardware, and check option
names against your ESPHome version's `online_image` and `http_request` docs.

```yaml
substitutions:
  mfd: http://mfd.local:8099/display/main_floor
  token: "?token=CHANGE_ME"        # or "" without MFD_DISPLAY_TOKEN

http_request:
  timeout: 10s

globals:
  - id: offline
    type: bool
    initial_value: "false"

online_image:
  - id: frame
    url: ${mfd}.png${token}
    format: PNG
    type: BINARY
    update_interval: 30s           # poll; the server sends a new image only when due
    on_download_finished:
      - lambda: id(offline) = false;
      - if:
          condition:
            lambda: return !cached;    # 304: same image, no redraw
          then:
            - component.update: epaper
    on_error:
      - lambda: id(offline) = true;
      - component.update: epaper

font:
  - file: "gfonts://Roboto Mono"
    id: small
    size: 16

display:
  - platform: waveshare_epaper     # your panel's driver and model
    id: epaper
    model: 7.50inV2
    cs_pin: GPIO15
    dc_pin: GPIO27
    busy_pin: GPIO25
    reset_pin: GPIO26
    update_interval: never         # redrawn only when the image changes
    lambda: |-
      it.image(0, 0, id(frame));
      if (id(offline)) {
        it.filled_rectangle(it.get_width() - 100, 0, 100, 26, COLOR_ON);
        it.print(it.get_width() - 50, 13, id(small), COLOR_OFF, TextAlign::CENTER, "OFFLINE");
      }

script:
  - id: press
    parameters:
      key: string
    then:
      - http_request.post:
          url: !lambda 'return "${mfd}/key/" + key + "${token}";'
          on_response:
            - component.update: frame  # fetch the new page right away

binary_sensor:
  - platform: gpio
    pin: {number: GPIO32, mode: INPUT_PULLUP, inverted: true}
    name: Key 1                    # PREV
    on_press: {script.execute: {id: press, key: "1"}}
  - platform: gpio
    pin: {number: GPIO33, mode: INPUT_PULLUP, inverted: true}
    name: Key 2                    # ALERTS / ACK / PG UP
    on_press: {script.execute: {id: press, key: "2"}}
  - platform: gpio
    pin: {number: GPIO34, mode: INPUT, inverted: true}   # needs an external pull-up
    name: Key 3                    # LOCK / PG DN
    on_press: {script.execute: {id: press, key: "3"}}
  - platform: gpio
    pin: {number: GPIO35, mode: INPUT, inverted: true}   # needs an external pull-up
    name: Key 4                    # NEXT
    on_press: {script.execute: {id: press, key: "4"}}
```

A Raspberry Pi (or any other device) uses the same two routes: fetch the PNG
with `If-None-Match`, draw it when the response is `200`, and `POST` a key on
each button press.

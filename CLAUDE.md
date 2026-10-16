# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project overview

`mfdhome` is a Python library for building **multifunction-display (MFD) style
"house status" pages** for a Home Assistant (HA) smart home. Pages are stylized
instrumentation-and-control (I&C) schematics (think P&ID / avionics MFD), not
standard HA dashboards. Examples: an Electrical page (solar → battery → loads ↔
grid), a Water page (main → shutoff valve → branches, leak sensors), a Network
page (WAN → router → switches → APs), and a Status/annunciator page.

The core idea is **author once, render many**: a page is defined once and
rendered to several display targets with different themes and constraints:

| Target | Theme | Hardware | Rendering | Constraints |
|---|---|---|---|---|
| `tablet` | `lcd` | Rugged Android tablet (workshop), kiosk browser | Live SVG/HTML, interactive | Touch targets ≥ 48px, glove-friendly |
| `mirror` | `mirror` | Two-way mirror over a monitor, kiosk browser | Live SVG/HTML | **Pure black background**, thin bright lines, no large light areas |
| `eink` | `eink_mono` / `eink_color` | 10–13" e-paper panel (main floor), likely ESPHome on an ESP32 | Server-side snapshot → PNG fetched by the device | No animation, limited palette (1-bit / grays / 6-color), refresh every 1–5 min, bezel buttons for page select |

House content (which sensors exist, where systems physically are) changes often,
so **page definitions are data, separate from library code**.

## Architecture

```
src/mfdhome/
  model/       # Page, Element, Binding, Alert dataclasses (pure data, no I/O)
  conditions/  # Pure condition logic (DNF rules, evaluation, thresholds/map
               # shorthands), shared by element status and alerts
  symbols/     # I&C symbol primitives, each returning SVG fragments: electrical
               # (breaker, transfer, battery, panel, meter, combiner), water
               # (valve, fittings, vessels, water_heater, outlet), hvac
               # (furnace, damper, thermostat), sensor (sensor, gauge),
               # floorplan (rooms, walls, openings, alarm panel), line, tile.
               # registry.py declares each type's channels, box, ports and
               # params; geometry.py gives element boxes and port points;
               # format.py formats readings.
  layout/      # Positioning helpers: anchors, polyline geometry, grids
               # (adaptive group layouts later)
  themes/      # Gruvbox palette and built-in themes (lcd, mirror, eink_mono,
               # eink_color):
               # palette, stroke weights, tile fill, attention style, fonts
  render/      # Pure render functions: (page, state, theme, target) -> SVG string;
               # resolve.py resolves status/derived channels bottom-up through
               # groups. log.py builds and draws the alert log. panels.py
               # (e-paper panel profiles) and raster.py (SVG ->
               # PNG via resvg, quantized to the panel palette)
  sources/     # State providers: HA websocket client (ha.py), JSON fixtures,
               # scripted scenarios (scenario.py), staleness marking
  mfd/         # MFD behavior: alert latching, hold times, house-wide
               # acknowledgement and attention order (pure, caller supplies the
               # clock); history events (history.py); page selection per
               # display and what each key does per page (keys.py)
  server/      # Live runtime (alert loop, persisted board and history, page
               # selection, log paging) and
               # the aiohttp display server (HTML shell + WebSocket frames,
               # static/client.js), and PNG snapshots + key presses for e-paper
               # displays (images.py).
  fonts/       # Bundled DejaVu Sans Mono (with its license), used by rasterization
  cli.py       # `mfdhome check | dump-states | render | serve` (see docs/running.md)
  config/      # Loading + validating page definition files (YAML, see
               # docs/page-schema.md). pydantic stays inside this package.
tests/
  fixtures/    # Recorded and synthetic HA state snapshots (JSON) and a test
               # config/ directory
  snapshots/   # Expected SVG/PNG output for snapshot tests
examples/
  config/      # Example config: defs, alerts, displays, pages (status,
               # electrical, water, hvac, security, log). Do not hardcode house
               # specifics in src/
  scenarios/   # A quiet example house and looping scenarios for
               # 'serve --scenario' (grid outage, water leak, break-in)
```

### Core rules

1. **Rendering is pure.** Render functions take a page definition, a state
   snapshot (plain dict of entity_id → state/attributes), a theme, and a target,
   and return SVG. No network calls, no clock reads, no randomness inside render
   code. This keeps output deterministic and snapshot-testable.
2. **HA access lives only in `sources/`.** Everything else works on state
   snapshots. Never import the HA client from `render/`, `symbols/`, or `model/`.
3. **Bindings are declarative.** A page element binds to HA entities and maps
   state to visual properties (color, flow arrow on/off, rotation,
   text). Prefer adding a new binding type over writing ad-hoc logic in a page.
4. **Themes, not conditionals.** Target differences (colors, stroke widths,
   animation allowed, palette size) belong in theme/target objects, not
   `if target == "eink"` branches scattered through render code.
5. **Missing or unavailable entities must render gracefully** (dotted / gray
   "no data" state), never crash. New sensors get added over time; stale configs
   are normal.
6. **Shared visual language across all targets,** from the Gruvbox palette:
   aqua `#8ec07c` = normal, yellow `#fabd2f` = caution, red `#fb4934` = warning,
   blue `#83a598` = flow/active/advisory, gray `#928374` + dotted = unavailable
   (on every element: lines, symbol outlines, tiles).
   Keep symbol shapes identical across themes; palette, stroke weights, tile
   fill and attention style vary by theme. Never rely on color alone where a
   palette can't show it: symbols carry severity in weight and fill on
   monochrome themes, and **lines carry it in pattern on every theme** (solid =
   normal, solid core = flowing, dashed core = caution, hatched = warning,
   dotted = unavailable).
   Patterns are therefore reserved for status: group frames can't use them,
   and lines have no weights or styles of their own.

### MFD behavior

- **Pages are selected, never auto-cycled.** Each display has a home page and a
  list of selectable pages; the viewer picks one with hardware buttons or with
  touchscreen soft keys drawn as stylized bezel buttons around the page (MFD
  style). The display stays on the selected page until changed.
- Alerts have severity (`advisory`, `caution`, `warning`) and belong to a
  system (one annunciator tile each). Defined in `alerts.yaml`.
- Cautions and warnings **latch**: they stay until acknowledged, even after
  their condition clears ("cleared, unacknowledged" is its own visible state).
  Advisories clear on their own.
- **One acknowledgement counts for the whole house** (one shared alert board);
  record who acknowledged and when.
- **No preemption (for now):** alerts never switch a display's page. While any
  caution/warning is unacknowledged, the annunciator banner shows over the
  current page (bottom of the canvas; keep the bottom 40 units of pages
  clear), naming the most urgent one: warning before caution, life-safety
  alerts (`life_safety: true`: smoke, CO, gas, a triggered alarm) first within
  a severity, active before cleared, most recently raised first.
- Unacknowledged cue by display type: LCD/LED panels flash (≤ 1 Hz), the mirror
  pulses slowly, e-ink draws a static outline ring.
- The Status/annunciator page is the default/home page.
- A mirror is configured to one page and not normally changed: it has no page
  selection.

## Tooling and commands

Python packaging uses **Poetry**. Always run tools through Poetry.

```bash
poetry install                      # install deps (including dev group)
poetry run pytest                   # run tests
poetry run pytest --snapshot-update # update SVG snapshots (only when output change is intended)
poetry run ruff check .             # lint
poetry run ruff format .            # format
poetry run mypy src                 # type check
poetry run mfdhome check examples/config   # validate a config directory
```

Running the live server is described in `docs/running.md`.

Before considering a task done: tests pass, ruff is clean, mypy is clean.

- Target Python 3.14+.
- Add dependencies with `poetry add <pkg>` (or `poetry add --group dev <pkg>` for
  dev tools). Do not edit dependency lists in `pyproject.toml` by hand, and do not
  use pip directly.
- Keep runtime dependencies minimal and justified. Ask before adding a new
  runtime dependency.

## Code conventions

- Full type hints everywhere; mypy strict-ish. Prefer dataclasses (frozen where
  practical) or pydantic models for config validation.
- SVG is generated as text/structured elements in Python; do not depend on a
  browser to produce SVG. Rasterization for e-ink may use a dedicated library.
- Coordinates: define pages on a logical canvas and scale to target resolution;
  do not hardcode device pixel sizes in page definitions.
- Docstrings on public API. Small, composable functions.
- Logging via the `logging` module, no prints in library code.

## Testing

- Use recorded state fixtures in `tests/fixtures/` instead of a live HA.
- Snapshot-test rendered SVG per page × target. When a snapshot changes, explain
  why in the summary of your work.
- Test edge cases: unavailable entities, missing attributes, extreme values
  (negative grid power = export), alert attention ordering.
- E-ink rendering tests should assert palette compliance (no colors outside the
  panel palette after quantization).

## Secrets and environment

- HA connection uses `HA_URL` and `HA_TOKEN` (long-lived access token) from the
  environment or a local `.env` file.
- **Never commit `.env`, tokens, or real network details.** Never print tokens in
  logs or test output.
- Do not read `.env` contents; reference the variable names only.

## Working style

- For anything larger than a small fix, propose a plan first and wait for
  approval.
- Keep changes focused; one concern per commit, with clear commit messages.
- When a design decision is not yet settled (see below), ask rather than choose
  silently.

## Settled decisions

- **Page definitions are YAML** (parsed as YAML 1.2 by ruamel.yaml, so `on`/`off`
  stay strings), validated with pydantic. Format reference: `docs/page-schema.md`.
- Elements are placed at absolute x/y on a logical canvas. Symbols have a fixed
  size. Text attaches to elements via nine named anchors.
- Elements bind entities to named channels declared by the symbol registry.
  Status rules are in disjunctive normal form (OR of AND-groups) and may refer
  to any entity, not just the element's own channels.

- **Colors come from Gruvbox.** Aqua replaces Gruvbox green for "normal"
  because green and yellow are nearly indistinguishable under color-vision
  deficiency; orange is unused for the same reason. The mirror keeps a pure
  black background; the LCD theme uses Gruvbox `bg0_h`.
- **Alerts live in `alerts.yaml`** (systems + alerts), using the same condition
  format as status rules but entity references only.
- **Annunciator tiles have a fixed size** (160 x 64) and are positioned
  manually or with `tile_grid`. Manual placement must always remain possible.
- **Battery power: negative = discharging**, positive = charging.
- **Whole-home backup topology:** a grid-isolating `transfer_switch` (ATS)
  sits between the main breaker and the backup bus; battery, solar and the load
  panel are on the house side. Islanding shows on the ATS as caution; the grid
  loss itself is a warning on the GRID system.
- **Connections route with at most one elbow**, following port directions,
  unless `via` gives bends explicitly. **A flowing cased line has a solid
  core**, using the same threshold as its flow arrow; a blank (hollow) core
  means no flow. **The flow arrow is a harpoon beside the line**, set off
  from its edge (never over the core), level with the first readout on the
  opposite side, never wrapping a bend.
- **Lines attach to elements** by `element.port` (edge/corner ports named like
  anchors, plus type-specific ports such as a breaker's `in`/`out`) or to
  `node` elements; nodes with 3+ attached lines get a junction dot. Endpoints
  resolve at load time.
- **Lines are hollow pipes (cased) by default**; `casing: false` on a line
  draws it plain, for sensing and minor connections. There are no line
  weights or named styles: widths come from the theme, so every pipe is the
  same width, and color and pattern always carry status.
- **Groups** contain items (symbols, tiles, nested groups) laid out by a grid;
  items have no connections of their own and connect through the group's
  ports. Item ids are scoped paths (`array.p3`); repetition is explicit
  (`item_defaults` + listed `items`); connecting to an item is a load error.
  Groups derive channels (`sum`/`min`/`max`/`count`) and default to their
  items' worst caution/warning, unavailable only when every item is.
  `tile_grid` is shorthand for a frameless group of tiles. Elements can bind
  to another element's channel (`array.power`), without chains.

- **Server stack: aiohttp** for both the HA websocket client and the display
  server (one runtime dependency). **Displays get live updates over a
  WebSocket**, which also carries acknowledgements back; the client patches
  changed top-level `<g id>` groups rather than replacing the page.
- **The real house config lives in a separate private repo**; the server is
  pointed at it with a path argument or `MFD_CONFIG`. Only generic examples
  live here.
- **Live runtime:** HA states arrive over HA's websocket API; bindings can
  `scale` values and set a `unit`; entities unreported for longer than
  `stale_after` count as unavailable. The alert board persists as JSON.
  `displays.yaml` gives each display a theme, size, home page and selectable
  pages. Browsers receive only rendered SVG; an optional `MFD_DISPLAY_TOKEN`
  gates display URLs.
- **E-paper rendering:** resvg (resvg-py) rasterizes with only the bundled
  font, then Pillow quantizes to the panel profile (`mono`, `gray4`,
  `gray16`, `spectra6`) by exact nearest color, never dithered, and writes an
  indexed PNG. Panels without intermediate tones render without
  antialiasing. A display's `panel` in `displays.yaml` makes it an e-paper
  display; its theme may only draw colors the panel shows (checked at load).
  `eink_color` draws the Gruvbox roles in the Spectra 6 inks (no gray ink:
  unavailable is black dotted; yellow never carries text). All displays
  are landscape.
- **E-paper delivery:** the device pulls `GET /display/<id>.png` on a timer
  (ETag / 304 when unchanged) and presses keys with `POST
  /display/<id>/key/<key>`. The expected device is ESPHome on an ESP32
  (`online_image`), possibly a Pi Zero; both use the same routes. The "as of"
  stamp in the bottom strip shows when content last changed, not fetch time,
  so unchanged pages don't redraw; the device marks failed fetches itself.
- **Soft keys** share the bottom 40-unit strip with the banner (no page
  space lost). **Keys are positions 1-4** (like bezel buttons; soft keys,
  the WebSocket and the e-paper key route all send positions) and
  `mfd.keys` decides their action per page: 1 = PREV and 4 = NEXT always;
  the middle two are ALERTS/LOCK, **ACK/LOCK on the display's alerts page**
  (acknowledges the banner's alert, so hardware buttons can acknowledge),
  and **PG UP/PG DN on a page with an alert log**. PREV/NEXT wrap through
  `pages`; ALERTS (and ACK) light while a caution/warning is
  unacknowledged; LOCK is a tap toggle with no auto-relock, enforced by the
  server, in memory (displays start unlocked; a locked display can't change
  pages, so the lock can't get stuck). Keys are always shown on displays
  with more than one page and never on single-page ones (the mirror).
- **Alert history** records only changes (raise, clear, acknowledge, and
  Home Assistant connection lost/restored) to `var/history.jsonl`, kept 14
  days by default. **Alerts are frozen while Home Assistant is
  disconnected.** Alerts may have a **`for:` hold time** (must hold that
  long to raise, and stop holding that long to clear).
- **Offline development:** `serve --states FILE` and `serve --scenario FILE`
  run everything without Home Assistant; synthetic fixtures follow
  `docs/entities.md` until the real-house check.
- **Media are told apart by service tags** on lines (`CW`, `HW`, `GAS`,
  `SA`, `RA`); color and pattern stay reserved for status. Numeric
  comparisons may compare against another value plus an offset (a room
  against its setpoint).
- **Floorplans** are rooms and walls (polygons/polylines in page YAML, in
  the theme's structure color) plus `opening` symbols for doors and windows
  on contact sensors and an `alarm_panel` badge. Displays never arm,
  disarm or silence anything.
- **Life-safety alerts** (`life_safety: true`) are named first within their
  severity; on the annunciator their systems (FIRE, GAS, SEC, LEAK) come
  first. **Logged entities** (`log:` in alerts.yaml, e.g. arming) appear in
  the alert log as information rows. Severities follow the guide in
  `docs/page-schema.md` ("Choosing a severity").
- **Alert log** (`alert_log` element): one row per change, newest first;
  advisories read START/END; repeat raise/clear cycles within 5 minutes
  fold into one FLAPPING row per alert; batches separated by rules; paged
  with PG UP/PG DN, always reopening on the newest entries. The log page is
  listed last in `pages`, so it sits just before the alerts (home) page.

## Next milestone

- **Real-house check (needs the owner):** run `mfdhome dump-states --scrub`
  against the real Home Assistant, add the result as a fixture, map its
  entities onto `docs/entities.md`, and build the real Electrical, Water,
  HVAC and Security pages against it (in the private config repo). The
  roadmap that built these pages on synthetic fixtures (`docs/roadmap.md`)
  is complete.

## Future work (not yet scheduled)

- Preemption (switching displays to an alert's page) may return later; alerts
  would then need a `page` field again (removed while unused).
- Adaptive group layouts (e.g. "flow" to wrap at a width, "fit" to fill a
  box), so large alert sets and arrays don't need manual layout. In addition
  to, not replacing, manual positioning and the fixed grid.
- Flow animation, if wanted: animate the arrows only, never "marching dashes"
  (dashes mean caution).
- Hardware buttons for the mirror (e-ink buttons use the key route).
- An alert timeline page (rows per system across a time window) as a
  graphical companion to the log, if the log proves hard to scan.
- Immediate e-ink refresh on new alerts (a wake signal to the device, e.g.
  through Home Assistant's ESPHome integration); today alerts appear at the
  next scheduled fetch.
- A Pi Zero client for the PNG and key routes.
- Tuning against a real panel's pixels: `hatch_spacing`, dot spacing, and
  `core_inset` (at 800×480 the gap between a flowing pipe's walls and its
  core falls below a pixel on 1-bit panels).

## Open decisions (ask before settling)

- The exact e-ink panel (mono expected; six-color if one can be had) and its
  resolution, which fix the profile and the tuning above.

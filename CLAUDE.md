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
| `eink` | `eink_mono` | 10–13" e-paper panel (main floor) | Server-side snapshot → PNG pushed to device | No animation, limited palette (1-bit / grays / 6-color), refresh every 1–5 min, bezel buttons for page select |

House content (which sensors exist, where systems physically are) changes often,
so **page definitions are data, separate from library code**.

## Architecture

```
src/mfdhome/
  model/       # Page, Element, Binding, Alert dataclasses (pure data, no I/O)
  conditions/  # Pure condition logic (DNF rules, evaluation, thresholds/map
               # shorthands), shared by element status and alerts
  symbols/     # I&C symbol primitives: pipe, valve, pump, breaker, battery, meter,
               # node, link, tank, sensor badge. Each returns SVG fragments.
               # registry.py declares each type's channels, box, ports and params;
               # geometry.py gives element boxes and port points.
  layout/      # Positioning helpers: anchors, polyline geometry, grids
               # (adaptive group layouts later)
  themes/      # Gruvbox palette and built-in themes (lcd, mirror, eink_mono):
               # palette, stroke weights, tile fill, attention style, fonts
  render/      # Pure render functions: (page, state, theme, target) -> SVG string;
               # resolve.py resolves status/derived channels bottom-up through
               # groups. Later: rasterization to PNG for e-ink (quantize to panel)
  sources/     # State providers: HA websocket client (ha.py), JSON fixtures,
               # staleness marking
  mfd/         # MFD behavior: alert latching, house-wide acknowledgement and
               # attention order (pure, caller supplies the clock); page
               # selection per display
  server/      # Live runtime (alert loop, persisted board, page selection) and
               # the aiohttp display server (HTML shell + WebSocket frames,
               # static/client.js). Later: PNG endpoints for e-ink devices.
  cli.py       # `mfdhome check | dump-states | serve` (see docs/running.md)
  config/      # Loading + validating page definition files (YAML, see
               # docs/page-schema.md). pydantic stays inside this package.
tests/
  fixtures/    # Recorded HA state snapshots (JSON) and a test config/ directory
  snapshots/   # Expected SVG output for snapshot tests
examples/
  config/      # Example config: defs.yaml + pages/*.yaml. Do not hardcode house
               # specifics in src/
```

### Core rules

1. **Rendering is pure.** Render functions take a page definition, a state
   snapshot (plain dict of entity_id → state/attributes), a theme, and a target,
   and return SVG. No network calls, no clock reads, no randomness inside render
   code. This keeps output deterministic and snapshot-testable.
2. **HA access lives only in `sources/`.** Everything else works on state
   snapshots. Never import the HA client from `render/`, `symbols/`, or `model/`.
3. **Bindings are declarative.** A page element binds to HA entities and maps
   state to visual properties (color, line weight, flow arrow on/off, rotation,
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
   Patterns are therefore reserved for status: styles and group frames can't
   use them, and line weight is purely structural.

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
  clear), naming the most urgent one: warning before caution, active before
  cleared, most recently raised first.
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
  means no flow.
- **Lines attach to elements** by `element.port` (edge/corner ports named like
  anchors, plus type-specific ports such as a breaker's `in`/`out`) or to
  `node` elements; nodes with 3+ attached lines get a junction dot. Endpoints
  resolve at load time.
- **Connection styles** are named and relative (`defs.yaml` `line_styles`:
  weight, casing; never color or pattern). Casing (hollow pipe) is the
  default. Resolution: defaults → style → style's per-theme variant →
  element's own weight/casing → theme policy (`max_line_weight`,
  `casing_allowed`), which always wins. Per-display overrides will slot in
  before theme policy once display configurations exist (server milestone).
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

## Next milestone

- **Real-house check (needs the owner):** run `mfdhome dump-states --scrub`
  against the real Home Assistant, add the result as a fixture, and build the
  real Electrical page against it (in the private config repo).

## Future work (not yet scheduled)

- Preemption (switching displays to an alert's page) may return later, once
  page selection and bezel buttons exist.
- Adaptive group layouts (e.g. "flow" to wrap at a width, "fit" to fill a
  box), so large alert sets and arrays don't need manual layout. In addition
  to, not replacing, manual positioning and the fixed grid.
- Flow animation, if wanted: animate chevrons only, never "marching dashes"
  (dashes mean caution).
- Bezel page-select buttons: touchscreen soft keys rendered around the page
  (tablet, and the mirror if it gets touch) and hardware button input (e-ink
  bezel buttons, possibly the mirror). Labels come from the display's
  selectable pages.

## Open decisions (ask before settling)


- PNG rasterization library for e-ink.
- **Panel profiles** (deferred to the rasterization milestone): the exact colors
  a panel can show and its dithering policy, used by rasterization to quantize.
  The color e-ink theme (Gruvbox light, mapped onto the panel's colors) and the
  choice of e-ink panel type (1-bit, grayscale or 6-color) come with it, as
  does tuning `hatch_spacing` and dot spacing against the panel's pixels.
- How e-ink devices fetch images (pull a PNG URL vs push) and which firmware.

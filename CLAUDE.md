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
| `mirror` | `mirror` | Two-way mirror over a monitor, kiosk browser | Live SVG/HTML, auto-cycling | **Pure black background**, thin bright lines, no large light areas |
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
               # registry.py declares each type's channels, box and params.
  layout/      # Positioning helpers: anchors, polyline geometry, (later) grids
  themes/      # Gruvbox palette and built-in themes (lcd, mirror, eink_mono):
               # palette, stroke weights, tile fill, attention style, fonts
  render/      # Pure render functions: (page, state, theme, target) -> SVG string
               # plus rasterization to PNG for e-ink (quantize to panel palette)
  sources/     # State providers: HA websocket/REST client, static fixture source
  mfd/         # MFD behavior: alert latching, house-wide acknowledgement and
               # preemption order (pure, caller supplies the clock); later page
               # rotation and selection
  server/      # Web server: serves live pages to tablet/mirror, pushes updates,
               # exposes PNG endpoints for e-ink devices
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
5. **Missing or unavailable entities must render gracefully** (dashed / gray
   "no data" state), never crash. New sensors get added over time; stale configs
   are normal.
6. **Shared visual language across all targets,** from the Gruvbox palette:
   aqua `#8ec07c` = normal, yellow `#fabd2f` = caution, red `#fb4934` = warning,
   blue `#83a598` = flow/active/advisory, gray `#928374` + dashed = unavailable.
   Keep symbol shapes identical across themes; palette, stroke weights, tile
   fill and attention style vary by theme. Never rely on color alone where a
   palette can't show it: monochrome themes carry severity in weight and fill.

### MFD behavior

- Each display has a current page, a rotation list, and a dwell time.
- Alerts have severity (`advisory`, `caution`, `warning`) and belong to a
  system (one annunciator tile each). Defined in `alerts.yaml`.
- Cautions and warnings **latch**: they stay until acknowledged, even after
  their condition clears ("cleared, unacknowledged" is its own visible state).
  Advisories clear on their own and never preempt.
- **One acknowledgement counts for the whole house** (one shared alert board);
  record who acknowledged and when.
- An unacknowledged caution/warning preempts rotation on all displays and shows
  its page with the annunciator banner (bottom of the canvas; keep the bottom
  40 units of pages clear). Order: warning before caution, active before
  cleared, most recently raised first.
- Unacknowledged cue by display type: LCD/LED panels flash (≤ 1 Hz), the mirror
  pulses slowly, e-ink draws a static outline ring.
- The Status/annunciator page is the default/home page.

## Tooling and commands

Python packaging uses **Poetry**. Always run tools through Poetry.

```bash
poetry install                      # install deps (including dev group)
poetry run pytest                   # run tests
poetry run pytest --snapshot-update # update SVG snapshots (only when output change is intended)
poetry run ruff check .             # lint
poetry run ruff format .            # format
poetry run mypy src                 # type check
```

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
  (negative grid power = export), alert preemption ordering.
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

## Next milestone

- **Battery sign convention: negative battery power means discharging**
  (positive = charging). The example and test configs currently assume the
  opposite: flip the `battery_feed` line (or its points) so discharge flows
  battery → bus, fix the comments in `electrical.yaml`, and update the
  `sensor.battery_power` values in the state fixtures so each scenario keeps
  its meaning (e.g. islanded = discharging). Snapshot changes should be limited
  to the battery readout sign.
- **Unavailable becomes dotted everywhere** (lines, symbol outlines, tiles),
  replacing dashed. Update core rules 5 and 6 when this lands; every
  unavailable snapshot changes.
- **Line severity is shown by pattern, plus color where the palette has it:**
  solid = normal, dashed = caution, angle-striped (hatched) = warning,
  dotted = unavailable. Lines only; symbols keep weight/fill and tiles keep
  fill/ring. Constraints:
  - Stripes fill the casing interior; a warning line needs a minimum rendered
    width (force casing on if a style turned it off).
  - Rotate the hatch per segment so stripes always cross the line (a fixed
    45° pattern vanishes on 45° lines).
  - Hatch spacing is a theme value, to be tuned against panel pixels in the
    rasterization milestone.
  - Flow arrows stay solid on top of any pattern. No "marching dashes" flow
    animation (it would read as caution); animate chevrons if anything.
  - E-ink stops using stroke weight for *line* severity (`status_weight`
    applies to symbols only), so weight on lines is purely structural.
- **Connection styles:** named, relative line styles in `defs.yaml`: weight
  multiplier, casing, junction dots. Never color, and never a pattern (solid,
  dashed, hatched and dotted all carry status). **Casing is the default**;
  `casing: false` opts out. Per-element `weight` override. Resolution, last
  wins except where noted:
  1. the style's base properties;
  2. the style's per-theme variant in `defs.yaml`, keyed by theme name
     (`themes: {mirror: {weight: 1.5}}`): house-level YAML, usable now;
  3. later, per-display overrides by style name, when display configurations
     arrive with the server milestone;
  4. theme policies applied last and always honored: generic limits on
     properties, never on style names (e.g. `max_weight`, `casing: never`),
     so library themes stay independent of house configs.
- **Attach lines to symbols:** ports declared per symbol type in the registry,
  a `node` element for junctions (auto junction dots where 3+ lines meet),
  line endpoints as coordinates or `element.port`, `via` bend points.
- **Groups (containers):** a `group` element whose `layout` (grid now,
  adaptive modes later) positions `items`; children have no lines and connect
  implicitly to the group, which exposes ports like a symbol. Groups nest,
  keep their hierarchy through render (bottom-up: children, then derived
  channels such as `sum`/`count`, then frame/status/readouts), and frames are
  solid/dim/none only (patterns carry status). `tile_grid` becomes shorthand
  for a frameless group of tiles (status snapshots must stay identical). Lines
  may bind to another element's channel (e.g. `array.power`). Decided:
  - Child ids are scoped to their group and addressed as a path (`array.p3`).
  - Repetition is explicit: `item_defaults` plus a listed `items` entry per
    child. No range/template shorthand.
  - Lines may never connect to a child (e.g. `array.p3.right` is a load
    error); only the group's own ports are connectable.
  - Default group status (when the group has no rules): the worst caution or
    warning among its children; unavailable only if every child is
    unavailable. Rules on derived channels (e.g. `offline >= 2`) can raise it.

## Future work (not yet scheduled)

- Adaptive layout for annunciator tiles, so large alert sets don't need manual
  layout (in addition to, not replacing, manual positioning).
- Page rotation and dwell timers (server milestone; needs a clock loop).

## Open decisions (ask before settling)

- Web server framework and live-update mechanism (e.g. websocket push vs polling).
- PNG rasterization library for e-ink.
- **Panel profiles** (deferred to the rasterization milestone): the exact colors
  a panel can show and its dithering policy, used by rasterization to quantize.
  The color e-ink theme (Gruvbox light, mapped onto the panel's colors) and the
  choice of e-ink panel type (1-bit, grayscale or 6-color) come with it.
- How e-ink devices fetch images (pull a PNG URL vs push) and which firmware.
- Whether house-specific page configs live in this repo or a separate one.

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

| Target | Hardware | Rendering | Constraints |
|---|---|---|---|
| `tablet` | Rugged Android tablet (workshop), kiosk browser | Live SVG/HTML, interactive | Touch targets ≥ 48px, glove-friendly |
| `mirror` | Two-way mirror over a monitor, kiosk browser | Live SVG/HTML, auto-cycling | **Pure black background**, thin bright lines, no large light areas |
| `eink` | 10–13" e-paper panel (main floor) | Server-side snapshot → PNG pushed to device | No animation, limited palette (1-bit / grays / 6-color), refresh every 1–5 min, bezel buttons for page select |

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
  themes/      # Theme definitions (palette, stroke widths, fonts) per target
  render/      # Pure render functions: (page, state, theme, target) -> SVG string
               # plus rasterization to PNG for e-ink (quantize to panel palette)
  sources/     # State providers: HA websocket/REST client, static fixture source
  mfd/         # MFD behavior: page rotation, page selection, master-caution
               # preemption, alert acknowledgement
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
6. **Shared visual language across all targets:** green = normal, amber =
   caution, red = warning, cyan = flow/active, gray/dashed = unavailable. Keep
   symbol shapes identical across themes; only palette and weights change.

### MFD behavior

- Each display has a current page, a rotation list, and a dwell time.
- Alerts have severity (`advisory`, `caution`, `warning`). A caution/warning
  preempts rotation on all displays, shows the relevant page with an annunciator
  banner, and persists until acknowledged or cleared.
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

## Open decisions (ask before settling)

- Web server framework and live-update mechanism (e.g. websocket push vs polling).
- PNG rasterization library for e-ink.
- How e-ink devices fetch images (pull a PNG URL vs push) and which firmware.
- Whether house-specific page configs live in this repo or a separate one.

# Page definition format

Pages are YAML files. A config directory looks like this:

```
config/
  defs.yaml        # optional: shared thresholds, named conditions, staleness
  alerts.yaml      # optional: systems and alerts (see "Alerts" below)
  displays.yaml    # optional: physical displays (see "Displays" below)
  pages/
    electrical.yaml
    water.yaml
```

Files are parsed as YAML 1.2, so bare `on`, `off`, `yes` and `no` are strings,
not booleans. Unknown keys are errors. Every problem is reported with its file,
line and location, for example:

```
pages/electrical.yaml:23: elements[3].bind.voltage: unknown channel 'voltage' for breaker; expected: state
```

`examples/config/` is a complete working example.

## Page

```yaml
page: electrical             # page id, unique across the config
title: Electrical
canvas: {width: 1000, height: 600}   # logical units; scaled to each display
defs: {...}                  # optional page-local defs (same shape as defs.yaml)
elements: [...]
```

Page-local `defs` may not redefine a name from the shared `defs.yaml`.

## Elements

Every element has an `id` (unique on the page) and a `type`. The kinds are
symbols, lines, nodes, text, annunciator tiles and groups.

### Symbols

Any registered symbol type, centered at `at`:

```yaml
- id: battery
  type: battery
  at: [200, 300]
  orientation: horizontal    # or vertical; default horizontal
  name: BATT                 # or {text, anchor, offset}
  bind:
    level: sensor.battery_soc                     # shorthand
    power: {entity: sensor.battery, attribute: power}   # long form
  status: {...}
  readouts: [...]
  params: {...}              # type-specific settings
```

| Type | Channels (primary first) | Required | Params |
|---|---|---|---|
| `battery` | `level` (numeric, sets fill), `power` (numeric) | `level` | none |
| `breaker` | `state` | `state` | `closed`: states that mean closed, default `[on, closed]` |
| `solar_panel` | `power` (numeric) | `power` | none |
| `transfer_switch` | `state` | `state` | `connected`: states that mean grid-connected, default `[on, connected, grid, closed]` |
| `load_panel` | `power` (numeric) | none | none |
| `electric_meter` | `power` (numeric), `energy` (numeric) | none | `label`: up to 5 characters drawn inside, default `kWh` |
| `water_meter` | `flow` (numeric), `total` (numeric) | none | `label`, default `GAL` |
| `smart_breaker` | `state`, `power` (numeric) | `state` | `closed`, as for `breaker` |
| `ball_valve` | `state`, `position` (numeric) | `state` | `open`: states that mean open, default `[open, on]`; `moving`: default `[opening, closing]` |
| `globe_valve` | `state`, `position` (numeric) | `state` | as for `ball_valve` |
| `water_heater` | `temperature` (numeric), `heating` | none | `heating`: states that mean the burner is lit, default `[on, heating]` |
| `hose_bib` | `state` | none | `open`: states that mean running, default `[open, on]` |
| `faucet` | `state` | none | as for `hose_bib` |
| `combiner` | `power` (numeric) | none | `inputs`: number of branch circuits, 1 to 4, default 2 |

`transfer_switch` is a grid-isolating ATS, as used in whole-home battery
backup. Its grid contact faces left (top when vertical) and its load contact
right (bottom). The blade is closed to the grid when connected and swung open
when islanded.

Meters are a circle with their unit inside, read upright in either
orientation. Their `in` and `out` ports are on the left and right (top and
bottom when vertical). A meter's power follows the grid convention: negative
means export.

A `smart_breaker` is a remotely switched breaker, such as a battery system's
smart circuit: the breaker symbol plus a small actuator box below the
contact. Displays only show its state; they don't switch it.

A `combiner` joins branch circuits (such as microinverter strings) onto one
output. Each input runs through a small breaker mark to a bus bar. Its ports
are `in1` to `inN` spaced evenly down the left edge (across the top when
vertical, `in1` on the right) and `out` on the right (bottom).

Valves follow the P&ID convention: two triangles tip to tip, outlined when
open and filled when closed. While opening or closing, only the inlet
triangle is filled. Any state that isn't `open` or `moving` counts as closed.
A ball valve has a hollow circle at the tips, a globe valve a solid dot.
`in` is on the left (top when vertical) and `out` on the right (bottom).
`position` is for readouts, such as a percentage open.

A `water_heater` is a gas tank heater: a tall rounded tank with a burner
flame at its base, drawn solid while `heating` and outlined otherwise. Its
ports are `cold` (top, left of center), `hot` (top, right) and `gas` (left
side, by the burner). Home Assistant water heaters report temperature as an
attribute: `temperature: {entity: water_heater.tank, attribute: current_temperature}`.

A `hose_bib` (outdoor spigot: T handle, threaded spout) is fed through its
`in` port on the left; a `faucet` (gooseneck spout, side lever) through `in`
at the bottom. Neither needs a binding. Bind `state` to a smart valve and a
drop shows under the spout while it's open.

The primary channel decides the "no data" display: if it is bound but has no
usable value (or a non-numeric value on a numeric channel), the element is
drawn gray and dotted.

A binding can correct an entity's numbers as they're read:

```yaml
bind:
  power: {entity: sensor.grid_power, scale: -1}          # inverter reports export as positive
  level: {entity: sensor.battery_kw, scale: 1000, unit: W}  # kW sensor shown in W
```

`scale` multiplies numeric values; non-numeric states pass through unchanged.
`unit` replaces the entity's own unit after scaling. Status rules, flow arrows
and readouts all see the corrected value.

A channel can also bind to another element's channel by naming it
`element.channel`, for example `power: array.power` (a group's derived sum).
The part before the last dot must be a top-level symbol or group on the page.
Chains aren't allowed: the target channel can't itself be bound to an element.

### Lines

```yaml
- id: grid
  type: line
  from: [880, 300]           # a coordinate, a node id, or element.port
  to: main_breaker.out
  via: [[700, 250]]          # optional bend points (otherwise auto-routed)
  elbow: vertical-first      # optional: horizontal-first | vertical-first
  route: straight            # optional: allow a diagonal instead of an elbow
  casing: false              # optional: a plain line (default: a hollow pipe)
  bind: {power: sensor.grid_power}
  flow: true                 # or {from: power, threshold: 10}
  name: {text: GRID, along: 0, anchor: right}
  status: {...}
  readouts: [{value: power, format: power, abs: true}]
```

Instead of `from`/`to`/`via`, a line can give explicit `points: [[x, y], ...]`.

Lines are hollow pipes ("cased") by default; cased lines merge cleanly where
they meet. `casing: false` draws a plain line, for sensing and minor
connections. Widths come from the theme, so every pipe on a page is the same
width; color and pattern can't be set, because they carry the line's status.

#### Routing

A `from`/`to` line without `via` is routed automatically with at most one
elbow:
- **Aligned endpoints:** a straight line.
- **Otherwise:** one right-angle bend. The first leg leaves along the start
  port's outward direction; a `right` port goes horizontal first. If the start
  has no direction (a node or a coordinate), the last leg enters the end port
  head-on. If neither end has a direction, it goes horizontal first.

`elbow` forces which leg comes first, and `route: straight` draws a diagonal
instead. The flow arrow sits at the middle of the longest leg.

Lines have one channel, `power` (numeric, primary). With `flow`, a chevron is
drawn when `|power| > threshold`: positive flows from the first point toward the
last, negative flows backward (e.g. grid export). A flowing line with normal
status is drawn in the active color (Gruvbox blue).

#### Ports

An endpoint `element.port` attaches the line to an element:

- Every symbol, tile and group has edge and corner ports named like anchors:
  `top`, `bottom`, `left`, `right` and the corners (`top-left`, and so on).
  Edge midpoints sit on the element's own axis.
- Edge ports have an outward direction, which routing follows. Corners and
  nodes have none.
- Breakers add `in` and `out`, and transfer switches `grid` and `load`. Both
  follow the symbol's orientation.
- Nodes take no port: `to: bus`.
- Items inside a group can't be connected to; use the group's ports.

Endpoints resolve when the page loads, so a line can refer to elements defined
later in the file.

#### Severity patterns

A line shows its status by pattern as well as color, so it reads on displays
without color:

| Status | Pattern |
|---|---|
| normal, no flow | solid walls, blank (hollow) core |
| normal, flowing | **solid core** in the status color while \|power\| is above the flow threshold |
| caution | solid walls, **dashed core**, flowing or not (the arrow shows flow); a dashed stroke if uncased |
| warning | hatched: stripes fill the hollow, rotated to cross each segment; casing is forced on |
| unavailable | dotted |

### Nodes

A connection point that isn't equipment, such as a bus junction:

```yaml
- {id: bus, type: node, at: [500, 300]}
```

When three or more lines attach to a node, a junction dot is drawn on top of
them.

### Text

```yaml
- {id: title, type: text, at: [80, 40], text: ELEC, align: middle}   # start | middle | end
```

### Tiles

An annunciator tile shows one system from `alerts.yaml`. Tiles have a fixed
size (160 x 64) and are centered at `at`:

```yaml
- {id: grid_tile, type: tile, at: [224, 232], system: GRID, label: GRID TIE}   # label optional
```

`tile_grid` is shorthand for a frameless, unpadded group of tiles laid out row
by row from its top-left corner `at`. Tile ids are `<grid id>.<system>`:

```yaml
- id: annunciator
  type: tile_grid
  at: [144, 200]
  columns: 4
  gap: 24          # or [x, y]
  tiles: [GRID, BATT, WATER, LEAK, HVAC, NET, SEC, WX]
```

What a tile shows:

| State | Appearance |
|---|---|
| Dark | Nothing lit. |
| Lit | The worst active or latched severity in the system. Advisories light in the active color. |
| CLR | Every lit alert at that severity has cleared but is unacknowledged. |
| Attention cue | Shown while a caution or warning is unacknowledged: flash, pulse or ring, depending on the theme. |
| Unavailable | Dotted: every entity the system's alerts read has no data. |

### Alert log

The alert history, newest first, in a box (`at` is its top-left corner):

```yaml
- id: log
  type: alert_log
  at: [40, 56]
  size: [920, 480]
  systems: [GRID, BATT]      # optional: only these systems (default: all)
```

- **One row per change:** each raise, clear and acknowledgement of a caution
  or warning (RAISED, CLEARED, ACK and the display that acknowledged);
  advisories read START and END. An alert that stays raised adds nothing
  until it changes.
- **Flapping:** an alert raised again within 5 minutes of clearing folds into
  one FLAPPING xN row with its first raise time, until it stays clear or is
  acknowledged. A `for:` hold time on the alert stops most flapping at the
  source.
- **Batches:** a thin rule separates events more than a minute apart, so
  alerts raised together read as one block.
- **Home Assistant outages** show as CONNECTION LOST and RESTORED rows (only
  in logs without `systems`). Alerts are frozen while disconnected.
- **Paging:** rows that don't fit go on further pages. On a page with a log
  the middle keys are PG UP (older) and PG DN (newer); the header shows which
  rows are on screen. The log always reopens on its newest entries.
- Times are in the server's local time; the date shows where the day changes.

List the log page last in a display's `pages`: the home (alerts) page comes
first, so PREV from it lands on the log.

### Groups

A group lays out items inside itself. Items have no positions or connections of
their own: they connect through the group, which has ports like a symbol.

```yaml
- id: array
  type: group
  at: [348, 30]                      # top-left of the group's box
  layout: {grid: {columns: 6, gap: 8, padding: 12}}
  frame: outline                     # or none
  name: {text: SOLAR, anchor: left}
  channels:                          # derived from the items
    power: {sum: power}              # sum | min | max of an item channel
    offline: {count: unavailable}    # count of items in a status
  status:
    rules: [{level: caution, when: [{channel: offline, ge: 2}]}]
  readouts: [{value: power, format: power}]
  item_defaults: {type: solar_panel}  # merged into every item
  items:
    - {id: p1, bind: {power: sensor.pv_p1_power}}
    - {id: p2, bind: {power: sensor.pv_p2_power}}
```

- **Items** can be symbols, tiles or nested groups, and each one is listed
  explicitly. Item ids are scoped to the group, so `p1` becomes `array.p1`. An
  item can't set `at`.
- **Layout:** cells are the size of the largest item, and each item is centered
  in its cell. `padding` is the space between the frame and the cells.
- **Derived channels** work in rules and readouts like any other channel. Items
  without usable data are left out of `sum`, `min` and `max`.
- **Status:** without rules, a group takes its items' worst caution or warning.
  It's unavailable only when every item is unavailable. Rules on derived
  channels can raise it, for example "caution when 2 or more panels are
  offline".
- **Frame:** dim when the group is normal, in the status color otherwise, and
  dotted when unavailable.

## Names and readouts

```yaml
name: {text: BATT, anchor: top, offset: [0, -2]}
readouts:
  - {value: level, format: percent, anchor: bottom}
  - {value: power, format: power}
  - {value: temp, format: "{:.1f} °C"}
```

- `value` is a channel name, and it must be bound.
- `format` is one of the named formatters, or a Python format string applied
  to the number:
  - `power`: W below 1000 and kW above; kW input is normalized
  - `percent`
  - `number`: up to 2 decimals plus the unit
  - `raw`: the state string as-is
- `unit` overrides the entity's `unit_of_measurement`.
- `abs: true` shows the magnitude, for use when a flow arrow shows direction.
- Missing or non-numeric data shows `---`.

Names use the theme's label font and text color. Readouts use the element's
status color.

### Anchors

Nine positions around the element's bounding box:

```
  top-left        top-center         top-right
             ┌──────────────────┐
 center-left │      center      │ center-right
             └──────────────────┘
 bottom-left     bottom-center      bottom-right
```

Aliases: `top`, `bottom`, `left`, `right` (the edge centers) and `middle` (the
same as `center`).

- **Columns** set horizontal alignment so text grows away from the symbol: text
  in the left column ends at the anchor, the center column is centered, and text
  in the right column starts at the anchor.
- **Rows** set vertical placement: top-row text sits above the box, bottom-row
  text hangs below it, and center-row text is vertically centered on the anchor.
- **Stacking:** several labels at one anchor stack away from the box, in the
  order they are listed.
- **Offset:** `offset: [dx, dy]` nudges a single label.

Defaults:
- On symbols, the name goes `top` and readouts go `bottom`.
- On lines, labels attach to a point on the path at `along` (0 = first point,
  1 = last, default 0.5). They go `top` on mostly-horizontal segments and
  `right` on mostly-vertical ones.

## Status

The rules below decide the element's status (normal, caution, warning):

```yaml
status:
  from: level                # channel for thresholds/map; default: the primary
  thresholds: battery_soc    # a defs name, or {warning_low, caution_low, caution_high, warning_high}
  map: {on: normal, off: caution}
  default: caution           # level for states not in `map` (only with map; default normal)
  systems: [GRID]            # also take the worst *active* alert of these systems
  alerts: [battery_low]      # ...and of these alerts
  rules:
    - level: warning
      any:                   # OR of the items below
        - all:               # AND-group
            - {channel: state, eq: off}
            - {use: grid_lost}
        - {channel: state, eq: tripped}
    - level: caution
      when:                  # shorthand for a single AND-group
        - {entity: sensor.grid_voltage, lt: 210}
```

Thresholds use "at or beyond": a value equal to a limit takes that limit's
level, and warning limits win over caution limits.

**How the result is chosen:**
1. The most severe of the matching rules and the referenced active alerts
   wins. This includes the rules generated by `thresholds` and `map`. Latched
   alerts don't count: an element shows the equipment's current state, while the
   latch shows on the annunciator.
2. If nothing matches and the primary channel has no data, the element is
   *unavailable* (gray, dotted).
3. Otherwise it is *normal*.

An explicit rule about missing data therefore beats the gray display.

### Conditions

Rules are in **disjunctive normal form**: `any` is a list whose items are
single conditions, `{use: name}`, or `{all: [...]}` groups. `when` is one
AND-group. An `all` group cannot appear inside another `all` group or inside
`when`.

A condition reads one value and applies exactly one predicate to it.

The value comes from one of:
- `channel: <name>`: one of this element's bound channels.
- `entity: <entity_id>`, with an optional `attribute: <name>`: any entity.

Predicates:

| Predicate | Example | Meaning |
|---|---|---|
| `eq`, `ne` | `{channel: state, eq: off}` | Equal or not equal. Numeric if both sides are numbers, otherwise case-insensitive text |
| `in`, `not_in` | `{channel: state, in: [off, tripped]}` | Membership in a list |
| `lt`, `le`, `gt`, `ge` | `{entity: sensor.soc, lt: 20}` | Numeric comparison |
| `between` | `{channel: power, between: [-50, 50]}` | Inclusive range |
| `unavailable` | `{entity: sensor.grid_power, unavailable: true}` | No usable data, or with `false`, has data |

Every predicate except `unavailable` is **false** when the value is missing.
A rule therefore never fires because of a dead sensor unless it asks about
availability.

## Defs

```yaml
stale_after:                 # house-wide; only in defs.yaml, not page-local defs
  default: 15m               # 90, "90s", "15m", "1h"
  entities:
    sensor.wind_speed: 1h

thresholds:
  battery_soc: {warning_low: 10, caution_low: 25}

conditions:
  grid_lost:
    when: [{entity: sensor.grid_power, unavailable: true}]
  grid_weak:
    any:
      - {use: grid_lost}
      - {entity: sensor.grid_voltage, lt: 210}
```

An entity that Home Assistant hasn't heard from for longer than its
`stale_after` limit is treated as unavailable (dotted), so the page never shows
an old value as if it were current. Entities without a limit never go stale.

Named conditions use the same `any` and `when` forms as rules. They may `use`
each other; cycles are errors.

A named condition used inside an AND-group is distributed back into DNF.
`all: [A, {use: X}]` where `X` is `B or C` becomes `(A and B) or (A and C)`.

Named conditions can refer to `channel:` values. Those channels are checked
where the condition is used, so they must be bound on every element that uses
it.

## Alerts

`alerts.yaml` declares the house's systems (one annunciator tile each) and the
alerts grouped under them:

```yaml
systems:
  GRID: {label: GRID}
  BATT: {label: BATT}

alerts:
  - id: grid_lost
    severity: warning          # advisory | caution | warning
    system: GRID
    page: electrical           # optional: the page the alert relates to
    message: GRID POWER LOST
    when: [{use: grid_lost}]   # same any/when forms as status rules
  - id: exporting
    severity: advisory
    system: GRID
    message: EXPORTING TO GRID
    for: 1m                    # optional hold time, like 30, "30s", "5m"
    when: [{entity: sensor.grid_power, lt: -1000}]
```

- **Hold time:** with `for:`, an alert is raised only once its condition has
  held that long, and clears only once it has stopped holding that long. A
  blip in between restarts the wait, so a reading hovering at a threshold
  doesn't raise and clear over and over. Conditions are checked on every
  change and at least every 30 seconds, so a hold can run up to 30 seconds
  long. The alert's raise time is when the hold ran out.
- An alert is raised while its condition holds. Conditions can only refer to
  `entity:` values, because alerts have no channels. They can `use` named
  conditions from `defs.yaml`, but only ones that also refer to entities.
- `page` is optional. Alerts never switch a display's page.
- Cautions and warnings **latch**: they stay raised until someone acknowledges
  them, even after the condition clears. Advisories clear on their own.
- One acknowledgement covers the whole house.
- `system` must be declared under `systems`, and `page`, if given, must be one
  of the loaded pages.
- While any caution or warning is unacknowledged, an annunciator banner naming
  the most urgent one shows along the bottom 40 units of whatever page is
  displayed, so keep that strip clear on every page.

## Displays

`displays.yaml` lists the physical displays the server drives:

```yaml
displays:
  workshop:
    theme: lcd                 # lcd | mirror | eink_mono | eink_color
    size: [1280, 800]          # pixels
    home: status               # shown at startup
    pages: [status, electrical]   # what a viewer can select
    controls: soft             # soft keys; default: soft when there is more than one page
    alerts_page: status        # where the ALERTS key goes; default: home
  hallway:
    theme: mirror
    size: [1920, 1080]
    home: electrical           # no 'pages': fixed to its home page
  main_floor:
    theme: eink_mono
    size: [800, 480]           # the panel's own resolution
    home: status
    pages: [status, electrical]
    panel: mono                # e-paper: served as PNG snapshots
```

A display shows one page at a time and stays on it until a viewer selects
another. Pages are never cycled automatically, and alerts never switch pages;
the annunciator banner overlays whatever page is showing. `home` (and
`alerts_page`) are always selectable.

### Soft keys

With `controls: soft`, four keys share the bottom 40-unit strip with the
banner, so they cost no page space. Like the bezel keys of an MFD, keys are
positions (1 to 4, left to right) whose labels change with the page:

```
alerts page:    [◀ PREV][ ACK ]    banner   [ LOCK  ][NEXT ▶]
log pages:      [◀ PREV][▲ PG UP]  banner   [▼ PG DN][NEXT ▶]
other pages:    [◀ PREV][ALERTS]   banner   [ LOCK  ][NEXT ▶]
```

| Key | What it does |
|---|---|
| PREV / NEXT | Step through `pages` in order, wrapping around. Always keys 1 and 4, so every page can be left. |
| ALERTS | Jumps to `alerts_page`. It lights in the alert's color, with the attention cue, while a caution or warning is unacknowledged. |
| ACK | On the alerts page, in place of ALERTS: acknowledges the alert the banner names, one per press. Lit like ALERTS. |
| LOCK | Toggles the lock. While locked, every key except LOCK (and every tap) is ignored, enforced by the server, and the key reads LOCKED. |
| PG UP / PG DN | On a page with an alert log: older and newer entries. |

Lock state isn't saved, so displays start unlocked. A locked display can't
change pages, so it never reaches a page without LOCK. Besides ACK, alerts
can be acknowledged by tapping the banner or a tile.

### E-paper panels

A display with a `panel` is an e-paper device that fetches PNG snapshots
instead of a live page (see `docs/running.md`). The PNG is the display's
`size` and uses only the panel's colors, without dithering:

| Panel | Colors | Theme |
|---|---|---|
| `mono` | black, white | `eink_mono` |
| `gray4` | 4 grays | `eink_mono` |
| `gray16` | 16 grays | `eink_mono` |
| `spectra6` | black, white, red, yellow, blue, green | `eink_mono` or `eink_color` |

The theme must draw only colors the panel can show; `mfdhome check` reports
anything else. `eink_color` uses the six inks directly: green normal, yellow
caution, red warning, blue active, black dotted for no data. A page whose
proportions differ from the panel's is centered, with margins in the
background color.

The soft-key labels are still drawn along the bottom strip when the display
has more than one page, so hardware buttons mounted beneath them are
labelled.

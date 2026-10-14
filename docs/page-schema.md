# Page definition format

Pages are YAML files. A config directory looks like this:

```
config/
  defs.yaml        # optional: shared thresholds and named conditions
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

Every element has an `id` (unique on the page) and a `type`. There are three
kinds.

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

The primary channel decides the "no data" display: if it is bound but has no
usable value (or a non-numeric value on a numeric channel), the element is
drawn gray and dashed.

### Lines

```yaml
- id: grid
  type: line
  points: [[880, 300], [670, 300]]
  bind: {power: sensor.grid_power}
  flow: true                 # or {from: power, threshold: 10}
  name: {text: GRID, along: 0, anchor: right}
  status: {...}
  readouts: [{value: power, format: power, abs: true}]
```

Lines have one channel, `power` (numeric, primary). With `flow`, a chevron is
drawn when `|power| > threshold`: positive flows from the first point toward the
last, negative flows backward (e.g. grid export). A flowing line with normal
status is drawn cyan.

### Text

```yaml
- {id: title, type: text, at: [80, 40], text: ELEC, align: middle}   # start | middle | end
```

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
1. The most severe matching rule wins, including the rules generated by
   `thresholds` and `map`.
2. If nothing matches and the primary channel has no data, the element is
   *unavailable* (gray, dashed).
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

Named conditions use the same `any` and `when` forms as rules. They may `use`
each other; cycles are errors.

A named condition used inside an AND-group is distributed back into DNF.
`all: [A, {use: X}]` where `X` is `B or C` becomes `(A and B) or (A and C)`.

Named conditions can refer to `channel:` values. Those channels are checked
where the condition is used, so they must be bound on every element that uses
it.

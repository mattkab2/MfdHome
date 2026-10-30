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
| `load_panel` | `power` (numeric) | none | none; ports `l1`-`l4` and `r1`-`r4` at its breakers |
| `electric_meter` | `power` (numeric), `energy` (numeric) | none | `label`: up to 5 characters drawn inside, default `kWh` |
| `water_meter` | `flow` (numeric), `total` (numeric) | none | `label`, default `GAL` |
| `smart_breaker` | `state`, `power` (numeric) | `state` | `closed`, as for `breaker` |
| `ball_valve` | `state`, `position` (numeric) | `state` | `open`: states that mean open, default `[open, on]`; `moving`: default `[opening, closing]`; `actuated`: true for a motorized or solenoid valve |
| `globe_valve` | `state`, `position` (numeric) | `state` | as for `ball_valve` |
| `check_valve` | `state` | none | none |
| `backflow_preventer` | `state` | none | none |
| `prv` | `pressure` (numeric) | none | none |
| `gas_meter` | `flow` (numeric), `total` (numeric) | none | `label`, default `CCF` |
| `tank` | `state` | none | `tag`: up to 4 characters (`SOFT`, `FILT`, `EXP`); `connections`: `top` (default), `sides` or `bottom` |
| `pump` | `state`, `power` (numeric) | none | `running`: states that mean running, default `[on, running]` |
| `water_heater` | `temperature` (numeric), `heating` | none | `heating`: states that mean the burner is lit, default `[on, heating]` |
| `outlet` | `state` | none | `label`: up to 5 characters, default `OUT`; `outdoor`: true doubles the back edge; `inlets`: 1 (default) or 2 for hot and cold; `facing`: `right` (default) or `left` |
| `sensor` | `state` | none | `code`: up to 3 characters drawn inside (`W`, `S`, `CO`, ...); `active`: states that mean tripped, default `[on]` |
| `gauge` | `value` (numeric) | `value` | `format`: a named format or format string, default `number`; `unit`: replaces the entity's unit |
| `furnace` | `action` | none | `coil`: true adds an AC coil; `heating`: actions that light the burner, default `[heating, on]`; `cooling`: actions that chill the coil, default `[cooling]`; `blowing`: actions that run the blower, default `[heating, cooling, fan, on]` |
| `air_handler` | `action` | none | as for `furnace` (no burner); `coil` defaults to true |
| `condenser` | `action` | none | `running`: actions that run the compressor, default `[cooling, on]` |
| `damper` | `state`, `position` (numeric) | `state` | as for `ball_valve` (`open`, `moving`, `actuated`) |
| `thermostat` | `temperature` (numeric), `setpoint` (numeric), `action` | `temperature` | `format`: for both temperatures, default `{:.0f}°` |
| `opening` | `state` | none | `kind`: `door` (default), `window` or `overhead`; `length` (default 36); `swing`: `up`/`left` or `down`/`right`; `hinge`: `start` or `end`; `angle`: degrees, for a diagonal wall; `open`: states that mean open, default `[on, open]` |
| `stairs` | none | none | `length` along the run (default 100); `width` (default 30); `treads` (default one per 10); `up`: `end` (default) or `start` |
| `alarm_panel` | `state` | `state` | none |
| `combiner` | `power` (numeric) | none | `inputs`: number of branch circuits, 1 to 4, default 2 |
| `router` | `state`, `cpu`, `memory`, `temperature` (numeric) | none | `lan`: LAN port numbers to break out, ports `lan<n>` down its right edge; `wan`: the WAN port's number, port `wan` on its left edge |
| `network_switch` | as for `router` | none | none |
| `access_point` | as for `router`, plus `clients` (numeric) | none | none |
| `host` | as for `router` | none | none |
| `radio` | `state`, `rssi`, `snr`, `noise_floor`, `hops`, `battery` (numeric) | none | none |

A `load_panel` has a port at each breaker it draws (`l1` to `l4` down the
left side, `r1` to `r4` down the right), so a circuit can leave from its own
breaker.

A `router` can break out its LAN ports: `params: {lan: [1, 2, 3, 4, 6, 7]}`
lists them top to bottom down its right edge, each a numbered square with a
port (`gateway.lan3`), and the router grows taller to fit. `wan: 5` adds the
WAN port the same way, centered on its left edge (port `gateway.wan`). Each device on the
gateway then gets its own line instead of sharing a junction; give unused
ports a place in the list and simply leave them unconnected.

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
`position` is for readouts, such as a percentage open. `actuated: true` adds
the actuator mark above the body (a smart shutoff, an irrigation zone), as on
a smart breaker; the element's box grows to include it, so labels stay clear.

Inline fittings are self-acting, so they need no binding: a `check_valve` (a
triangle pointing downstream with a seat bar), a `backflow_preventer` (two
checks in series in a box) and a `prv`, a pressure reducing valve (a valve
body with a spring dome above; bind `pressure` to show the downstream
pressure). All run `in` to `out`, left to right or top to bottom.

A `tank` is a vessel such as a water softener, filter or expansion tank,
tagged inside. Its `connections` are `in` and `out` on top (`top`, the
default), `in` on the left and `out` on the right (`sides`, an inline
filter), or a single `port` underneath (`bottom`, an expansion tank). A
`pump` (a circle with a triangle pointing downstream, filled while running)
runs `in` to `out`. A `gas_meter` is the meter circle labelled `CCF`.

A `water_heater` is a gas tank heater: a tall rounded tank with a burner
flame at its base, drawn solid while `heating` and outlined otherwise. Its
ports are `cold` (top, left of center), `hot` (top, right) and `gas` (left
side, by the burner). Home Assistant water heaters report temperature as an
attribute: `temperature: {entity: water_heater.tank, attribute: current_temperature}`.

An `outlet` is a point of use (a sink, a hose bib), drawn the P&ID way: a
terminal flag with a short tag inside (`label: SINK`, `HB`, ...), its flat
back flush with the pipe that feeds it through `in`. `outdoor: true` doubles
that back edge, the wall the pipe passes through. `inlets: 2` (a sink) swaps
`in` for `cold` (upper) and `hot` (lower) on the back, so a water heater's
cold inlet and hot outlet reach it without the pipes crossing. Outlets are
always horizontal, fed from the left with the flag pointing right;
`facing: left` mirrors one, fed from the right. Outlets also end lines that
leave the page's subject, such as a circuit to an outdoor condenser. No
binding is needed; `state` is there for status rules (the line feeding the
outlet shows whether water flows).

Network devices are abstract boxes told apart by a mark inside or above:
a `router` (a gateway) has a circle crossed by four routes, a
`network_switch` a row of ports, an `access_point` Wi-Fi arcs rising from a
flat body, a `host` (a server, such as the one running Home Assistant)
stacked drive bays, and a `radio` (a LoRa node, such as a MeshCore companion
or repeater) an antenna mast topped by the schematic antenna, an inverted
triangle. They draw nothing from their state: bind `state` (a UniFi device
state, a node's online sensor) for status rules, usually a named map, and
the numeric channels for readouts. `hops` is how many repeaters a radio's
messages pass through (0: heard directly). Only the outline takes the status
weight; the marks inside keep theirs, so they stay legible on e-paper. The
access point's arcs and the radio's mast stand above the body, inside the
element's box, and their side ports are level with the body.

Point sensors come in two kinds. A `sensor` is an on/off detector (leak,
smoke, CO, gas, motion): a small diamond, so it can't be mistaken for a meter,
with a short code inside, drawn filled while tripped. A `gauge` shows a
reading (a room temperature, a pressure) inside a small box. Both take status
rules like any symbol, so a wet leak sensor can be a warning:

```yaml
- {id: leak_basement, type: sensor, at: [640, 520], params: {code: W},
   bind: {state: binary_sensor.leak_basement}, status: {map: {"on": warning}}}
- {id: pressure, type: gauge, at: [230, 310], params: {format: "{:.0f} psi"},
   bind: {value: sensor.water_pressure}}
```

The primary channel decides the "no data" display: if it is bound but has no
usable value (or a non-numeric value on a numeric channel), the element is
drawn gray and dotted.

A binding can correct an entity's numbers as they're read:

```yaml
bind:
  rate: {entity: sensor.grid_power, scale: -1}           # inverter reports export as positive
  level: {entity: sensor.battery_kw, scale: 1000, unit: W}  # kW sensor shown in W
```

`scale` multiplies numeric values; non-numeric states pass through unchanged.
`unit` replaces the entity's own unit after scaling. Status rules, flow arrows
and readouts all see the corrected value.

A channel can also bind to another element's channel by naming it
`element.channel`, for example `rate: array.power` (a group's derived sum).
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
  tag: HW                    # optional: what it carries, or {text: HW, along: 0.7}
  bind: {rate: sensor.grid_power}
  flow: {threshold: 10}      # or just 'true' (threshold 0: any nonzero rate), or a condition
  name: {text: GRID, along: 0, anchor: right}
  status: {...}
  readouts: [{value: rate, format: power, abs: true}]
```

A line always runs `from` one endpoint `to` another. Give `via` points for an
exact polyline; endpoints can be plain coordinates.

Lines are hollow pipes ("cased") by default; cased lines merge cleanly where
they meet. `casing: false` draws a plain line, for sensing and minor
connections. Widths come from the theme, so every pipe on a page is the same
width; color and pattern can't be set, because they carry the line's status.

A `tag` (up to 4 characters: `CW`, `HW`, `GAS`, `SA`, `RA`) names what the
line carries, the way a P&ID labels its lines, since color can't: it's
reserved for status. It's drawn as a small plate on the line, a quarter of
the way along unless `along` says otherwise, in the line's status color.

#### Routing

A `from`/`to` line without `via` is routed automatically with at most one
elbow:
- **Aligned endpoints:** a straight line.
- **Otherwise:** one right-angle bend. The first leg leaves along the start
  port's outward direction; a `right` port goes horizontal first. If the start
  has no direction (a node or a coordinate), the last leg enters the end port
  head-on. If neither end has a direction, it goes horizontal first.

`elbow` forces which leg comes first, and `route: straight` draws a diagonal
instead.

Lines have three channels. `rate` (numeric, primary) is whatever the line carries,
such as power in W, water flow in gal/min or throughput in Mbps. With `flow`,
an arrow is drawn when `|rate| > threshold` (default 0, so any nonzero rate;
set a threshold for noisy sensors, such as power hovering around zero):
positive flows from the first point toward the last, negative flows backward
(e.g. grid export). A flowing
line with normal status is drawn in the active color (Gruvbox blue).

Where there's nothing to measure (an air duct, a gas line, an irrigation
pipe), flow can come from a condition instead, written like a status rule's
`when` or `any`: the line flows from its first point toward its last while
the condition holds. `reverse: true` flips the direction (for a rate too).
There's no rate, so there's nothing to read out.

```yaml
- id: supply_1
  type: line
  from: furnace.supply
  to: trunk
  flow:
    when: [{entity: climate.main, attribute: hvac_action, in: [heating, cooling, fan]}]
```

A line that physically can't carry anything at times (a feeder whose relay
is open) can gate flow from its rate with `while`, written like `when`: no
flow while it fails, whatever the rate reads. The rate still sets direction
and readouts. This matters on averaging displays, where a reading taken just
before a grid outage can keep the 5-minute average above the threshold after
the relay has opened. The condition is judged on live states.

```yaml
- id: grid
  type: line
  bind: {rate: sensor.grid_power}
  flow:
    threshold: 10
    while: [{entity: binary_sensor.grid_connected, eq: "on"}]
```

`rate_back` (numeric) makes a line two-way, for links that report each
direction separately: a network port's download and upload, or a grid feed's
import and export as two positive sensors. Each rate is then a magnitude in
its own direction (`rate` from the first point toward the last, `rate_back`
the other way), with its own harpoon: the forward one on the side of the
line's first `rate` readout (by default above horizontal lines, right of
vertical ones), the backward one on the other side. Readouts of `rate_back`
default to that other side, and a two-way line's labels sit clear of both
harpoons. The core is solid while either direction flows; the `threshold`
applies to both, and `reverse` swaps them. A condition can't drive a two-way
line.

```yaml
- id: to_core
  type: line
  from: lan
  to: core_switch.left
  bind: {rate: sensor.core_switch_port_1_rx, rate_back: sensor.core_switch_port_1_tx}
  flow: {threshold: 1}
  readouts:
    - {value: rate, format: data_rate}        # above, over the download harpoon
    - {value: rate_back, format: data_rate}   # below, under the upload harpoon
```

`state` is the link's own state, for a line whose health can be read but
not measured, such as a radio link's reachability or the device at the far
end of a cable. A line with only `state` bound takes it as its primary
channel, so `map` reads it and a link with no data is drawn gray and dotted.
Beside a `rate`, give `from: state` to map it:

```yaml
- id: rf
  type: line
  from: radio.right
  to: repeater.left
  casing: false
  tag: RF
  bind: {state: binary_sensor.repeater_online}
  status: {map: {"on": normal, "off": caution}}
```

The arrow is a harpoon (⇀) beside the line: a shaft parallel to it, set off
from its edge, with a half-arrowhead flaring away from the line at the
downstream end. It never covers the line's core, so the status patterns
always show in full. It sits level with the line's first readout, on the
other side of the line (below horizontal lines and left of vertical ones for
default readout positions), sliding along the leg if needed so it never wraps
a bend. A line without readouts gets it in the other half from its tag, or
at the middle of its longest leg.

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
| normal, flowing | **solid core** in the status color while \|rate\| is above the flow threshold |
| caution | solid walls, **dashed core**, flowing or not (the arrow shows flow); long dashes if uncased, so they never read as dots |
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
- **Logged state changes** (see "Logged state changes" below) appear as
  information rows under their system, such as the alarm panel arming.
- **Paging:** rows that don't fit go on further pages. On a page with a log
  the middle keys are PG UP (older) and PG DN (newer); the header shows which
  rows are on screen. The log always reopens on its newest entries.
- Times are in the server's local time; the date shows where the day changes.

List the log page last in a display's `pages`: the home (alerts) page comes
first, so PREV from it lands on the log.

### HVAC

An `air_handler` is a cabinet with an AC evaporator coil on top and its
blower (a fan); a `furnace` is one with a gas burner (a flame) at the bottom,
and a coil only with `coil: true`. Bind `action` to the thermostat's
`hvac_action` attribute: the coil is filled while cooling, the fan while the
blower runs and the flame while heating. Ports: `supply` (top), `return`
(left, at the blower), `refrigerant` (right, at the coil) and `gas` (right,
at the burner), each only where the cabinet has that section. A `condenser`
is the outdoor AC unit, its fan seen from above, filled while the compressor
runs; its `refrigerant` port faces the air handler (a plain line tagged
`REF`). A `damper` is a blade on a
pivot in a duct: along the flow when open, across it when closed, diagonal
while moving; `actuated: true` marks a motorized zone damper. A `thermostat`
shows the room temperature, the setpoint and what it's doing (HEAT, IDLE,
FAN, ...), in the active color while equipment runs:

```yaml
- id: upstairs
  type: thermostat
  at: [920, 110]
  bind:
    temperature: {entity: climate.upstairs, attribute: current_temperature}
    setpoint: {entity: climate.upstairs, attribute: temperature}
    action: {entity: climate.upstairs, attribute: hvac_action}
  status: {alerts: [upstairs_below_setpoint]}
```

Room temperatures fit in a group of gauges whose format carries the room
(`format: "BD1 {:.0f}°"`), so a floor reads as one framed panel that takes
its coldest room's caution. Ducts are lines tagged `SA` and `RA`.

### Floorplans

A floorplan page (a security page, say) is drawn from the same elements as
any other page, plus rooms and walls. Structure is drawn in the theme's
structure color so it recedes; only things that report take status colors.

```yaml
- {id: living, type: room, name: LIVING, points: [[80, 80], [420, 80], [420, 300], [80, 300]]}
- {id: exterior, type: wall, exterior: true, points: [[80, 80], [760, 80], [760, 520], [80, 520], [80, 80]]}
- id: front_door
  type: opening
  at: [80, 330]                      # the middle of the opening, on the wall
  orientation: vertical              # along the wall
  params: {kind: door, length: 44, swing: right}
  bind: {state: binary_sensor.front_door}
  status:
    rules: [{level: caution, when: [{channel: state, eq: "on"}, {use: armed}]}]
- id: panel
  type: alarm_panel
  at: [880, 110]
  bind: {state: alarm_control_panel.house}
  status: {map: {triggered: warning, pending: caution, arming: caution}, default: normal}
```

- **`room`**: a polygon with a `name` (placed in the middle, or at
  `label_at`). Rooms have no channels; their `status` can use entity rules
  and alerts (for example a room with smoke), and then the outline takes the
  status color.
- **`wall`**: a static polyline; `exterior: true` draws it heavier.
- **`opening`**: a door or window in a wall, bound to a contact sensor. The
  wall is cut under it and its ends marked. A closed door is a leaf across
  the gap; an open one swings 90 degrees toward `swing` around its `hinge`
  end, with the swing arc. A closed window is a double line; an open one
  is a bare gap between brackets at its jambs. An `overhead` door (a garage door) is a panel
  across the gap; open, the gap is clear and the panel shows lifted overhead
  on the `swing` side, a box reaching into the room. On a
  diagonal wall, `angle` turns the opening (degrees, clockwise from pointing
  right; `orientation` is then ignored), and its sides turn with it: at 45
  the wall runs down-right and `down` is down-left of it. Its box includes
  the door's swing.
- **`stairs`**: a flight drawn as structure (never a status color): its
  outline, a line at each tread and an arrow pointing up the flight. It runs
  along its `orientation`; `up: start` points the arrow to the top (or left)
  end.
- **`alarm_panel`**: the panel's state in words (DISARMED, ARMED AWAY, ENTRY
  DELAY, TRIGGERED, ...), drawn in the active color while armed; status rules
  make it a caution or warning.
- Point sensors (motion `M`, smoke `S`, glass break `GB`, ...) are `sensor`
  symbols. Displays only show the system: they never arm, disarm or silence
  it.

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

### Enclosures

An enclosure frames elements that share a cabinet, such as a battery gateway's
grid relay and smart-circuit relays. Unlike a group's items, its members stay
ordinary elements: each is placed with its own `at` and keeps its own
connections, which cross the frame.

```yaml
- id: agate
  type: enclosure
  contains: [grid_relay, ac_main, ac_aux]   # top-level symbols, groups, tiles or nodes
  padding: 12                               # frame to the members' boxes (default 12)
  name: AGATE                               # above the frame by default
```

- The frame is sized at load time to its members' boxes plus `padding`.
- Its status is its members' worst caution or warning, unavailable only when
  every member is. While normal the frame is in the structure color (like
  floorplan walls, so it shows on paper too); otherwise it's drawn like a
  group's frame, in the status color.
- It has no channels or ports: lines connect to the members inside it. Pipes
  are drawn over the frame where they cross it.

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
  - `data_rate`: bits per second, scaled to b/s, kb/s, Mb/s or Gb/s; any of Home
    Assistant's data rate units is converted (no unit: Mbit/s)
  - `percent`
  - `number`: up to 2 decimals plus the unit
  - `raw`: the state string as-is
- `unit` overrides the entity's `unit_of_measurement`.
- `abs: true` shows the magnitude, for use when a flow arrow shows direction.
- `with_flow: true` (line readouts) shows the value only while its direction's
  flow arrow is drawn: a `rate_back` readout with the backward arrow, any other
  with the forward one. Busy pages (the network) then label only what moves.
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
  map: {on: normal, off: caution}   # or a defs name
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

The numeric comparisons (`lt`, `le`, `gt`, `ge`) can also compare against
another value, plus an optional `offset`, written the same way as the value
itself:

```yaml
# A room more than 3 degrees below its thermostat's setpoint:
- entity: sensor.bedroom_temperature
  lt: {entity: climate.upstairs, attribute: temperature, offset: -3}
# On an element, against another of its channels:
- {channel: pressure, lt: {channel: prv_setting}}
```

Every predicate except `unavailable` is **false** when the value is missing,
including the value it's compared against. A rule therefore never fires
because of a dead sensor unless it asks about availability.

## Defs

```yaml
averaging:                   # house-wide; see "Displays"
  entities: {sensor.battery_soc: false}

stale_after:                 # house-wide; only in defs.yaml, not page-local defs
  default: 15m               # 90, "90s", "15m", "1h"
  entities:
    sensor.wind_speed: 1h

thresholds:
  battery_soc: {warning_low: 10, caution_low: 25}

maps:                        # named state maps, for 'map: unifi_device'
  unifi_device:
    states: {connected: normal, disconnected: warning}
    default: caution         # any other state; an element's own 'default' wins

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
    message: GRID POWER LOST
    when: [{use: grid_lost}]   # same any/when forms as status rules
  - id: exporting
    severity: advisory
    system: GRID
    message: EXPORTING TO GRID
    for: 1m                    # optional hold time, like 30, "30s", "5m"
    life_safety: false         # true: named first among alerts of its severity
    when: [{entity: sensor.grid_power, lt: -1000}]
```

- **Hold time:** with `for:`, an alert is raised only once its condition has
  held that long, and clears only once it has stopped holding that long. A
  blip in between restarts the wait, so a reading hovering at a threshold
  doesn't raise and clear over and over. Conditions are checked on every
  change and at least every 30 seconds, so a hold can run up to 30 seconds
  long. The alert's raise time is when the hold ran out.
- **Life safety:** `life_safety: true` (smoke, CO, gas, a triggered alarm)
  puts an alert first among alerts of its severity, so the banner and the ACK
  key name it before anything else. Severity still comes first.
- An alert is raised while its condition holds. Conditions can only refer to
  `entity:` values, because alerts have no channels. They can `use` named
  conditions from `defs.yaml`, but only ones that also refer to entities.
- Alerts never switch a display's page.
- Cautions and warnings **latch**: they stay raised until someone acknowledges
  them, even after the condition clears. Advisories clear on their own.
- One acknowledgement covers the whole house.
- `system` must be declared under `systems`.
- While any caution or warning is unacknowledged, an annunciator banner naming
  the most urgent one shows along the bottom 40 units of whatever page is
  displayed, so keep that strip clear on every page.

### Logged state changes

Some changes aren't alerts but belong beside them in the log, such as
arming and disarming. List those entities under `log` in `alerts.yaml`:

```yaml
log:
  - {entity: alarm_control_panel.house, label: ALARM PANEL, system: SEC}
  - {entity: valve.main_water, label: MAIN WATER, system: WATER}
```

Each change becomes an information row (`ALARM PANEL  ARMED AWAY`) under its
system, with no severity mark, kept as long as alert history. The first
state seen after starting only sets a baseline, so restarts log nothing, and
nothing is compared while Home Assistant is disconnected.

### Choosing a severity

A **warning** is a hazard to people or property happening now. A **caution**
needs attention soon or means something isn't as it should be. An
**advisory** is information that clears itself. Every alert on a sensor that
can bounce gets a `for:` hold time. Status (what a symbol shows now) is kept
separate from alerts (what latches and needs acknowledging). On security and
life-safety systems a sensor that stops reporting is a caution, not just gray.
One fault raises one alert: a device behind one that is already down, or
every device when their controller can't be reached, is left to that one's
alert (see the NET alerts in `examples/config/alerts.yaml`).

| System | Warning | Caution | Advisory |
|---|---|---|---|
| LEAK | leak sensor wet | leak sensor offline | sensor battery low |
| WATER | | main shut off unexpectedly; continuous flow with nothing in use (`for: 30m`); pressure out of range (`for: 2m`); water heater not heating (`for: 1h`) | filter/softener service due; irrigation running |
| GAS | gas or CO detected | detector offline | |
| HVAC | no heat with the house below a freeze-risk temperature | a zone can't reach setpoint (more than 3° off, `for: 30m`); thermostat offline | filter overdue; humidity out of range |
| SEC | alarm triggered | armed with a zone open; zone tamper or trouble; panel offline | zone battery low; door left open (`for: 10m`) |
| FIRE | smoke detected | detector offline or trouble | detector battery low |
| NET | internet down (`for: 2m`); network controller unreachable | a switch, access point or the LoRa radio offline (`for: 5m`) | slow link speed; a mesh repeater gone quiet |

## Displays

`displays.yaml` lists the physical displays the server drives:

```yaml
displays:
  workshop:
    theme: lcd                 # lcd | mirror | eink_mono | eink_color
    size: [1280, 800]          # pixels
    home: status               # shown at startup
    pages: [status, electrical]   # what a viewer can select
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
    refresh: 5m                # how often the device fetches (panels only; default 5m)
    average: 5m                # averaging window: default 'refresh' on panels, live
                               # elsewhere; 0 for live values, at most 1h
```

A display with an averaging window shows each measurement averaged over
the window ending now, instead of its latest reading: a slow display isn't
left showing a passing spike or lull until its next refresh. Panels average
over their `refresh` by default; browser displays are live unless given an
`average` (a short one, such as `30s`, can calm a jittery reading on the
mirror). Only Home Assistant measurements are averaged (`state_class:
measurement`); totals, on/off and text states and attributes show as they
are now. An entity with no data now shows no data. Status rules judge the
averaged values, so a color always matches the number shown; alerts always
judge live readings. Override the choice per entity in `defs.yaml`:

```yaml
averaging:
  entities:
    sensor.battery_soc: false   # show live
    sensor.template_power: true # a template sensor without a state_class
```

A display shows one page at a time and stays on it until a viewer selects
another. Pages are never cycled automatically, and alerts never switch pages;
the annunciator banner overlays whatever page is showing. `home` (and
`alerts_page`) are always selectable.

### Soft keys

Every display with more than one page has four keys; a display with one
page (like the mirror) has none. The keys share the bottom 40-unit strip with the
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

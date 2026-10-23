# Entity conventions

The example config and the synthetic fixtures follow how Home Assistant
integrations usually expose each kind of equipment. When the real house is
connected, map its entities onto these shapes (`mfdhome check CONFIG --ha`
lists anything missing); the pages and alerts shouldn't need redesigning.

Bindings can read an attribute (`{entity: ..., attribute: ...}`), fix a sign or
scale (`scale: -1`, `scale: 1000`) and set a unit (`unit: W`). Anything that
needs real logic, such as "a fixture is in use", is best made a template
sensor in Home Assistant and bound like any other entity.

## Every entity

- Sensors' `state_class` decides what slow displays average: `measurement`
  readings (power, flow, temperature, ...) are averaged over the display's
  window; `total` and `total_increasing` (energy, water used) never are.
  Template sensors should declare one; otherwise override them under
  `averaging` in `defs.yaml`.

- `unavailable` and `unknown` mean no data: the element is drawn gray and
  dotted, and status rules or alerts can test for it with `unavailable: true`.
- Binary sensors are `on`/`off`. Their `device_class` says what `on` means
  (`door` open, `moisture` wet, `motion` detected, `problem` faulty,
  `connectivity` connected).

## Electrical

| What | Entity | Notes |
|---|---|---|
| Power flows | `sensor.*_power` | W or kW. Grid: positive = import. Battery: positive = charging. |
| Battery level | `sensor.*_soc` | % |
| Breakers, smart circuits | `switch.*` | `on` = closed |
| Grid connection | `binary_sensor.*` | `on` = connected to the grid |

## Water

| What | Entity | Notes |
|---|---|---|
| Main shutoff | `valve.*` | `open`, `closed`, `opening`, `closing`; some shutoffs are a `switch` (`on` = open) |
| Flow rate | `sensor.*_flow` | gal/min (or L/min) |
| Pressure | `sensor.*_pressure` | psi |
| Water temperature | `sensor.*_water_temperature` | °F |
| Usage | `sensor.*_water_usage` | gal, `total_increasing` |
| Leak sensors | `binary_sensor.*_leak` | `device_class: moisture`, `on` = wet |
| Water heater | `water_heater.*` | state is the operation mode (`eco`, `gas`, `performance`, `off`, ...); attributes `current_temperature`, `temperature` (target). A burner-on signal, where available, is usually a separate `binary_sensor`. |
| Irrigation zones | `valve.*` or `switch.*` | per zone |

## Natural gas

| What | Entity | Notes |
|---|---|---|
| Gas meter | `sensor.*_gas` | `device_class: gas`; ft³, CCF or m³, `total_increasing` |
| Gas leak detector | `binary_sensor.*_gas` | `device_class: gas`, `on` = gas detected |
| CO detector | `binary_sensor.*_co` | `device_class: carbon_monoxide` |

## HVAC

| What | Entity | Notes |
|---|---|---|
| Thermostat (one per zone) | `climate.*` | state is the HVAC mode (`off`, `heat`, `cool`, `heat_cool`, `auto`, `fan_only`); attributes `current_temperature`, `temperature` (setpoint; `target_temp_low`/`high` in `heat_cool`), `hvac_action` (`heating`, `cooling`, `idle`, `fan`, `off`), `current_humidity` |
| Zone damper | `cover.*` or `switch.*` | `open`/`closed`, or `on` = open |
| Room temperatures | `sensor.*_temperature` | °F |
| Filter | `sensor.*_filter_*` | days remaining or % life, where the thermostat reports it |
| Furnace fault | `binary_sensor.*` | `device_class: problem` |

## Security (Konnected-style)

| What | Entity | Notes |
|---|---|---|
| Alarm panel | `alarm_control_panel.*` | `disarmed`, `arming`, `armed_home`, `armed_away`, `armed_night`, `armed_vacation`, `pending` (entry delay), `triggered`, `disarming` |
| Door and window zones | `binary_sensor.*` | `device_class: door` / `window`, `on` = open |
| Motion zones | `binary_sensor.*` | `device_class: motion`, `on` = motion |
| Smoke detectors | `binary_sensor.*` | `device_class: smoke`, `on` = smoke |
| Glass break, tamper | `binary_sensor.*` | `device_class: sound` / `tamper` |
| Siren | `switch.*` | displays never switch it |

## Network (UniFi)

From Home Assistant's UniFi Network integration. Entity ids follow the device
names given in UniFi (`Gateway`, `Core Switch`, ...).

| What | Entity | Notes |
|---|---|---|
| Device state | `sensor.<device>_state` | `connected`, `disconnected`, `pending`, `firmware_mismatch`, `upgrading`, `provisioning`, `heartbeat_missed`, `adopting`, `deleting`, `inform_error`, `adoption_failed`, `isolated` |
| CPU, memory | `sensor.<device>_cpu_utilization`, `sensor.<device>_memory_utilization` | % |
| Temperature | `sensor.<device>_temperature` | devices with a sensor |
| Clients | `sensor.<device>_clients` | clients connected through the device |
| Port throughput | `sensor.<device>_port_<n>_rx`, `_tx` | Mbit/s; disabled by default, enable the ports you draw |
| Port link speed | `sensor.<device>_port_<n>_link_speed` | Mbit/s; disabled by default |
| Internet | `binary_sensor.*` | UniFi has no WAN entity: use the Ping integration (`device_class: connectivity`, `on` = reachable, `round_trip_time_avg` in ms) |

On UniFi OS consoles the controller runs on the gateway, so when the gateway
goes down every UniFi entity becomes unavailable at once. The example alerts
raise one gateway alert for that, not one per device.

## Network (MeshCore LoRa)

From the meshcore-ha integration (HACS), with the companion radio on USB.
`<pk6>`/`<pk10>` are the first 6 or 10 hex digits of a node's public key and
`<name>` its advertised name.

| What | Entity | Notes |
|---|---|---|
| Companion link | `sensor.meshcore_<pk6>_node_status` | `online`/`offline`: the radio's link to Home Assistant; its other entities go unavailable when it's disconnected |
| Repeater reachable | `binary_sensor.meshcore_<pk10>_online_<name>` | `on` if a status request succeeded within 2.5 update intervals, `off` if not, `unknown` until the first success after Home Assistant starts |
| Repeater path | `sensor.meshcore_<pk10>_out_path_len_<name>` | hops through other repeaters; 0 = heard directly |
| Repeater signal | `sensor.meshcore_<pk10>_last_rssi_<name>`, `_last_snr_<name>`, `_noise_floor_<name>` | dBm, dB, dBm |
| Repeater battery | `sensor.meshcore_<pk10>_battery_percentage_<name>` | solar or battery repeaters only |

Repeater entities only update when the integration polls the repeater (its
update interval, 2 hours by default; 30 minutes is a reasonable setting for
a repeater you watch). Give them a `stale_after` longer than that interval,
or the default limit marks them unavailable between polls; the Online sensor
already says when a repeater has gone quiet.

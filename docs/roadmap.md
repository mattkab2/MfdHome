# Roadmap: Water, HVAC and Security pages

Bring water and HVAC pages to parity with the Electrical page, fold natural gas
into both, and add a floorplan page for a home security system. Built against
synthetic fixtures (modelled on Home Assistant integration conventions) until
the real-house check maps them to real entities.

## Milestones

| | Milestone | Delivers |
|---|---|---|
| M0 | Offline development | `serve --states` / `--scenario` (a scripted timeline of state changes), synthetic fixtures, entity conventions doc |
| M1 | Shared building blocks | sensor badge symbol, entity-vs-entity comparisons in conditions, line service tags, severity guide |
| M2 | Water page | smart shutoff, PRV, check valve, backflow preventer, filter/softener, expansion tank, recirculation pump; gas meter and gas lines; example page and scenarios |
| M4 | Floorplan page | rooms, walls, openings (doors/windows on contact sensors), point sensors, alarm panel badge |
| M3 | HVAC page | furnace, blower, filter, zone damper, thermostat element (current/setpoint/action); ducts; room temperatures |
| M5 | Security alerts and log | arming-aware status, zone trouble, logged non-alert events (arm/disarm) |
| M6 | Integration | new systems on the annunciator, life-safety priority, docs |

Order: M0, M1, then M2 and M4 (independent), M3, M5, M6.

**Status: complete.** Every milestone is in, built and tested against
synthetic fixtures; what remains is the real-house check (see CLAUDE.md).

## Settled decisions

- **Media are told apart by service tags** on lines (`CW`, `HW`, `GAS`, `SA`,
  `RA`), the P&ID way; color and pattern stay reserved for status.
- **Floorplans are coordinates in page YAML** (rooms, walls, openings), not an
  imported drawing, so the theme controls every color and weight. A real
  floorplan lives only in the private config repo.
- **Life-safety alerts** (smoke, CO, gas, a triggered alarm) sort first in the
  banner. Preemption stays out.
- **Non-alert events** (arm/disarm) can be logged alongside alerts.
- **Displays never control anything**: acknowledging is not disarming or
  silencing.

## Severity guide

See "Choosing a severity" in `docs/page-schema.md`.

# mfdhome

House status pages for [Home Assistant](https://www.home-assistant.io/), drawn
as multifunction-display (MFD) schematics: P&ID and avionics-style pages for
the electrical system, water, HVAC, the network and security, with an
annunciator panel and an alert log. They're not dashboards.

You define a page once in YAML. It then renders to several kinds of display:

| Display | Theme | Notes |
|---|---|---|
| A tablet in a kiosk browser | `lcd` | Live, with touch soft keys |
| A two-way mirror over a monitor | `mirror` | Pure black, thin bright lines |
| An e-paper panel (ESPHome or a Pi) | `eink_mono`, `eink_color` | PNG snapshots in the panel's own colors, with readings averaged over its refresh interval |

Status reads the same way on every display, using the Gruvbox palette: aqua is
normal, yellow is caution, red is warning, blue means flowing, and gray dotted
means no data. Lines also carry status in their pattern, so it survives a
one-color e-paper panel.

Cautions and warnings latch until someone acknowledges them, and one
acknowledgement clears them for the whole house. Every alert is also written
to a history log.

## Quick start

```bash
poetry install
poetry run mfdhome check examples/config
poetry run mfdhome serve examples/config --scenario examples/scenarios/grid_outage.yaml
```

Then open `http://localhost:8099/`. The scenario replays a grid outage with
no Home Assistant needed.

## Documentation

- [docs/running.md](docs/running.md): the commands, connecting to Home Assistant, and serving displays
- [docs/page-schema.md](docs/page-schema.md): the page, alert and display file formats
- [docs/entities.md](docs/entities.md): the Home Assistant entities the examples expect
- [docs/addon.md](docs/addon.md): installing as a Home Assistant add-on

Keep your own house's configuration in a separate repository; `examples/` is a
generic starting point.

## License

MIT, see [LICENSE](LICENSE). The bundled DejaVu Sans Mono font has its own
license in `src/mfdhome/fonts/`.

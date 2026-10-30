# Changelog

## 0.2.0

- Taller displays (a 4:3 e-paper panel showing 5:3 pages) fill the extra
  height with a band of annunciator tiles, so every page shows the house's
  status; `annunciator` in `displays.yaml` picks the systems (default: all).
- The server paces e-paper redraws: let the panel poll often (every 30 s).
  It gets a new image when its `refresh` has passed, or at once when an
  alert, acknowledgement, key press or page change makes one due.
- New `eink_gray` theme for 4- and 16-gray panels: walls, rooms and no-data
  marks in dark gray, unlit tiles in light gray.
- Condensers take a `power` reading.

## 0.1.0

- First add-on release: connects through the Supervisor, pulls the house
  config from git, keeps the alert board and history in the add-on's data
  (included in Home Assistant backups).

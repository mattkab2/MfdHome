# MFD Home

Serves your house's status pages to the displays around the house: tablets
and mirrors in a kiosk browser, and e-paper panels that fetch a PNG. The pages
come from your own config, which the add-on pulls from a git repository each
time it starts.

## Install

1. In Home Assistant, go to **Settings → Apps → App store** (older versions:
   **Settings → Add-ons → Add-on store**). Open the **⋮** menu, choose
   **Repositories**, and add `https://github.com/mattkab2/MfdHome`.
2. Find **MFD Home** in the store and install it. The first install builds
   the image on your device, which takes a few minutes on a Raspberry Pi 5.
3. Fill in the **Configuration** tab (below), then start the add-on.

The add-on connects to Home Assistant by itself; it needs no access token.

## Your house config

Keep your config (`defs.yaml`, `alerts.yaml`, `displays.yaml`, `pages/`) in a
git repository of its own. If the repository is private, give the add-on a
read-only **deploy key**:

1. On any computer, make a key pair with no passphrase:

   ```bash
   ssh-keygen -t ed25519 -N "" -C mfdhome -f mfdhome_deploy_key
   ```

2. On GitHub, open the config repository's **Settings → Deploy keys → Add
   deploy key**. Paste the contents of `mfdhome_deploy_key.pub`, and leave
   **Allow write access** unticked.
3. In the add-on's **Configuration** tab, paste the private key
   (`mfdhome_deploy_key`) into **Deploy key**, one line per entry, from
   `-----BEGIN OPENSSH PRIVATE KEY-----` to `-----END OPENSSH PRIVATE KEY-----`.
   In YAML mode:

   ```yaml
   config_repo: git@github.com:you/your-house-config.git
   config_branch: main
   config_path: config
   deploy_key:
     - "-----BEGIN OPENSSH PRIVATE KEY-----"
     - "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW"
     - "..."
     - "-----END OPENSSH PRIVATE KEY-----"
   ```

4. Delete both key files from that computer. The key now lives only in the
   add-on's private data and on GitHub.

| Option | Meaning |
|---|---|
| `config_repo` | The repository's git URL. Leave it empty to copy the config into the add-on's config folder (`/addon_configs/<id>_mfdhome/` over Samba) by hand instead. |
| `config_branch` | The branch to serve. |
| `config_path` | The folder holding the config inside the repository. Leave it empty if the files are at the top of the repository. |
| `deploy_key` | The private key, for a private repository. |
| `display_token` | Optional. Every display URL then needs `?token=<value>`. |

**Updating:** push your config changes, then restart the add-on. Each start
fetches the branch again and discards any edits made on the device. If the
fetch fails (GitHub down, say), the add-on serves the last copy it has and
logs a warning. It won't start only when there's no copy at all.

Before pushing, check the config on your computer with `mfdhome check`.

## Displays

Each display in `displays.yaml` is served at
`http://homeassistant.local:8099/display/<id>`. Use your Home Assistant's
address if `homeassistant.local` doesn't resolve on a device. Open that URL
in the display's kiosk browser; `http://homeassistant.local:8099/` lists them
all. An e-paper panel fetches `/display/<id>.png` and presses keys with
`POST /display/<id>/key/<1-4>`.

The port is reached directly, not through Home Assistant's sidebar
(ingress), because kiosks and ESP32 panels can't log in to Home Assistant.
You can change the host port in the **Network** section. Keep it on your
local network, and set a `display_token` if other people use your Wi-Fi.

## Data and backups

The alert board (what's latched and who acknowledged it) and the alert
history are kept in the add-on's private data. Home Assistant backups include
it, so they survive restarts, updates and restores.

# Standalone mfdhome image, built from this source tree: Home Assistant in
# plain Docker, or a separate host. (The Home Assistant add-on builds from
# addon/Dockerfile instead.)
#
#   podman build -t mfdhome .
#   podman run -p 8099:8099 -e TZ=America/New_York \
#       -e HA_URL=http://192.168.1.10:8123 -e HA_TOKEN=... \
#       -v ./house-config:/config:ro -v mfdhome-data:/data mfdhome
#
# The house config goes in /config (defs.yaml, alerts.yaml, displays.yaml,
# pages/); the alert board and history are kept in /data. TZ sets the time
# the e-paper "as of" stamp and the alert log show (default UTC). Give HA_URL
# as an address: homeassistant.local (mDNS) usually doesn't resolve inside a
# container.
ARG BUILD_FROM=ghcr.io/home-assistant/base-python:3.14-alpine3.24
FROM ${BUILD_FROM}

RUN apk add --no-cache git openssh-client

COPY pyproject.toml poetry.lock README.md LICENSE /opt/mfdhome/
COPY src /opt/mfdhome/src
COPY docker/install.sh /opt/mfdhome/docker/install.sh
RUN /opt/mfdhome/docker/install.sh

ENV PATH="/opt/venv/bin:${PATH}"
EXPOSE 8099
# with-contenv: s6 (the base image's init) gives the command the container's
# environment (HA_URL/HA_TOKEN here, SUPERVISOR_TOKEN in an add-on) only through it.
CMD ["/usr/bin/with-contenv", "mfdhome", "addon"]

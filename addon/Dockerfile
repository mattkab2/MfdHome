# The Home Assistant add-on image, built by the Supervisor on the device: the
# mfdhome release tagged v<add-on version>, installed with the dependency
# versions in its poetry.lock. Runs 'mfdhome addon': options, the house config
# from git, then the display server.
ARG BUILD_FROM=ghcr.io/home-assistant/base-python:3.14-alpine3.24
FROM ${BUILD_FROM}
ARG BUILD_VERSION=0.1.0

RUN apk add --no-cache git openssh-client \
    && git clone --depth 1 --branch "v${BUILD_VERSION}" \
        https://github.com/mattkab2/MfdHome.git /opt/mfdhome \
    && /opt/mfdhome/docker/install.sh

ENV PATH="/opt/venv/bin:${PATH}"
EXPOSE 8099
# with-contenv: s6 (the base image's init) gives the command the container's
# environment (HA_URL/HA_TOKEN here, SUPERVISOR_TOKEN in an add-on) only through it.
CMD ["/usr/bin/with-contenv", "mfdhome", "addon"]

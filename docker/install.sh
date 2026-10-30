#!/bin/sh
# Install mfdhome from the source tree in /opt/mfdhome into /opt/venv, with the
# exact dependency versions in poetry.lock, then drop Poetry itself. Shared by
# the standalone image (Dockerfile) and the Home Assistant add-on
# (addon/Dockerfile).
set -eu

POETRY_VERSION=2.3.1

python3 -m venv /opt/poetry
/opt/poetry/bin/pip install --no-cache-dir "poetry==${POETRY_VERSION}"
python3 -m venv /opt/venv
cd /opt/mfdhome
VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:${PATH}" POETRY_VIRTUALENVS_CREATE=false \
    /opt/poetry/bin/poetry install --only main --no-interaction --no-ansi
rm -rf /opt/poetry /root/.cache

"""Loading and validating page definition files (YAML).

A config directory holds an optional ``defs.yaml`` (shared thresholds, state
maps and named conditions, and the house-wide staleness limits and averaging
overrides), an optional ``alerts.yaml`` (systems, alerts and logged
entities), an optional ``displays.yaml`` and one file per page under
``pages/``. See ``docs/page-schema.md`` for the format.
"""

from mfdhome.config.build import Alerts, Defs
from mfdhome.config.errors import ConfigError, Issue
from mfdhome.config.load import Config, load_alerts, load_config, load_defs, load_page

__all__ = [
    "Alerts",
    "Config",
    "ConfigError",
    "Defs",
    "Issue",
    "load_alerts",
    "load_config",
    "load_defs",
    "load_page",
]

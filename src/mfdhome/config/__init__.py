"""Loading and validating page definition files (YAML).

A config directory holds an optional ``defs.yaml`` (shared thresholds and
named conditions) and one file per page under ``pages/``. See
``docs/page-schema.md`` for the format.
"""

from mfdhome.config.build import Defs
from mfdhome.config.errors import ConfigError, Issue
from mfdhome.config.load import Config, load_config, load_defs, load_page

__all__ = ["Config", "ConfigError", "Defs", "Issue", "load_config", "load_defs", "load_page"]

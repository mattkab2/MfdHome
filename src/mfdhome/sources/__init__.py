"""State providers. The only package allowed to do I/O against HA or fixtures."""

from mfdhome.sources.fixture import load_fixture

__all__ = ["load_fixture"]

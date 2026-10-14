"""Shared test fixtures."""

from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.image import PNGImageSnapshotExtension, SVGImageSnapshotExtension
from syrupy.location import PyTestLocation


class SnapshotsDirSVGExtension(SVGImageSnapshotExtension):
    """Store SVG snapshots under ``tests/snapshots/<test module>/``."""

    @classmethod
    def dirname(cls, *, test_location: PyTestLocation) -> str:
        return str(Path(test_location.filepath).parent / "snapshots" / test_location.basename)


@pytest.fixture
def svg_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Snapshot assertion that writes viewable ``.svg`` files."""
    return snapshot.use_extension(SnapshotsDirSVGExtension)


class SnapshotsDirPNGExtension(PNGImageSnapshotExtension):
    """Store PNG snapshots under ``tests/snapshots/<test module>/``."""

    @classmethod
    def dirname(cls, *, test_location: PyTestLocation) -> str:
        return SnapshotsDirSVGExtension.dirname(test_location=test_location)


@pytest.fixture
def png_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Snapshot assertion that writes viewable ``.png`` files."""
    return snapshot.use_extension(SnapshotsDirPNGExtension)

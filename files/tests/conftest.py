"""Shared fixtures for the iRacing Setup Machine test suite."""
import sys, os
import pytest

# Ensure the project root is on sys.path so ``import core.*`` works.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.ibt_parser import load_demo_data, TelemetryData
from core.setup_parser import create_demo_setup


@pytest.fixture
def demo_data() -> TelemetryData:
    """Pre-built demo telemetry with 8 laps of ferrari_296_gt3 at Sebring."""
    return load_demo_data()


@pytest.fixture
def demo_setup():
    """Pre-built demo setup dict for ferrari_296_gt3 at Sebring."""
    return create_demo_setup("ferrari_296_gt3", "Sebring International Raceway")

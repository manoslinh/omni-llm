"""
Pytest configuration for scheduling module tests.

This conftest.py provides test isolation for scheduling module tests,
allowing them to run independently even when other components have import issues.
"""

import os
import sys

import pytest


def pytest_configure(config):
    """Configure pytest for scheduling tests."""
    # Mark all tests in this directory as scheduling tests
    config.addinivalue_line(
        "markers", "scheduling: tests for scheduling module components"
    )


@pytest.fixture(scope="session")
def predictive_module():
    """
    Fixture to import predictive module directly, bypassing import chain issues.

    This allows predictive module tests to run even when resource_pool.py
    has import issues (e.g., ResourceBudget import problem).
    """
    # Add src to path if not already there
    src_dir = os.path.join(os.path.dirname(__file__), '../../..')
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    # Import directly from the module file
    import importlib.util
    module_path = os.path.join(src_dir, "src/omni/scheduling/predictive.py")

    spec = importlib.util.spec_from_file_location("predictive", module_path)
    predictive = importlib.util.module_from_spec(spec)
    sys.modules["predictive"] = predictive
    spec.loader.exec_module(predictive)

    return predictive

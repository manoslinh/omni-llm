"""
Basic tests for CostTracker.
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from omni.providers.base import CostRate
from omni.providers.cost_tracker import CostTracker


def test_basic_tracking():
    """Test basic cost tracking."""
    print("Testing basic cost tracking...")

    # Create cost rates
    cost_rates = {
        "openai/gpt-4o": CostRate(input_per_million=30.00, output_per_million=60.00),
        "openai/gpt-4o-mini": CostRate(input_per_million=0.50, output_per_million=1.50),
    }

    tracker = CostTracker(cost_rates)

    # Track a request
    record = tracker.track("openai/gpt-4o", input_tokens=1000, output_tokens=500)

    # Verify calculations
    expected_input_cost = (1000 / 1_000_000) * 30.00  # $0.00003
    expected_output_cost = (500 / 1_000_000) * 60.00   # $0.00003
    expected_total_cost = expected_input_cost + expected_output_cost

    assert abs(record.input_cost - expected_input_cost) < 1e-10, f"Input cost mismatch: {record.input_cost} vs {expected_input_cost}"
    assert abs(record.output_cost - expected_output_cost) < 1e-10, f"Output cost mismatch: {record.output_cost} vs {expected_output_cost}"
    assert abs(record.total_cost - expected_total_cost) < 1e-10, f"Total cost mismatch: {record.total_cost} vs {expected_total_cost}"
    assert record.input_tokens == 1000
    assert record.output_tokens == 500
    assert record.total_tokens == 1500
    assert record.model == "openai/gpt-4o"

    print("✓ Basic tracking test passed")


def test_multiple_requests():
    """Test tracking multiple requests."""
    print("Testing multiple requests...")

    cost_rates = {
        "openai/gpt-4o-mini": CostRate(input_per_million=0.50, output_per_million=1.50),
        "openai/gpt-4o": CostRate(input_per_million=30.00, output_per_million=60.00),
    }

    tracker = CostTracker(cost_rates)

    # Track multiple requests
    tracker.track("openai/gpt-4o", input_tokens=1000, output_tokens=500)
    tracker.track("openai/gpt-4o-mini", input_tokens=2000, output_tokens=1000)

    totals = tracker.get_total()

    # Calculate expected totals
    gpt4_input_cost = (1000 / 1_000_000) * 30.00
    gpt4_output_cost = (500 / 1_000_000) * 60.00
    gpt4o_mini_input_cost = (2000 / 1_000_000) * 0.50
    gpt4o_mini_output_cost = (1000 / 1_000_000) * 1.50

    expected_total_cost = gpt4_input_cost + gpt4_output_cost + gpt4o_mini_input_cost + gpt4o_mini_output_cost
    expected_total_input_cost = gpt4_input_cost + gpt4o_mini_input_cost
    expected_total_output_cost = gpt4_output_cost + gpt4o_mini_output_cost

    assert abs(totals["total_cost"] - expected_total_cost) < 1e-10
    assert abs(totals["total_input_cost"] - expected_total_input_cost) < 1e-10
    assert abs(totals["total_output_cost"] - expected_total_output_cost) < 1e-10
    assert totals["total_input_tokens"] == 3000
    assert totals["total_output_tokens"] == 1500
    assert totals["total_tokens"] == 4500

    print("✓ Multiple requests test passed")


def test_reset():
    """Test reset functionality."""
    print("Testing reset...")

    cost_rates = {
        "openai/gpt-4o": CostRate(input_per_million=30.00, output_per_million=60.00),
    }

    tracker = CostTracker(cost_rates)
    tracker.track("openai/gpt-4o", input_tokens=1000, output_tokens=500)

    assert len(tracker) == 1
    assert tracker.get_total()["total_cost"] > 0

    tracker.reset()

    assert len(tracker) == 0
    assert tracker.get_total()["total_cost"] == 0.0
    assert tracker.get_total()["total_input_tokens"] == 0
    assert tracker.get_total()["total_output_tokens"] == 0

    print("✓ Reset test passed")


def test_fallback_cost():
    """Test fallback cost calculation for unknown models."""
    print("Testing fallback cost calculation...")

    tracker = CostTracker()  # No cost rates provided

    # Track with unknown model - should use fallback rates
    record = tracker.track("unknown/model", input_tokens=1000, output_tokens=500)

    # Fallback rates: input_per_million=5.00, output_per_million=15.00
    expected_input_cost = (1000 / 1_000_000) * 5.00
    expected_output_cost = (500 / 1_000_000) * 15.00

    assert abs(record.input_cost - expected_input_cost) < 1e-10
    assert abs(record.output_cost - expected_output_cost) < 1e-10

    print("✓ Fallback cost test passed")


def test_get_records():
    """Test getting all records."""
    print("Testing get_records...")

    cost_rates = {
        "openai/gpt-4o": CostRate(input_per_million=30.00, output_per_million=60.00),
    }

    tracker = CostTracker(cost_rates)
    tracker.track("openai/gpt-4o", input_tokens=1000, output_tokens=500)
    tracker.track("openai/gpt-4o", input_tokens=2000, output_tokens=1000)

    records = tracker.get_records()

    assert len(records) == 2
    assert records[0].input_tokens == 1000
    assert records[1].input_tokens == 2000

    print("✓ Get records test passed")


def test_integration_with_provider():
    """Test integration with provider cost rates."""
    print("Testing integration with provider cost rates...")

    # Simulate provider cost rates
    provider_cost_rates = {
        "openai/gpt-4o": CostRate(input_per_million=30.00, output_per_million=60.00),
        "openai/gpt-4o-mini": CostRate(input_per_million=0.50, output_per_million=1.50),
    }

    tracker = CostTracker(provider_cost_rates)

    # Track using the same cost rates
    record = tracker.track("openai/gpt-4o", input_tokens=1000, output_tokens=500)

    # Verify cost calculation matches provider's cost_per_token
    expected_input_cost = (1000 / 1_000_000) * 30.00
    expected_output_cost = (500 / 1_000_000) * 60.00

    assert abs(record.input_cost - expected_input_cost) < 1e-10
    assert abs(record.output_cost - expected_output_cost) < 1e-10

    print("✓ Integration test passed")


def test_empty_tracker():
    """Test empty tracker behavior."""
    print("Testing empty tracker...")

    tracker = CostTracker()

    assert len(tracker) == 0
    assert bool(tracker) is False

    totals = tracker.get_total()
    assert totals["total_cost"] == 0.0
    assert totals["total_input_tokens"] == 0
    assert totals["total_output_tokens"] == 0

    print("✓ Empty tracker test passed")


if __name__ == "__main__":
    print("Running CostTracker tests...\n")

    test_basic_tracking()
    test_multiple_requests()
    test_reset()
    test_fallback_cost()
    test_get_records()
    test_integration_with_provider()
    test_empty_tracker()

    print("\n✅ All tests passed!")

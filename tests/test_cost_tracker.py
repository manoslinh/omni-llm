"""
Tests for CostTracker.
"""

import pytest

from omni.providers.cost_tracker import CostTracker, CostRecord
from omni.providers.base import CostRate


class TestCostTracker:
    """Tests for the CostTracker class."""
    
    @pytest.fixture
    def cost_rates(self):
        """Create sample cost rates for testing."""
        return {
            "openai/gpt-4": CostRate(input_per_million=30.00, output_per_million=60.00),
            "openai/gpt-3.5-turbo": CostRate(input_per_million=0.50, output_per_million=1.50),
            "anthropic/claude-3-opus": CostRate(input_per_million=15.00, output_per_million=75.00),
        }
    
    @pytest.fixture
    def tracker(self, cost_rates):
        """Create a cost tracker for testing."""
        return CostTracker(cost_rates)
    
    def test_initialization(self, tracker):
        """Test tracker initialization."""
        assert len(tracker) == 0
        assert bool(tracker) is False
        
        totals = tracker.get_total()
        assert totals["total_cost"] == 0.0
        assert totals["total_input_tokens"] == 0
        assert totals["total_output_tokens"] == 0
    
    def test_track_single_request(self, tracker):
        """Test tracking a single request."""
        record = tracker.track("openai/gpt-4", input_tokens=1000, output_tokens=500)
        
        # Verify record structure
        assert isinstance(record, CostRecord)
        assert record.input_tokens == 1000
        assert record.output_tokens == 500
        assert record.total_tokens == 1500
        assert record.model == "openai/gpt-4"
        
        # Verify cost calculations
        expected_input_cost = (1000 / 1_000_000) * 30.00
        expected_output_cost = (500 / 1_000_000) * 60.00
        expected_total_cost = expected_input_cost + expected_output_cost
        
        assert abs(record.input_cost - expected_input_cost) < 1e-10
        assert abs(record.output_cost - expected_output_cost) < 1e-10
        assert abs(record.total_cost - expected_total_cost) < 1e-10
    
    def test_track_multiple_requests(self, tracker):
        """Test tracking multiple requests."""
        # Track first request
        tracker.track("openai/gpt-4", input_tokens=1000, output_tokens=500)
        
        # Track second request with different model
        tracker.track("openai/gpt-3.5-turbo", input_tokens=2000, output_tokens=1000)
        
        # Verify totals
        totals = tracker.get_total()
        
        # Calculate expected totals
        gpt4_input_cost = (1000 / 1_000_000) * 30.00
        gpt4_output_cost = (500 / 1_000_000) * 60.00
        gpt35_input_cost = (2000 / 1_000_000) * 0.50
        gpt35_output_cost = (1000 / 1_000_000) * 1.50
        
        expected_total_cost = gpt4_input_cost + gpt4_output_cost + gpt35_input_cost + gpt35_output_cost
        expected_total_input_cost = gpt4_input_cost + gpt35_input_cost
        expected_total_output_cost = gpt4_output_cost + gpt35_output_cost
        
        assert abs(totals["total_cost"] - expected_total_cost) < 1e-10
        assert abs(totals["total_input_cost"] - expected_total_input_cost) < 1e-10
        assert abs(totals["total_output_cost"] - expected_total_output_cost) < 1e-10
        assert totals["total_input_tokens"] == 3000
        assert totals["total_output_tokens"] == 1500
        assert totals["total_tokens"] == 4500
    
    def test_reset(self, tracker):
        """Test reset functionality."""
        tracker.track("openai/gpt-4", input_tokens=1000, output_tokens=500)
        
        assert len(tracker) == 1
        assert tracker.get_total()["total_cost"] > 0
        
        tracker.reset()
        
        assert len(tracker) == 0
        assert tracker.get_total()["total_cost"] == 0.0
        assert tracker.get_total()["total_input_tokens"] == 0
        assert tracker.get_total()["total_output_tokens"] == 0
    
    def test_fallback_cost_calculation(self):
        """Test fallback cost calculation for unknown models."""
        tracker = CostTracker()  # No cost rates provided
        
        # Track with unknown model - should use fallback rates
        record = tracker.track("unknown/model", input_tokens=1000, output_tokens=500)
        
        # Fallback rates: input_per_million=5.00, output_per_million=15.00
        expected_input_cost = (1000 / 1_000_000) * 5.00
        expected_output_cost = (500 / 1_000_000) * 15.00
        
        assert abs(record.input_cost - expected_input_cost) < 1e-10
        assert abs(record.output_cost - expected_output_cost) < 1e-10
    
    def test_get_records(self, tracker):
        """Test getting all records."""
        tracker.track("openai/gpt-4", input_tokens=1000, output_tokens=500)
        tracker.track("openai/gpt-4", input_tokens=2000, output_tokens=1000)
        
        records = tracker.get_records()
        
        assert len(records) == 2
        assert records[0].input_tokens == 1000
        assert records[1].input_tokens == 2000
        
        # Verify records are independent copies
        records[0].input_tokens = 9999
        assert tracker.get_records()[0].input_tokens == 1000
    
    def test_model_pattern_matching(self, tracker):
        """Test that model pattern matching works correctly."""
        # Track with a model that contains the pattern
        record = tracker.track("openai/gpt-4-turbo", input_tokens=1000, output_tokens=500)
        
        # Should match "openai/gpt-4" pattern
        expected_input_cost = (1000 / 1_000_000) * 30.00
        expected_output_cost = (500 / 1_000_000) * 60.00
        
        assert abs(record.input_cost - expected_input_cost) < 1e-10
        assert abs(record.output_cost - expected_output_cost) < 1e-10
    
    def test_empty_tracker_behavior(self):
        """Test behavior of empty tracker."""
        tracker = CostTracker()
        
        assert len(tracker) == 0
        assert bool(tracker) is False
        
        totals = tracker.get_total()
        assert totals["total_cost"] == 0.0
        assert totals["total_input_cost"] == 0.0
        assert totals["total_output_cost"] == 0.0
        assert totals["total_input_tokens"] == 0
        assert totals["total_output_tokens"] == 0
        assert totals["total_tokens"] == 0
    
    def test_cost_record_dataclass(self):
        """Test CostRecord dataclass structure."""
        record = CostRecord(
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            input_cost=0.03,
            output_cost=0.03,
            total_cost=0.06,
            model="test-model",
        )
        
        assert record.input_tokens == 1000
        assert record.output_tokens == 500
        assert record.total_tokens == 1500
        assert record.input_cost == 0.03
        assert record.output_cost == 0.03
        assert record.total_cost == 0.06
        assert record.model == "test-model"
    
    def test_custom_cost_rates(self, tracker):
        """Test using custom cost rates for a specific track call."""
        custom_rates = {
            "custom/model": CostRate(input_per_million=1.00, output_per_million=2.00),
        }
        
        # Track with custom rates
        record = tracker.track(
            "custom/model",
            input_tokens=1000,
            output_tokens=500,
            cost_rates=custom_rates
        )
        
        # Should use custom rates, not instance rates
        expected_input_cost = (1000 / 1_000_000) * 1.00
        expected_output_cost = (500 / 1_000_000) * 2.00
        
        assert abs(record.input_cost - expected_input_cost) < 1e-10
        assert abs(record.output_cost - expected_output_cost) < 1e-10
    
    def test_integration_with_provider_cost_rates(self, cost_rates):
        """Test integration with provider cost rates."""
        # Simulate using provider's cost_per_token
        tracker = CostTracker(cost_rates)
        
        # Track using the same cost rates
        record = tracker.track("openai/gpt-4", input_tokens=1000, output_tokens=500)
        
        # Verify cost calculation matches provider's cost_per_token
        expected_input_cost = (1000 / 1_000_000) * 30.00
        expected_output_cost = (500 / 1_000_000) * 60.00
        
        assert abs(record.input_cost - expected_input_cost) < 1e-10
        assert abs(record.output_cost - expected_output_cost) < 1e-10
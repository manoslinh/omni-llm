"""
Cost Tracker for Omni-LLM.

Tracks per-request costs for LLM API calls.
"""

from copy import deepcopy
from dataclasses import dataclass

from .base import CostRate


@dataclass
class CostRecord:
    """Record of costs for a single request."""
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    model: str

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (f"CostRecord(model={self.model}, "
                f"input_tokens={self.input_tokens}, "
                f"output_tokens={self.output_tokens}, "
                f"total_tokens={self.total_tokens}, "
                f"input_cost={self.input_cost:.6f}, "
                f"output_cost={self.output_cost:.6f}, "
                f"total_cost={self.total_cost:.6f})")


class CostTracker:
    """
    Tracks costs for LLM API requests.

    Usage:
        tracker = CostTracker(cost_rates)
        tracker.track("openai/gpt-4", input_tokens=100, output_tokens=50)
        total = tracker.get_total()
        tracker.reset()
    """

    def __init__(self, cost_rates: dict[str, CostRate] | None = None):
        """
        Initialize cost tracker.

        Args:
            cost_rates: Dictionary mapping model names to CostRate objects.
                       If None, uses empty dict (no cost calculation).
        """
        self._cost_rates = cost_rates or {}
        self._records: list[CostRecord] = []
        self._total_cost: float = 0.0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_tokens: int = 0

    def track(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_rates: dict[str, CostRate] | None = None
    ) -> CostRecord:
        """
        Track costs for a single request.

        Args:
            model: Model identifier (e.g., "openai/gpt-4")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cost_rates: Optional cost rates to use (overrides instance rates)

        Returns:
            CostRecord with calculated costs

        Raises:
            ValueError: If token counts are negative
        """
        # Validate token counts are non-negative
        if input_tokens < 0:
            raise ValueError(f"input_tokens must be non-negative, got {input_tokens}")
        if output_tokens < 0:
            raise ValueError(f"output_tokens must be non-negative, got {output_tokens}")

        # Use provided cost rates or instance cost rates
        effective_cost_rates = cost_rates or self._cost_rates

        # Calculate costs
        input_cost, output_cost = self._calculate_costs(
            model, input_tokens, output_tokens, effective_cost_rates
        )

        total_cost = input_cost + output_cost
        total_tokens = input_tokens + output_tokens

        # Create record
        record = CostRecord(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            model=model,
        )

        # Update totals
        self._records.append(record)
        self._total_cost += total_cost
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_tokens += total_tokens

        return record

    def get_total(self) -> dict[str, float]:
        """
        Get total costs across all tracked requests.

        Returns:
            Dictionary with total_cost, total_input_cost, total_output_cost
        """
        total_input_cost = sum(r.input_cost for r in self._records)
        total_output_cost = sum(r.output_cost for r in self._records)

        return {
            "total_cost": self._total_cost,
            "total_input_cost": total_input_cost,
            "total_output_cost": total_output_cost,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_tokens,
        }

    def reset(self):
        """Reset all tracked costs."""
        self._records.clear()
        self._total_cost = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_tokens = 0

    def get_records(self) -> list[CostRecord]:
        """Get all cost records."""
        return deepcopy(self._records)

    def _calculate_costs(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_rates: dict[str, CostRate]
    ) -> tuple[float, float]:
        """
        Calculate input and output costs for a model.

        Args:
            model: Model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cost_rates: Cost rates dictionary

        Returns:
            Tuple of (input_cost, output_cost) in USD
        """
        # Find matching cost rate
        cost_rate = None
        for model_pattern, rate in cost_rates.items():
            if model_pattern in model:
                cost_rate = rate
                break

        # Default fallback if no match found
        if cost_rate is None:
            cost_rate = CostRate(input_per_million=5.00, output_per_million=15.00)

        # Calculate costs (tokens per million * cost per million)
        input_cost = (input_tokens / 1_000_000) * cost_rate.input_per_million
        output_cost = (output_tokens / 1_000_000) * cost_rate.output_per_million

        return input_cost, output_cost

    def __len__(self) -> int:
        """Get number of tracked records."""
        return len(self._records)

    def __bool__(self) -> bool:
        """Check if tracker has any records."""
        return len(self._records) > 0

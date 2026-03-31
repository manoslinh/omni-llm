"""
Tests for CostOptimizedStrategy.

Validates:
- Model selection by task type (architecture → expensive, coding → cheap)
- Budget enforcement
- Cost estimation
- Model ranking
- Config loading from YAML
"""

import sys

import pytest

sys.path.insert(0, "src")

from omni.router import BudgetExceededError, NoEligibleModelError, TaskType
from omni.router.cost_optimized import CostOptimizedStrategy
from omni.router.models import RoutingContext


@pytest.fixture
def strategy() -> CostOptimizedStrategy:
    """Create a CostOptimizedStrategy with default config paths."""
    return CostOptimizedStrategy()


# ── Initialization ─────────────────────────────────────────────────────────


class TestCostOptimizedInit:
    """Tests for strategy initialization."""

    def test_loads_models(self, strategy: CostOptimizedStrategy) -> None:
        """Strategy should load model definitions from models.yaml."""
        assert len(strategy._models) > 0
        assert "gpt-4o" in strategy._models
        assert "deepseek-chat" in strategy._models

    def test_loads_routing_rules(self, strategy: CostOptimizedStrategy) -> None:
        """Strategy should load routing rules from models.yaml."""
        assert "task_types" in strategy._routing_rules
        assert "coding" in strategy._routing_rules["task_types"]

    def test_loads_cost_rates(self, strategy: CostOptimizedStrategy) -> None:
        """Strategy should load cost rates from providers.yaml."""
        assert len(strategy._cost_rates) > 0

    def test_name(self, strategy: CostOptimizedStrategy) -> None:
        """Strategy name should be 'cost_optimized'."""
        assert strategy.name == "cost_optimized"


# ── Model Selection ────────────────────────────────────────────────────────


class TestSelectModel:
    """Tests for select_model routing logic."""

    def test_architecture_task_picks_high_quality(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """Architecture tasks should NOT pick the cheapest model."""
        ctx = RoutingContext(task_type=TaskType.ARCHITECTURE, file_count=5)
        result = strategy.select_model(TaskType.ARCHITECTURE, ctx)

        assert result is not None
        # Architecture has min_quality=0.8, so cheap models like deepseek
        # (quality ~0.6 for architecture) should not be selected
        assert result.model_id in [
            "claude-sonnet-4",
            "gpt-4o",
            "gemini-2.5-pro",
            "gpt-4.1",
        ]

    def test_coding_task_picks_cheap_model(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """Coding tasks should pick a cheap model that can code."""
        ctx = RoutingContext(task_type=TaskType.CODING, file_count=3)
        result = strategy.select_model(TaskType.CODING, ctx)

        assert result is not None
        # Coding has min_quality=0.7, cheapest qualifying models
        assert result.model_id in [
            "deepseek-chat",
            "deepseek-coder",
            "gpt-4o-mini",
            "claude-haiku-3.5",
        ]

    def test_testing_task_picks_cheap_model(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """Testing tasks (min_quality=0.6) should pick cheap models."""
        ctx = RoutingContext(task_type=TaskType.TESTING, file_count=2)
        result = strategy.select_model(TaskType.TESTING, ctx)

        assert result is not None
        # Testing has low min_quality, so cheaper models qualify
        assert result.model_id in [
            "deepseek-coder",
            "gpt-4o-mini",
            "claude-haiku-3.5",
            "deepseek-chat",
        ]

    def test_code_review_picks_high_quality(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """Code review (min_quality=0.9) needs high-quality models."""
        ctx = RoutingContext(task_type=TaskType.CODE_REVIEW, file_count=3)
        result = strategy.select_model(TaskType.CODE_REVIEW, ctx)

        assert result is not None
        # Only top-priority models should qualify
        assert result.model_id in ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"]

    def test_result_has_reason(self, strategy: CostOptimizedStrategy) -> None:
        """ModelSelection should include a human-readable reason."""
        ctx = RoutingContext(task_type=TaskType.CODING)
        result = strategy.select_model(TaskType.CODING, ctx)

        assert result is not None
        assert "cost" in result.reason.lower() or "cheapest" in result.reason.lower()
        assert result.confidence > 0

    def test_result_has_cost_estimate(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """ModelSelection should include a cost estimate."""
        ctx = RoutingContext(task_type=TaskType.CODING, file_count=5)
        result = strategy.select_model(TaskType.CODING, ctx)

        assert result is not None
        assert result.estimated_cost.total_cost_usd >= 0
        assert result.estimated_cost.input_tokens > 0
        assert result.estimated_cost.output_tokens > 0


# ── Budget Enforcement ─────────────────────────────────────────────────────


class TestBudgetEnforcement:
    """Tests for budget-aware model selection."""

    def test_low_budget_picks_cheaper_model(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """Low budget should force selection of cheaper models."""
        # Very low budget — should still find *some* model for coding
        ctx = RoutingContext(
            task_type=TaskType.CODING, file_count=1, budget_remaining=0.01
        )
        result = strategy.select_model(TaskType.CODING, ctx)

        assert result is not None
        assert result.estimated_cost.total_cost_usd <= 0.01

    def test_zero_budget_raises_error(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """Zero budget should raise BudgetExceededError."""
        ctx = RoutingContext(
            task_type=TaskType.CODING, file_count=1, budget_remaining=0.0
        )

        with pytest.raises(BudgetExceededError):
            strategy.select_model(TaskType.CODING, ctx)

    def test_impossible_budget_raises_error(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """Budget too small for any model should raise appropriate error."""
        # Architecture needs expensive models; tiny budget won't work
        ctx = RoutingContext(
            task_type=TaskType.ARCHITECTURE,
            file_count=100,
            budget_remaining=0.000001,
        )

        with pytest.raises((BudgetExceededError, NoEligibleModelError)):
            strategy.select_model(TaskType.ARCHITECTURE, ctx)

    def test_unlimited_budget_selects_any_qualified(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """None budget (unlimited) should work fine."""
        ctx = RoutingContext(
            task_type=TaskType.CODING, file_count=5, budget_remaining=None
        )
        result = strategy.select_model(TaskType.CODING, ctx)
        assert result is not None


# ── Cost Estimation ────────────────────────────────────────────────────────


class TestEstimateCost:
    """Tests for cost estimation."""

    def test_basic_estimate(self, strategy: CostOptimizedStrategy) -> None:
        """Cost estimate should return reasonable values."""
        ctx = RoutingContext(task_type=TaskType.CODING, file_count=5)
        est = strategy.estimate_cost(TaskType.CODING, "deepseek-chat", ctx)

        assert est.input_tokens > 0
        assert est.output_tokens > 0
        assert est.total_cost_usd > 0
        # DeepSeek is very cheap — should be well under $0.01 for 5 files
        assert est.total_cost_usd < 0.01

    def test_more_files_costs_more(self, strategy: CostOptimizedStrategy) -> None:
        """More files should mean higher cost."""
        ctx_1 = RoutingContext(task_type=TaskType.CODING, file_count=1)
        ctx_10 = RoutingContext(task_type=TaskType.CODING, file_count=10)

        est_1 = strategy.estimate_cost(TaskType.CODING, "gpt-4", ctx_1)
        est_10 = strategy.estimate_cost(TaskType.CODING, "gpt-4", ctx_10)

        assert est_10.total_cost_usd > est_1.total_cost_usd

    def test_higher_complexity_costs_more(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """Higher complexity should mean more tokens and higher cost."""
        ctx_low = RoutingContext(
            task_type=TaskType.CODING, file_count=5, complexity=0.1
        )
        ctx_high = RoutingContext(
            task_type=TaskType.CODING, file_count=5, complexity=0.9
        )

        est_low = strategy.estimate_cost(TaskType.CODING, "gpt-4", ctx_low)
        est_high = strategy.estimate_cost(TaskType.CODING, "gpt-4", ctx_high)

        assert est_high.total_cost_usd > est_low.total_cost_usd

    def test_expensive_model_costs_more(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """GPT-4 should cost more than DeepSeek for the same task."""
        ctx = RoutingContext(task_type=TaskType.CODING, file_count=5)

        est_gpt4 = strategy.estimate_cost(TaskType.CODING, "gpt-4", ctx)
        est_ds = strategy.estimate_cost(TaskType.CODING, "deepseek-chat", ctx)

        assert est_gpt4.total_cost_usd > est_ds.total_cost_usd


# ── Model Ranking ──────────────────────────────────────────────────────────


class TestRankModels:
    """Tests for model ranking."""

    def test_returns_list(self, strategy: CostOptimizedStrategy) -> None:
        """rank_models should return a non-empty list."""
        ctx = RoutingContext(task_type=TaskType.CODING)
        ranked = strategy.rank_models(TaskType.CODING, ctx)
        assert len(ranked) > 0

    def test_sorted_by_cost_ascending(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """Models should be sorted cheapest first."""
        ctx = RoutingContext(task_type=TaskType.CODING, file_count=5)
        ranked = strategy.rank_models(TaskType.CODING, ctx)

        costs = [m.cost_estimate.total_cost_usd for m in ranked]
        assert costs == sorted(costs)

    def test_no_mock_models(self, strategy: CostOptimizedStrategy) -> None:
        """Mock models should be excluded from ranking."""
        ctx = RoutingContext(task_type=TaskType.CODING)
        ranked = strategy.rank_models(TaskType.CODING, ctx)

        model_ids = [m.model_id for m in ranked]
        assert "mock-gpt" not in model_ids

    def test_all_models_have_scores(
        self, strategy: CostOptimizedStrategy
    ) -> None:
        """Every ranked model should have valid score and quality."""
        ctx = RoutingContext(task_type=TaskType.CODING)
        ranked = strategy.rank_models(TaskType.CODING, ctx)

        for model in ranked:
            assert 0.0 <= model.score <= 1.0
            assert 0.0 <= model.quality_estimate <= 1.0
            assert model.cost_estimate.total_cost_usd >= 0


# ── Edge Cases ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_zero_files(self, strategy: CostOptimizedStrategy) -> None:
        """Zero file count should still work (uses minimum of 1)."""
        ctx = RoutingContext(task_type=TaskType.CODING, file_count=0)
        result = strategy.select_model(TaskType.CODING, ctx)
        assert result is not None

    def test_simple_query_task(self, strategy: CostOptimizedStrategy) -> None:
        """Simple query should pick a cheap model."""
        ctx = RoutingContext(task_type=TaskType.SIMPLE_QUERY, file_count=1)
        result = strategy.select_model(TaskType.SIMPLE_QUERY, ctx)
        assert result is not None

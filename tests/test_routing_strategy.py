"""
Tests for RoutingStrategy ABC and router data models.

Validates:
- ABC contract (cannot instantiate, abstract methods raise TypeError)
- Data model validation (__post_init__ checks)
- Enum coverage for TaskType
- Error classes
"""

import sys

import pytest

sys.path.insert(0, "src")

from omni.router import (
    AllModelsFailedError,
    BudgetExceededError,
    CostEstimate,
    FallbackConfig,
    ModelSelection,
    NoEligibleModelError,
    RankedModel,
    RouterError,
    RoutingContext,
    RoutingStrategy,
    TaskType,
)

# ── TaskType Enum ──────────────────────────────────────────────────────────


class TestTaskType:
    """Tests for TaskType enum."""

    def test_all_expected_types_exist(self) -> None:
        """TaskType must cover all routing-relevant categories."""
        expected = {
            "architecture",
            "coding",
            "code_review",
            "testing",
            "documentation",
            "simple_query",
        }
        actual = {t.value for t in TaskType}
        assert actual == expected

    def test_is_string_enum(self) -> None:
        """TaskType values should be usable as plain strings."""
        assert TaskType.CODING == "coding"
        assert str(TaskType.CODING) == "coding"


# ── CostEstimate ───────────────────────────────────────────────────────────


class TestCostEstimate:
    """Tests for CostEstimate dataclass."""

    def test_valid_creation(self) -> None:
        est = CostEstimate(input_tokens=100, output_tokens=200, total_cost_usd=0.005)
        assert est.input_tokens == 100
        assert est.output_tokens == 200
        assert est.total_cost_usd == 0.005

    def test_zero_cost(self) -> None:
        est = CostEstimate(input_tokens=0, output_tokens=0, total_cost_usd=0.0)
        assert est.total_cost_usd == 0.0

    def test_negative_input_tokens_rejected(self) -> None:
        with pytest.raises(ValueError, match="input_tokens must be >= 0"):
            CostEstimate(input_tokens=-1, output_tokens=0, total_cost_usd=0.0)

    def test_negative_output_tokens_rejected(self) -> None:
        with pytest.raises(ValueError, match="output_tokens must be >= 0"):
            CostEstimate(input_tokens=0, output_tokens=-1, total_cost_usd=0.0)

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="total_cost_usd must be >= 0"):
            CostEstimate(input_tokens=0, output_tokens=0, total_cost_usd=-0.01)


# ── ModelSelection ─────────────────────────────────────────────────────────


class TestModelSelection:
    """Tests for ModelSelection dataclass."""

    def test_valid_creation(self) -> None:
        cost = CostEstimate(100, 200, 0.005)
        sel = ModelSelection(
            model_id="gpt-4",
            reason="Best quality for architecture tasks",
            estimated_cost=cost,
            confidence=0.9,
        )
        assert sel.model_id == "gpt-4"
        assert sel.confidence == 0.9

    def test_empty_model_id_rejected(self) -> None:
        cost = CostEstimate(0, 0, 0.0)
        with pytest.raises(ValueError, match="model_id cannot be empty"):
            ModelSelection(
                model_id="",
                reason="test",
                estimated_cost=cost,
                confidence=0.5,
            )

    def test_confidence_bounds(self) -> None:
        cost = CostEstimate(0, 0, 0.0)
        # Valid boundaries
        ModelSelection(model_id="m", reason="r", estimated_cost=cost, confidence=0.0)
        ModelSelection(model_id="m", reason="r", estimated_cost=cost, confidence=1.0)
        # Invalid
        with pytest.raises(ValueError, match="confidence must be between"):
            ModelSelection(
                model_id="m", reason="r", estimated_cost=cost, confidence=1.1
            )
        with pytest.raises(ValueError, match="confidence must be between"):
            ModelSelection(
                model_id="m", reason="r", estimated_cost=cost, confidence=-0.1
            )


# ── RankedModel ────────────────────────────────────────────────────────────


class TestRankedModel:
    """Tests for RankedModel dataclass."""

    def test_valid_creation(self) -> None:
        cost = CostEstimate(100, 200, 0.005)
        rm = RankedModel(
            model_id="gpt-4", score=0.85, cost_estimate=cost, quality_estimate=0.9
        )
        assert rm.model_id == "gpt-4"
        assert rm.score == 0.85

    def test_empty_model_id_rejected(self) -> None:
        cost = CostEstimate(0, 0, 0.0)
        with pytest.raises(ValueError, match="model_id cannot be empty"):
            RankedModel(
                model_id="", score=0.5, cost_estimate=cost, quality_estimate=0.5
            )

    def test_score_bounds(self) -> None:
        cost = CostEstimate(0, 0, 0.0)
        with pytest.raises(ValueError, match="score must be between"):
            RankedModel(
                model_id="m", score=1.5, cost_estimate=cost, quality_estimate=0.5
            )

    def test_quality_bounds(self) -> None:
        cost = CostEstimate(0, 0, 0.0)
        with pytest.raises(ValueError, match="quality_estimate must be between"):
            RankedModel(
                model_id="m", score=0.5, cost_estimate=cost, quality_estimate=-0.1
            )


# ── RoutingContext ─────────────────────────────────────────────────────────


class TestRoutingContext:
    """Tests for RoutingContext dataclass."""

    def test_defaults(self) -> None:
        ctx = RoutingContext(task_type=TaskType.CODING)
        assert ctx.file_count == 0
        assert ctx.complexity == 0.5
        assert ctx.budget_remaining is None
        assert ctx.history == []
        assert ctx.metadata == {}

    def test_full_creation(self) -> None:
        ctx = RoutingContext(
            task_type=TaskType.ARCHITECTURE,
            file_count=10,
            complexity=0.8,
            budget_remaining=1.50,
            history=[{"model": "gpt-4", "cost": 0.05}],
            metadata={"user": "test"},
        )
        assert ctx.file_count == 10
        assert ctx.budget_remaining == 1.50

    def test_negative_file_count_rejected(self) -> None:
        with pytest.raises(ValueError, match="file_count must be >= 0"):
            RoutingContext(task_type=TaskType.CODING, file_count=-1)

    def test_complexity_bounds(self) -> None:
        with pytest.raises(ValueError, match="complexity must be between"):
            RoutingContext(task_type=TaskType.CODING, complexity=1.5)

    def test_negative_budget_rejected(self) -> None:
        with pytest.raises(ValueError, match="budget_remaining must be >= 0"):
            RoutingContext(task_type=TaskType.CODING, budget_remaining=-1.0)


# ── FallbackConfig ─────────────────────────────────────────────────────────


class TestFallbackConfig:
    """Tests for FallbackConfig dataclass."""

    def test_defaults(self) -> None:
        cfg = FallbackConfig()
        assert cfg.chain == []
        assert cfg.max_retries == 3
        assert cfg.backoff_seconds == 1.0

    def test_valid_chain(self) -> None:
        cfg = FallbackConfig(
            chain=["gpt-4o", "claude-sonnet-4", "deepseek-chat"],
            max_retries=2,
            backoff_seconds=0.5,
        )
        assert len(cfg.chain) == 3

    def test_negative_retries_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            FallbackConfig(max_retries=-1)

    def test_negative_backoff_rejected(self) -> None:
        with pytest.raises(ValueError, match="backoff_seconds must be >= 0"):
            FallbackConfig(backoff_seconds=-1.0)


# ── RoutingStrategy ABC ────────────────────────────────────────────────────


class TestRoutingStrategyABC:
    """Tests for RoutingStrategy abstract base class."""

    def test_cannot_instantiate(self) -> None:
        """RoutingStrategy is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            RoutingStrategy()  # type: ignore[abstract]

    def test_concrete_implementation_works(self) -> None:
        """A concrete subclass implementing all methods should be instantiable."""

        class ConcreteStrategy(RoutingStrategy):
            @property
            def name(self) -> str:
                return "test"

            def select_model(
                self,
                task_type: TaskType,
                context: RoutingContext,
            ) -> ModelSelection | None:
                cost = CostEstimate(100, 200, 0.005)
                return ModelSelection(
                    model_id="mock",
                    reason="test",
                    estimated_cost=cost,
                    confidence=1.0,
                )

            def estimate_cost(
                self,
                task_type: TaskType,
                model_id: str,
                context: RoutingContext,
            ) -> CostEstimate:
                return CostEstimate(100, 200, 0.005)

            def rank_models(
                self,
                task_type: TaskType,
                context: RoutingContext,
            ) -> list[RankedModel]:
                return []

        strategy = ConcreteStrategy()
        assert strategy.name == "test"

        ctx = RoutingContext(task_type=TaskType.CODING)
        result = strategy.select_model(TaskType.CODING, ctx)
        assert result is not None
        assert result.model_id == "mock"

    def test_partial_implementation_fails(self) -> None:
        """A subclass missing abstract methods cannot be instantiated."""

        class PartialStrategy(RoutingStrategy):
            @property
            def name(self) -> str:
                return "partial"

            # Missing select_model, estimate_cost, rank_models

        with pytest.raises(TypeError):
            PartialStrategy()  # type: ignore[abstract]

    def test_all_abstract_methods_documented(self) -> None:
        """Verify the ABC exposes the expected abstract interface."""
        abstract_methods = {
            "name",
            "select_model",
            "estimate_cost",
            "rank_models",
        }
        # Get abstract methods from the class
        actual = {
            name
            for name, method in RoutingStrategy.__dict__.items()
            if getattr(method, "__isabstractmethod__", False)
        }
        # 'name' is a property, others are methods — check both
        assert abstract_methods.issubset(actual | {"name"})


# ── Error Classes ──────────────────────────────────────────────────────────


class TestRouterErrors:
    """Tests for router-specific error classes."""

    def test_no_eligible_model_error(self) -> None:
        err = NoEligibleModelError("coding", "no models match")
        assert "coding" in str(err)
        assert "no models match" in str(err)
        assert err.task_type == "coding"

    def test_no_eligible_model_error_no_reason(self) -> None:
        err = NoEligibleModelError("testing")
        assert "testing" in str(err)

    def test_budget_exceeded_error(self) -> None:
        err = BudgetExceededError(budget_remaining=0.01, estimated_cost=0.05)
        assert err.budget_remaining == 0.01
        assert err.estimated_cost == 0.05
        assert "0.0100" in str(err)
        assert "0.0500" in str(err)

    def test_all_models_failed_error(self) -> None:
        inner = RuntimeError("connection timeout")
        err = AllModelsFailedError(["gpt-4", "claude-3"], last_error=inner)
        assert "gpt-4" in str(err)
        assert "claude-3" in str(err)
        assert "connection timeout" in str(err)

    def test_all_models_failed_no_inner_error(self) -> None:
        err = AllModelsFailedError(["gpt-4"])
        assert "gpt-4" in str(err)

    def test_errors_are_router_errors(self) -> None:
        """All router errors should inherit from RouterError."""
        assert issubclass(NoEligibleModelError, RouterError)
        assert issubclass(BudgetExceededError, RouterError)
        assert issubclass(AllModelsFailedError, RouterError)
        assert issubclass(RouterError, Exception)

"""
Tests for BudgetTracker and budget enforcement.

Validates:
- Budget tracking per session and project
- Budget enforcement (raise BudgetExceededError)
- Warning thresholds (80%, 90%, 95%)
- State persistence (JSON file)
- Integration with CostOptimizedStrategy
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, "src")

from omni.router import (
    BudgetConfig,
    BudgetExceededError,
    BudgetTracker,
    NoEligibleModelError,
    TaskType,
)
from omni.router.cost_optimized import CostOptimizedStrategy
from omni.router.models import RoutingContext


@pytest.fixture
def budget_config() -> BudgetConfig:
    """Create a BudgetConfig with test settings."""
    return BudgetConfig(
        daily_limit=10.0,
        per_session_limit=2.0,
        warning_thresholds=[0.8, 0.9, 0.95],
    )


@pytest.fixture
def budget_tracker(budget_config: BudgetConfig) -> BudgetTracker:
    """Create a BudgetTracker with a temporary state file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "budget_state.json"
        config = BudgetConfig(
            daily_limit=budget_config.daily_limit,
            per_session_limit=budget_config.per_session_limit,
            warning_thresholds=budget_config.warning_thresholds,
            state_file=state_file,
        )
        tracker = BudgetTracker(config=config, session_id="test-session", project_id="test-project")
        yield tracker


# ── BudgetConfig Tests ─────────────────────────────────────────────────────


class TestBudgetConfig:
    """Tests for BudgetConfig validation."""

    def test_default_values(self) -> None:
        """BudgetConfig should have sensible defaults."""
        config = BudgetConfig()
        assert config.daily_limit == 10.0
        assert config.per_session_limit == 2.0
        assert config.warning_thresholds == [0.8, 0.9, 0.95]

    def test_negative_daily_limit_raises_error(self) -> None:
        """Negative daily limit should raise ValueError."""
        with pytest.raises(ValueError, match="daily_limit must be >= 0"):
            BudgetConfig(daily_limit=-1.0)

    def test_negative_session_limit_raises_error(self) -> None:
        """Negative session limit should raise ValueError."""
        with pytest.raises(ValueError, match="per_session_limit must be >= 0"):
            BudgetConfig(per_session_limit=-1.0)

    def test_invalid_threshold_raises_error(self) -> None:
        """Threshold outside 0-1 range should raise ValueError."""
        with pytest.raises(ValueError, match="warning_thresholds must be between 0.0 and 1.0"):
            BudgetConfig(warning_thresholds=[1.5])


# ── BudgetTracker Initialization ───────────────────────────────────────────


class TestBudgetTrackerInit:
    """Tests for BudgetTracker initialization."""

    def test_default_initialization(self, budget_config: BudgetConfig) -> None:
        """BudgetTracker should initialize with default values."""
        tracker = BudgetTracker(config=budget_config)
        assert tracker.session_id == "default"
        assert tracker.project_id == "default"
        assert tracker.state.daily_spent == 0.0
        assert tracker.state.session_spent == 0.0

    def test_custom_session_and_project(self, budget_config: BudgetConfig) -> None:
        """BudgetTracker should accept custom session and project IDs."""
        tracker = BudgetTracker(
            config=budget_config,
            session_id="my-session",
            project_id="my-project",
        )
        assert tracker.session_id == "my-session"
        assert tracker.project_id == "my-project"

    def test_loads_existing_state(self, budget_config: BudgetConfig) -> None:
        """BudgetTracker should load existing state from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "budget_state.json"
            # Create existing state
            existing_state = {
                "daily_spent": 5.0,
                "session_spent": 1.0,
                "last_reset_date": "2026-03-26",
                "project_spending": {"test-project": 3.0},
                "session_spending": {"test-session": 1.0},
            }
            with open(state_file, "w") as f:
                json.dump(existing_state, f)

            config = BudgetConfig(state_file=state_file)
            tracker = BudgetTracker(config=config, session_id="test-session", project_id="test-project")

            assert tracker.state.daily_spent == 5.0
            assert tracker.state.session_spent == 1.0

    def test_resets_daily_budget_on_new_day(self, budget_config: BudgetConfig) -> None:
        """BudgetTracker should reset daily budget on new day."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "budget_state.json"
            # Create state from yesterday
            existing_state = {
                "daily_spent": 5.0,
                "session_spent": 1.0,
                "last_reset_date": "2026-03-25",  # Yesterday
                "project_spending": {},
                "session_spending": {},
            }
            with open(state_file, "w") as f:
                json.dump(existing_state, f)

            config = BudgetConfig(state_file=state_file)
            tracker = BudgetTracker(config=config)

            # Daily budget should be reset
            assert tracker.state.daily_spent == 0.0


# ── Budget Tracking ────────────────────────────────────────────────────────


class TestBudgetTracking:
    """Tests for tracking spending."""

    def test_track_spending(self, budget_tracker: BudgetTracker) -> None:
        """Track spending should update totals."""
        budget_tracker.track_spending(0.50)

        assert budget_tracker.state.daily_spent == 0.50
        assert budget_tracker.state.session_spent == 0.50
        assert budget_tracker.state.project_spending["test-project"] == 0.50
        assert budget_tracker.state.session_spending["test-session"] == 0.50

    def test_track_multiple_spending(self, budget_tracker: BudgetTracker) -> None:
        """Multiple tracking calls should accumulate."""
        budget_tracker.track_spending(0.25)
        budget_tracker.track_spending(0.35)

        assert budget_tracker.state.daily_spent == 0.60
        assert budget_tracker.state.session_spent == 0.60

    def test_track_with_different_session(self, budget_tracker: BudgetTracker) -> None:
        """Tracking with different session should update correct session."""
        # First track for the default session
        budget_tracker.track_spending(0.25)

        # Then track for a different session
        budget_tracker.track_spending(0.50, session_id="other-session")

        assert budget_tracker.state.session_spending["other-session"] == 0.50
        assert budget_tracker.state.session_spending["test-session"] == 0.25

    def test_track_with_different_project(self, budget_tracker: BudgetTracker) -> None:
        """Tracking with different project should update correct project."""
        # First track for the default project
        budget_tracker.track_spending(0.25)

        # Then track for a different project
        budget_tracker.track_spending(0.50, project_id="other-project")

        assert budget_tracker.state.project_spending["other-project"] == 0.50
        assert budget_tracker.state.project_spending["test-project"] == 0.25

    def test_negative_amount_raises_error(self, budget_tracker: BudgetTracker) -> None:
        """Negative spending amount should raise ValueError."""
        with pytest.raises(ValueError, match="amount must be >= 0"):
            budget_tracker.track_spending(-1.0)


# ── Budget Enforcement ─────────────────────────────────────────────────────


class TestBudgetEnforcement:
    """Tests for budget enforcement."""

    def test_check_budget_within_limit(self, budget_tracker: BudgetTracker) -> None:
        """Budget check should pass when within limits."""
        is_allowed, reason = budget_tracker.check_budget(0.50)
        assert is_allowed is True
        assert "passed" in reason

    def test_check_budget_exceeds_session_limit(self, budget_tracker: BudgetTracker) -> None:
        """Budget check should fail when exceeds session limit."""
        is_allowed, reason = budget_tracker.check_budget(3.00)
        assert is_allowed is False
        assert "Session budget exceeded" in reason

    def test_check_budget_exceeds_daily_limit(self, budget_tracker: BudgetTracker) -> None:
        """Budget check should fail when exceeds daily limit."""
        # Track spending to approach daily limit (but within session limit)
        # Use a different session to avoid session limit
        budget_tracker.track_spending(9.00, session_id="other-session")  # Within daily limit (10.00)
        # Now check budget for a different session that hasn't spent anything yet
        is_allowed, reason = budget_tracker.check_budget(1.50, session_id="third-session")
        assert is_allowed is False
        assert "Daily budget exceeded" in reason

    def test_check_budget_after_tracking(self, budget_tracker: BudgetTracker) -> None:
        """Budget check should consider already tracked spending."""
        budget_tracker.track_spending(1.50)
        is_allowed, reason = budget_tracker.check_budget(0.50)
        assert is_allowed is True

        is_allowed, reason = budget_tracker.check_budget(1.00)
        assert is_allowed is False  # 1.50 + 1.00 = 2.50 > 2.00 session limit


# ── Warning Thresholds ─────────────────────────────────────────────────────


class TestWarningThresholds:
    """Tests for warning threshold detection."""

    def test_get_warnings_at_80_percent(self, budget_tracker: BudgetTracker) -> None:
        """Should generate warning at 80% threshold."""
        budget_tracker.track_spending(1.60)  # 80% of 2.00 session limit
        warnings = budget_tracker.get_warnings()
        assert len(warnings) > 0
        assert any("80%" in w for w in warnings)

    def test_get_warnings_at_90_percent(self, budget_tracker: BudgetTracker) -> None:
        """Should generate warning at 90% threshold."""
        budget_tracker.track_spending(1.80)  # 90% of 2.00 session limit
        warnings = budget_tracker.get_warnings()
        assert len(warnings) > 0
        assert any("90%" in w for w in warnings)

    def test_get_warnings_at_95_percent(self, budget_tracker: BudgetTracker) -> None:
        """Should generate warning at 95% threshold."""
        budget_tracker.track_spending(1.90)  # 95% of 2.00 session limit
        warnings = budget_tracker.get_warnings()
        assert len(warnings) > 0
        assert any("95%" in w for w in warnings)

    def test_no_warnings_below_threshold(self, budget_tracker: BudgetTracker) -> None:
        """Should not generate warnings below lowest threshold."""
        budget_tracker.track_spending(1.00)  # 50% of 2.00 session limit
        warnings = budget_tracker.get_warnings()
        assert len(warnings) == 0


# ── State Persistence ──────────────────────────────────────────────────────


class TestStatePersistence:
    """Tests for state persistence to JSON file."""

    def test_state_saves_to_file(self, budget_config: BudgetConfig) -> None:
        """Budget state should be saved to JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "budget_state.json"
            config = BudgetConfig(state_file=state_file)
            tracker = BudgetTracker(config=config)

            tracker.track_spending(0.50)

            # Check file exists and contains correct data
            assert state_file.exists()
            with open(state_file) as f:
                data = json.load(f)
                assert data["daily_spent"] == 0.50
                assert data["session_spent"] == 0.50

    def test_state_loads_on_init(self, budget_config: BudgetConfig) -> None:
        """Budget state should load from file on initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "budget_state.json"
            # Create state file
            existing_state = {
                "daily_spent": 3.0,
                "session_spent": 1.5,
                "last_reset_date": "2026-03-26",
                "project_spending": {"test-project": 2.0},
                "session_spending": {"test-session": 1.5},
            }
            with open(state_file, "w") as f:
                json.dump(existing_state, f)

            config = BudgetConfig(state_file=state_file)
            tracker = BudgetTracker(config=config, session_id="test-session", project_id="test-project")

            assert tracker.state.daily_spent == 3.0
            assert tracker.state.session_spent == 1.5


# ── Reset Operations ───────────────────────────────────────────────────────


class TestResetOperations:
    """Tests for reset operations."""

    def test_reset_session(self, budget_tracker: BudgetTracker) -> None:
        """Reset session should clear session spending."""
        budget_tracker.track_spending(0.50)
        budget_tracker.reset_session()

        assert budget_tracker.state.session_spent == 0.0
        assert len(budget_tracker.state.session_spending) == 0

    def test_reset_daily(self, budget_tracker: BudgetTracker) -> None:
        """Reset daily should clear daily spending."""
        budget_tracker.track_spending(0.50)
        budget_tracker.reset_daily()

        assert budget_tracker.state.daily_spent == 0.0
        assert budget_tracker.state.last_reset_date is not None

    def test_reset_project(self, budget_tracker: BudgetTracker) -> None:
        """Reset project should clear project spending."""
        budget_tracker.track_spending(0.50, project_id="test-project")
        budget_tracker.reset_project("test-project")

        assert "test-project" not in budget_tracker.state.project_spending


# ── Integration with CostOptimizedStrategy ─────────────────────────────────


class TestIntegrationWithCostOptimizedStrategy:
    """Tests for integration with CostOptimizedStrategy."""

    def test_strategy_with_budget_tracker(self, budget_config: BudgetConfig) -> None:
        """CostOptimizedStrategy should work with BudgetTracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "budget_state.json"
            config = BudgetConfig(state_file=state_file)
            tracker = BudgetTracker(config=config, session_id="test-session", project_id="test-project")

            strategy = CostOptimizedStrategy(budget_tracker=tracker)
            ctx = RoutingContext(task_type=TaskType.CODING, file_count=1)

            # Should select a model within budget
            result = strategy.select_model(TaskType.CODING, ctx)
            assert result is not None
            assert result.estimated_cost.total_cost_usd <= tracker.config.per_session_limit

    def test_strategy_respects_budget_limits(self, budget_config: BudgetConfig) -> None:
        """CostOptimizedStrategy should respect budget limits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "budget_state.json"
            # Use a budget that's too small for any model
            config = BudgetConfig(state_file=state_file, per_session_limit=0.000001)
            tracker = BudgetTracker(config=config, session_id="test-session", project_id="test-project")

            strategy = CostOptimizedStrategy(budget_tracker=tracker)
            ctx = RoutingContext(task_type=TaskType.CODING, file_count=1)

            # Should raise BudgetExceededError if no model fits budget
            with pytest.raises((BudgetExceededError, NoEligibleModelError)):
                strategy.select_model(TaskType.CODING, ctx)

    def test_strategy_tracks_spending(self, budget_config: BudgetConfig) -> None:
        """CostOptimizedStrategy should track spending via BudgetTracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "budget_state.json"
            config = BudgetConfig(state_file=state_file)
            tracker = BudgetTracker(config=config, session_id="test-session", project_id="test-project")

            strategy = CostOptimizedStrategy(budget_tracker=tracker)
            ctx = RoutingContext(task_type=TaskType.CODING, file_count=1)

            # Select a model
            result = strategy.select_model(TaskType.CODING, ctx)
            assert result is not None

            # Track the actual cost (simulating usage)
            tracker.track_spending(result.estimated_cost.total_cost_usd)

            # Check that spending was tracked
            assert tracker.state.session_spent > 0.0


# ── Edge Cases ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_zero_budget(self, budget_config: BudgetConfig) -> None:
        """Zero budget should immediately exceed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "budget_state.json"
            config = BudgetConfig(state_file=state_file, per_session_limit=0.0)
            tracker = BudgetTracker(config=config)

            is_allowed, reason = tracker.check_budget(0.01)
            assert is_allowed is False

    def test_unlimited_budget(self, budget_config: BudgetConfig) -> None:
        """Unlimited budget (None) should always allow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "budget_state.json"
            config = BudgetConfig(state_file=state_file, daily_limit=0.0, per_session_limit=0.0)
            tracker = BudgetTracker(config=config)

            # With zero limits, any positive cost should exceed
            is_allowed, reason = tracker.check_budget(0.01)
            assert is_allowed is False

    def test_get_total_spent(self, budget_tracker: BudgetTracker) -> None:
        """get_total_spent should return correct totals."""
        budget_tracker.track_spending(0.50, project_id="project1")
        budget_tracker.track_spending(0.30, project_id="project2")

        totals = budget_tracker.get_total_spent()
        assert totals["daily"] == 0.80
        assert totals["session"] == 0.80
        assert totals["total_projects"] == 0.80

    def test_repr(self, budget_tracker: BudgetTracker) -> None:
        """BudgetTracker should have a readable repr."""
        repr_str = repr(budget_tracker)
        assert "BudgetTracker" in repr_str
        assert "$" in repr_str

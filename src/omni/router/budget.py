"""
Budget Tracker for Omni-LLM Router.

Tracks spending per session/project and enforces budget limits.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class BudgetConfig:
    """Configuration for budget limits and thresholds."""

    daily_limit: float = 10.0  # USD per day
    per_session_limit: float = 2.0  # USD per session
    warning_thresholds: list[float] = field(default_factory=lambda: [0.8, 0.9, 0.95])
    state_file: Path = Path.home() / ".omni-llm" / "budget_state.json"

    def __post_init__(self) -> None:
        """Validate budget config fields."""
        if self.daily_limit < 0:
            raise ValueError(f"daily_limit must be >= 0, got {self.daily_limit}")
        if self.per_session_limit < 0:
            raise ValueError(
                f"per_session_limit must be >= 0, got {self.per_session_limit}"
            )
        for threshold in self.warning_thresholds:
            if not 0.0 <= threshold <= 1.0:
                raise ValueError(
                    f"warning_thresholds must be between 0.0 and 1.0, got {threshold}"
                )


@dataclass
class BudgetState:
    """Persisted budget state."""

    daily_spent: float = 0.0
    session_spent: float = 0.0
    last_reset_date: str = field(default_factory=lambda: datetime.now().date().isoformat())
    project_spending: dict[str, float] = field(default_factory=dict)
    session_spending: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "daily_spent": self.daily_spent,
            "session_spent": self.session_spent,
            "last_reset_date": self.last_reset_date,
            "project_spending": self.project_spending,
            "session_spending": self.session_spending,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetState":
        """Create BudgetState from dictionary."""
        return cls(
            daily_spent=data.get("daily_spent", 0.0),
            session_spent=data.get("session_spent", 0.0),
            last_reset_date=data.get("last_reset_date", datetime.now().date().isoformat()),
            project_spending=data.get("project_spending", {}),
            session_spending=data.get("session_spending", {}),
        )


class BudgetTracker:
    """
    Tracks spending and enforces budget limits.

    Features:
    - Per-session and per-day budget tracking
    - Project-based spending tracking
    - Warning thresholds (80%, 90%, 95%)
    - State persistence to JSON file
    - Budget exceeded error raising
    """

    def __init__(
        self,
        config: BudgetConfig | None = None,
        session_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """
        Initialize budget tracker.

        Args:
            config: Budget configuration (uses defaults if None)
            session_id: Current session identifier
            project_id: Current project identifier
        """
        self.config = config or BudgetConfig()
        self.session_id = session_id or "default"
        self.project_id = project_id or "default"
        self.state = BudgetState()
        self._load_state()

    def _load_state(self) -> None:
        """Load budget state from file if it exists."""
        if self.config.state_file.exists():
            try:
                with open(self.config.state_file) as f:
                    data = json.load(f)
                    self.state = BudgetState.from_dict(data)

                # Check if we need to reset daily budget
                today = datetime.now().date().isoformat()
                if self.state.last_reset_date != today:
                    self.state.daily_spent = 0.0
                    self.state.last_reset_date = today
                    self._save_state()
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                # If state file is corrupted, start fresh
                print(f"Warning: Could not load budget state: {e}")
                self.state = BudgetState()

    def _save_state(self) -> None:
        """Save budget state to file."""
        self.config.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.state_file, "w") as f:
            json.dump(self.state.to_dict(), f, indent=2)

    def _check_thresholds(self, spent: float, limit: float) -> list[float]:
        """Check which warning thresholds have been crossed."""
        if limit <= 0:
            return []

        ratio = spent / limit
        crossed = [t for t in self.config.warning_thresholds if ratio >= t]
        return crossed

    def _get_remaining(self, spent: float, limit: float) -> float:
        """Calculate remaining budget."""
        return max(0.0, limit - spent)

    def track_spending(
        self,
        amount: float,
        session_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """
        Track spending for a request.

        Args:
            amount: Cost in USD
            session_id: Session identifier (uses instance session_id if None)
            project_id: Project identifier (uses instance project_id if None)
        """
        if amount < 0:
            raise ValueError(f"amount must be >= 0, got {amount}")

        session = session_id or self.session_id
        project = project_id or self.project_id

        # Update daily spending (always)
        self.state.daily_spent += amount

        # Update project spending
        if project not in self.state.project_spending:
            self.state.project_spending[project] = 0.0
        self.state.project_spending[project] += amount

        # Update session spending
        if session not in self.state.session_spending:
            self.state.session_spending[session] = 0.0
        self.state.session_spending[session] += amount

        # Update session spent only for the current session
        if session_id is None or session_id == self.session_id:
            self.state.session_spent = self.state.session_spending.get(session, 0.0)

        self._save_state()

    def check_budget(
        self,
        estimated_cost: float,
        session_id: str | None = None,
        project_id: str | None = None,
    ) -> tuple[bool, str]:
        """
        Check if budget allows for the estimated cost.

        Args:
            estimated_cost: Cost to check against budget
            session_id: Session identifier (uses instance session_id if None)
            project_id: Project identifier (uses instance project_id if None)

        Returns:
            Tuple of (is_allowed, reason)
        """
        session = session_id or self.session_id

        # Check session budget
        session_remaining = self._get_remaining(
            self.state.session_spending.get(session, 0.0),
            self.config.per_session_limit
        )
        if estimated_cost > session_remaining:
            return False, f"Session budget exceeded: need ${estimated_cost:.4f}, remaining ${session_remaining:.4f}"

        # Check daily budget
        daily_remaining = self._get_remaining(self.state.daily_spent, self.config.daily_limit)
        if estimated_cost > daily_remaining:
            return False, f"Daily budget exceeded: need ${estimated_cost:.4f}, remaining ${daily_remaining:.4f}"

        return True, "Budget check passed"

    def get_budget_status(self) -> dict[str, Any]:
        """Get current budget status."""
        session_spent = self.state.session_spending.get(self.session_id, 0.0)
        project_spent = self.state.project_spending.get(self.project_id, 0.0)

        session_remaining = self._get_remaining(session_spent, self.config.per_session_limit)
        daily_remaining = self._get_remaining(self.state.daily_spent, self.config.daily_limit)

        session_thresholds = self._check_thresholds(session_spent, self.config.per_session_limit)
        daily_thresholds = self._check_thresholds(self.state.daily_spent, self.config.daily_limit)

        return {
            "session": {
                "spent": session_spent,
                "limit": self.config.per_session_limit,
                "remaining": session_remaining,
                "thresholds_crossed": session_thresholds,
            },
            "daily": {
                "spent": self.state.daily_spent,
                "limit": self.config.daily_limit,
                "remaining": daily_remaining,
                "thresholds_crossed": daily_thresholds,
            },
            "project": {
                "id": self.project_id,
                "spent": project_spent,
            },
            "session_id": self.session_id,
        }

    def get_warnings(self) -> list[str]:
        """Get warning messages for crossed thresholds."""
        warnings = []
        status = self.get_budget_status()

        # Session warnings
        for threshold in status["session"]["thresholds_crossed"]:
            warnings.append(
                f"Session budget at {threshold*100:.0f}%: "
                f"${status['session']['spent']:.4f}/${status['session']['limit']:.4f}"
            )

        # Daily warnings
        for threshold in status["daily"]["thresholds_crossed"]:
            warnings.append(
                f"Daily budget at {threshold*100:.0f}%: "
                f"${status['daily']['spent']:.4f}/${status['daily']['limit']:.4f}"
            )

        return warnings

    def reset_session(self) -> None:
        """Reset session spending (e.g., for new session)."""
        self.state.session_spent = 0.0
        self.state.session_spending.clear()
        self._save_state()

    def reset_daily(self) -> None:
        """Reset daily spending (e.g., for new day)."""
        self.state.daily_spent = 0.0
        self.state.last_reset_date = datetime.now().date().isoformat()
        self._save_state()

    def reset_project(self, project_id: str | None = None) -> None:
        """Reset project spending."""
        project = project_id or self.project_id
        if project in self.state.project_spending:
            del self.state.project_spending[project]
        self._save_state()

    def get_total_spent(self) -> dict[str, float]:
        """Get total spending across all tracked categories."""
        return {
            "daily": self.state.daily_spent,
            "session": self.state.session_spent,
            "total_projects": sum(self.state.project_spending.values()),
            "total_sessions": sum(self.state.session_spending.values()),
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        status = self.get_budget_status()
        return (
            f"BudgetTracker("
            f"session=${status['session']['spent']:.4f}/${status['session']['limit']:.4f}, "
            f"daily=${status['daily']['spent']:.4f}/${status['daily']['limit']:.4f})"
        )

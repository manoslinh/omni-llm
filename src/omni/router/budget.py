"""
Budget Tracker for Omni-LLM Router.

Tracks spending per session/project and enforces budget limits.

All monetary values use Decimal for financial precision.
Thread-safe for concurrent access with file locking for state persistence.
"""

import fcntl
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default config path relative to repo
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "budget.yaml"


class _Money(Decimal):
    """Decimal subclass that compares equal to equivalent float values.

    This preserves Decimal precision internally while maintaining
    backward compatibility with tests and consumers that compare
    state fields directly with float literals.

    Arithmetic operations return _Money to preserve the type.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, float):
            return float(self) == other
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return super().__hash__()

    def _wrap(self, result: Decimal) -> "_Money":
        """Convert arithmetic result back to _Money."""
        return _Money(str(result))

    def __add__(self, other: object) -> "_Money":
        return self._wrap(super().__add__(other))  # type: ignore[operator]

    def __radd__(self, other: object) -> "_Money":
        return self._wrap(super().__radd__(other))  # type: ignore[operator]

    def __sub__(self, other: object) -> "_Money":
        return self._wrap(super().__sub__(other))  # type: ignore[operator]

    def __rsub__(self, other: object) -> "_Money":
        return self._wrap(super().__rsub__(other))  # type: ignore[operator]

    def __mul__(self, other: object) -> "_Money":
        return self._wrap(super().__mul__(other))  # type: ignore[operator]

    def __rmul__(self, other: object) -> "_Money":
        return self._wrap(super().__rmul__(other))  # type: ignore[operator]

    def __truediv__(self, other: object) -> "_Money":
        return self._wrap(super().__truediv__(other))  # type: ignore[operator]

    def __neg__(self) -> "_Money":
        return self._wrap(super().__neg__())

    def __abs__(self) -> "_Money":
        return self._wrap(super().__abs__())


def _to_decimal(value: float | str | Decimal | None) -> _Money | None:
    """Convert a value to _Money (Decimal subclass) safely.

    Uses str() intermediary to avoid float precision artifacts.
    Returns None for None input (unlimited budget).
    """
    if value is None:
        return None
    if isinstance(value, _Money):
        return value
    # str() avoids: Decimal(0.1) → Decimal('0.1000000000000000055511151231...')
    return _Money(str(value))


def _decimal_to_float(value: Decimal | None) -> float | None:
    """Convert Decimal back to float for API backward compatibility."""
    if value is None:
        return None
    return float(value)


@dataclass
class BudgetConfig:
    """Configuration for budget limits and thresholds.

    Attributes:
        daily_limit: Maximum USD spend per day. None = unlimited.
        per_session_limit: Maximum USD spend per session. None = unlimited.
        warning_thresholds: Fractions of limit at which to generate warnings.
        state_file: Path to JSON state persistence file.
    """

    daily_limit: float | None = 10.0  # USD per day; None = unlimited
    per_session_limit: float | None = 2.0  # USD per session; None = unlimited
    warning_thresholds: list[float] = field(default_factory=lambda: [0.8, 0.9, 0.95])
    state_file: Path = Path.home() / ".omni-llm" / "budget_state.json"

    def __post_init__(self) -> None:
        """Validate budget config fields."""
        if self.daily_limit is not None and self.daily_limit < 0:
            raise ValueError(f"daily_limit must be >= 0 or None, got {self.daily_limit}")
        if self.per_session_limit is not None and self.per_session_limit < 0:
            raise ValueError(
                f"per_session_limit must be >= 0 or None, got {self.per_session_limit}"
            )
        for threshold in self.warning_thresholds:
            if not 0.0 <= threshold <= 1.0:
                raise ValueError(
                    f"warning_thresholds must be between 0.0 and 1.0, got {threshold}"
                )

    @classmethod
    def from_yaml(
        cls,
        config_path: str | Path | None = None,
    ) -> "BudgetConfig":
        """Load BudgetConfig from a YAML file.

        Args:
            config_path: Path to budget.yaml. Uses default if None.

        Returns:
            BudgetConfig instance loaded from YAML.
        """
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required for YAML config loading. "
                "Install with: pip install pyyaml"
            ) from None

        path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH

        if not path.exists():
            raise FileNotFoundError(f"Budget config file not found: {path}")

        with open(path) as f:
            raw = f.read()

        # Substitute environment variables
        import os
        import re

        def _replace_env(match: re.Match[str]) -> str:
            var_name = match.group(1) or match.group(2)
            return os.getenv(var_name, match.group(0)) or match.group(0)

        pattern = r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)"
        raw = re.sub(pattern, _replace_env, raw)

        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {path}: {e}") from e

        if not isinstance(data, dict):
            raise ValueError(f"YAML root must be a mapping, got {type(data)}")

        # Extract fields with fallbacks
        limits = data.get("limits", {})
        state = data.get("state", {})
        warning_thrs = data.get("warning_thresholds", [0.8, 0.9, 0.95])

        # Handle unlimited: YAML can use null/None for unlimited
        daily_limit = limits.get("daily_limit", 10.0)
        per_session_limit = limits.get("per_session_limit", 2.0)

        state_file_raw = state.get("state_file", None)
        if state_file_raw:
            state_file = Path.home() / state_file_raw
        else:
            state_file = Path.home() / ".omni-llm" / "budget_state.json"

        return cls(
            daily_limit=daily_limit,
            per_session_limit=per_session_limit,
            warning_thresholds=warning_thrs,
            state_file=state_file,
        )


@dataclass
class BudgetState:
    """Persisted budget state.

    All monetary values are stored as Decimal strings internally
    for JSON serialization. The `daily_spent` and session/project
    spending dicts use Decimal for precision.
    """

    daily_spent: _Money = field(default_factory=lambda: _Money("0"))
    last_reset_date: str = field(default_factory=lambda: datetime.now().date().isoformat())
    project_spending: dict[str, _Money] = field(default_factory=dict)
    session_spending: dict[str, _Money] = field(default_factory=dict)

    # Legacy field: kept for backward-compatible deserialization.
    # Current code derives session spending from session_spending dict.
    _legacy_session_spent: _Money = field(default_factory=lambda: _Money("0"))

    @property
    def session_spent(self) -> _Money:
        """Backward-compatible access to session spending.

        Returns the legacy value. For current code, use
        session_spending[session_id] instead.
        """
        return self._legacy_session_spent

    @session_spent.setter
    def session_spent(self, value: _Money | Decimal) -> None:
        """Backward-compatible setter for session spending."""
        if not isinstance(value, _Money):
            value = _Money(str(value))
        self._legacy_session_spent = value

    def __eq__(self, other: object) -> bool:
        """Compare BudgetState, supporting Decimal-to-float comparison."""
        if not isinstance(other, BudgetState):
            return NotImplemented

        def _eq(a: Any, b: Any) -> bool:
            if isinstance(a, dict) and isinstance(b, dict):
                return bool(a == b)
            if isinstance(a, Decimal) and isinstance(b, float):
                return float(a) == b
            return bool(a == b)

        return (
            _eq(self.daily_spent, other.daily_spent)
            and self.last_reset_date == other.last_reset_date
            and self.project_spending == other.project_spending
            and self.session_spending == other.session_spending
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Decimals are serialized as floats for backward compatibility
        with consumers that expect numeric JSON values.
        """
        return {
            "daily_spent": float(self.daily_spent),
            "session_spent": float(self._legacy_session_spent),
            "last_reset_date": self.last_reset_date,
            "project_spending": {k: float(v) for k, v in self.project_spending.items()},
            "session_spending": {k: float(v) for k, v in self.session_spending.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetState":
        """Create BudgetState from dictionary.

        Handles both old format (float values) and new format (string values).
        """
        def _parse_decimal(val: Any) -> _Money:
            if isinstance(val, (int, float)):
                return _Money(str(val))
            try:
                return _Money(val)
            except (InvalidOperation, TypeError):
                return _Money("0")

        return cls(
            daily_spent=_parse_decimal(data.get("daily_spent", 0)),
            last_reset_date=data.get(
                "last_reset_date", datetime.now().date().isoformat()
            ),
            project_spending={
                k: _parse_decimal(v) for k, v in data.get("project_spending", {}).items()
            },
            session_spending={
                k: _parse_decimal(v) for k, v in data.get("session_spending", {}).items()
            },
            _legacy_session_spent=_parse_decimal(data.get("session_spent", 0)),
        )


class BudgetTracker:
    """
    Tracks spending and enforces budget limits.

    Features:
    - Per-session and per-day budget tracking
    - Project-based spending tracking
    - Warning thresholds (80%, 90%, 95%)
    - Thread-safe state persistence to JSON file
    - Atomic file writes with corruption recovery
    - Unlimited budget support (None = no limit)
    - Decimal precision for financial accuracy

    Thread Safety:
        All public methods are thread-safe. Internal state mutations
        are protected by a threading.Lock. File I/O uses fcntl.flock
        to prevent corruption from concurrent process access.
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
        self._lock = threading.Lock()
        self._load_state()

    # ── Internal helpers ───────────────────────────────────────────────

    def _decimal_limit(self, limit: float | None) -> Decimal | None:
        """Convert a config limit (float|None) to Decimal|None."""
        if limit is None:
            return None
        return _to_decimal(limit)

    # Lock timeout in seconds for cross-process coordination
    _LOCK_TIMEOUT: float = 5.0
    # Retry interval for non-blocking lock acquisition (seconds)
    _LOCK_RETRY_INTERVAL: float = 0.05

    def _load_state(self) -> None:
        """Load budget state from file if it exists.

        Handles corrupted files by backing them up and starting fresh.
        Uses the same .lock file as _save_state for cross-process coordination.
        """
        if not self.config.state_file.exists():
            return

        with self._lock:
            lock_path = self.config.state_file.with_suffix(".lock")
            lock_fd = None
            try:
                # Ensure lock file exists
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDONLY, 0o644)
                # Acquire shared lock with timeout to prevent deadlocks
                self._acquire_lock(lock_fd, fcntl.LOCK_SH)
                try:
                    with open(self.config.state_file) as f:
                        raw = f.read()
                finally:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)

                data = json.loads(raw)
                self.state = BudgetState.from_dict(data)

                # Check if we need to reset daily budget
                today = datetime.now().date().isoformat()
                if self.state.last_reset_date != today:
                    self.state.daily_spent = _Money("0")
                    self.state.last_reset_date = today
                    self._save_state_unlocked()

            except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
                # Backup corrupted file and start fresh
                logger.warning("Could not load budget state: %s — starting fresh", e)
                try:
                    backup = self.config.state_file.with_suffix(".corrupted.json")
                    if self.config.state_file.exists():
                        os.replace(self.config.state_file, backup)
                        logger.info("Backed up corrupted state to %s", backup)
                except OSError:
                    pass  # Best effort backup
                self.state = BudgetState()
            finally:
                if lock_fd is not None:
                    os.close(lock_fd)

    def _acquire_lock(self, lock_fd: int, lock_type: int) -> None:
        """Acquire a file lock with timeout and retry.

        Args:
            lock_fd: File descriptor of the lock file.
            lock_type: fcntl.LOCK_SH (shared/reader) or fcntl.LOCK_EX (exclusive/writer).

        Raises:
            TimeoutError: If lock cannot be acquired within _LOCK_TIMEOUT.
        """
        import time

        deadline = time.monotonic() + self._LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(lock_fd, lock_type | fcntl.LOCK_NB)
                return  # Lock acquired
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire file lock within {self._LOCK_TIMEOUT}s"
                    ) from None
                time.sleep(self._LOCK_RETRY_INTERVAL)

    def _save_state_unlocked(self) -> None:
        """Save state to file with atomic write and file locking.

        Uses temp file + rename for crash safety.
        Uses a dedicated .lock file for cross-process coordination.
        Writers use LOCK_EX (exclusive) to coordinate with readers (LOCK_SH).
        """
        self.config.state_file.parent.mkdir(parents=True, exist_ok=True)
        state_dir = self.config.state_file.parent
        lock_path = self.config.state_file.with_suffix(".lock")
        payload = json.dumps(self.state.to_dict(), indent=2)

        # Cross-process file locking via dedicated lock file
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            self._acquire_lock(lock_fd, fcntl.LOCK_EX)
            try:
                # Atomic write: temp file + rename
                fd, tmp_path = tempfile.mkstemp(
                    dir=state_dir, prefix=".budget_", suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, "w") as f:
                        f.write(payload)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp_path, self.config.state_file)
                except BaseException:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)

    def _save_state(self) -> None:
        """Thread-safe state save."""
        with self._lock:
            self._save_state_unlocked()

    def _check_thresholds(
        self, spent: Decimal, limit: Decimal | None
    ) -> list[float]:
        """Check which warning thresholds have been crossed."""
        if limit is None or limit <= 0:
            return []
        ratio = float(spent / limit)
        return [t for t in self.config.warning_thresholds if ratio >= t]

    def _get_remaining(
        self, spent: Decimal, limit: Decimal | None
    ) -> Decimal | None:
        """Calculate remaining budget.

        Returns None if limit is None (unlimited).
        """
        if limit is None:
            return None
        remaining = limit - spent
        return remaining if remaining > _Money("0") else _Money("0")

    # ── Public API ─────────────────────────────────────────────────────

    def track_spending(
        self,
        amount: float | Decimal,
        session_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """
        Track spending for a request.

        Args:
            amount: Cost in USD (float or Decimal)
            session_id: Session identifier (uses instance session_id if None)
            project_id: Project identifier (uses instance project_id if None)
        """
        amount_d = _to_decimal(amount)
        if amount_d is None or amount_d < 0:
            raise ValueError(f"amount must be >= 0, got {amount}")

        session = session_id or self.session_id
        project = project_id or self.project_id

        with self._lock:
            # Update daily spending
            self.state.daily_spent += amount_d

            # Update project spending
            if project not in self.state.project_spending:
                self.state.project_spending[project] = _Money("0")
            self.state.project_spending[project] += amount_d

            # Update session spending
            if session not in self.state.session_spending:
                self.state.session_spending[session] = _Money("0")
            self.state.session_spending[session] += amount_d

            # Update legacy field for backward compatibility
            if session_id is None or session_id == self.session_id:
                self.state._legacy_session_spent = self.state.session_spending.get(
                    session, _Money("0")
                )

            self._save_state_unlocked()

    def check_budget(
        self,
        estimated_cost: float | Decimal,
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
        cost_d = _to_decimal(estimated_cost)
        if cost_d is None:
            cost_d = _Money("0")

        session = session_id or self.session_id

        with self._lock:
            # Check session budget
            session_limit = self._decimal_limit(self.config.per_session_limit)
            session_spent = self.state.session_spending.get(session, _Money("0"))
            session_remaining = self._get_remaining(session_spent, session_limit)

            if session_remaining is not None and cost_d > session_remaining:
                return (
                    False,
                    f"Session budget exceeded: need ${float(cost_d):.4f}, "
                    f"remaining ${float(session_remaining):.4f}",
                )

            # Check daily budget
            daily_limit = self._decimal_limit(self.config.daily_limit)
            daily_remaining = self._get_remaining(self.state.daily_spent, daily_limit)

            if daily_remaining is not None and cost_d > daily_remaining:
                return (
                    False,
                    f"Daily budget exceeded: need ${float(cost_d):.4f}, "
                    f"remaining ${float(daily_remaining):.4f}",
                )

        return True, "Budget check passed"

    def get_budget_status(self) -> dict[str, Any]:
        """Get current budget status.

        Returns float values for backward compatibility.
        None limits are reported as float('inf') for remaining.
        """
        with self._lock:
            session_limit = self._decimal_limit(self.config.per_session_limit)
            daily_limit = self._decimal_limit(self.config.daily_limit)

            session_spent = self.state.session_spending.get(
                self.session_id, _Money("0")
            )
            project_spent = self.state.project_spending.get(
                self.project_id, _Money("0")
            )

            session_remaining = self._get_remaining(session_spent, session_limit)
            daily_remaining = self._get_remaining(self.state.daily_spent, daily_limit)

            session_thresholds = self._check_thresholds(session_spent, session_limit)
            daily_thresholds = self._check_thresholds(
                self.state.daily_spent, daily_limit
            )

        return {
            "session": {
                "spent": float(session_spent),
                "limit": _decimal_to_float(session_limit),
                "remaining": (
                    float(session_remaining)
                    if session_remaining is not None
                    else float("inf")
                ),
                "thresholds_crossed": session_thresholds,
            },
            "daily": {
                "spent": float(self.state.daily_spent),
                "limit": _decimal_to_float(daily_limit),
                "remaining": (
                    float(daily_remaining)
                    if daily_remaining is not None
                    else float("inf")
                ),
                "thresholds_crossed": daily_thresholds,
            },
            "project": {
                "id": self.project_id,
                "spent": float(project_spent),
            },
            "session_id": self.session_id,
        }

    def get_warnings(self) -> list[str]:
        """Get warning messages for crossed thresholds."""
        status = self.get_budget_status()
        warnings = []

        for threshold in status["session"]["thresholds_crossed"]:
            warnings.append(
                f"Session budget at {threshold * 100:.0f}%: "
                f"${status['session']['spent']:.4f}/"
                f"${status['session']['limit']:.4f}"
            )

        for threshold in status["daily"]["thresholds_crossed"]:
            warnings.append(
                f"Daily budget at {threshold * 100:.0f}%: "
                f"${status['daily']['spent']:.4f}/"
                f"${status['daily']['limit']:.4f}"
            )

        return warnings

    def reset_session(self) -> None:
        """Reset session spending (e.g., for new session)."""
        with self._lock:
            self.state._legacy_session_spent = _Money("0")
            self.state.session_spending.clear()
            self._save_state_unlocked()

    def reset_daily(self) -> None:
        """Reset daily spending (e.g., for new day)."""
        with self._lock:
            self.state.daily_spent = _Money("0")
            self.state.last_reset_date = datetime.now().date().isoformat()
            self._save_state_unlocked()

    def reset_project(self, project_id: str | None = None) -> None:
        """Reset project spending."""
        project = project_id or self.project_id
        with self._lock:
            if project in self.state.project_spending:
                del self.state.project_spending[project]
            self._save_state_unlocked()

    def get_total_spent(self) -> dict[str, float]:
        """Get total spending across all tracked categories.

        Returns float values for backward compatibility.
        """
        with self._lock:
            return {
                "daily": float(self.state.daily_spent),
                "session": float(
                    self.state.session_spending.get(self.session_id, _Money("0"))
                ),
                "total_projects": float(sum(self.state.project_spending.values())),
                "total_sessions": float(sum(self.state.session_spending.values())),
            }

    def __repr__(self) -> str:
        """String representation for debugging."""
        status = self.get_budget_status()
        session_limit = status["session"]["limit"]
        daily_limit = status["daily"]["limit"]
        session_str = (
            f"${status['session']['spent']:.4f}/${session_limit:.4f}"
            if session_limit is not None
            else f"${status['session']['spent']:.4f}/unlimited"
        )
        daily_str = (
            f"${status['daily']['spent']:.4f}/${daily_limit:.4f}"
            if daily_limit is not None
            else f"${status['daily']['spent']:.4f}/unlimited"
        )
        return f"BudgetTracker(session={session_str}, daily={daily_str})"

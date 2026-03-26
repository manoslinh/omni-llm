"""
Router-specific exceptions.

Defines error types for routing failures, budget enforcement,
and model eligibility issues.
"""


class RouterError(Exception):
    """Base exception for router errors."""
    pass


class NoEligibleModelError(RouterError):
    """No model matches the task requirements."""

    def __init__(self, task_type: str, reason: str = "") -> None:
        self.task_type = task_type
        self.reason = reason
        message = f"No eligible model for task type '{task_type}'"
        if reason:
            message += f": {reason}"
        super().__init__(message)


class BudgetExceededError(RouterError):
    """Budget is insufficient for the requested operation."""

    def __init__(
        self,
        budget_remaining: float,
        estimated_cost: float,
    ) -> None:
        self.budget_remaining = budget_remaining
        self.estimated_cost = estimated_cost
        super().__init__(
            f"Budget exceeded: remaining ${budget_remaining:.4f}, "
            f"need ${estimated_cost:.4f}"
        )


class AllModelsFailedError(RouterError):
    """All models in the fallback chain failed."""

    def __init__(self, model_ids: list[str], last_error: Exception | None = None) -> None:
        self.model_ids = model_ids
        self.last_error = last_error
        models_str = ", ".join(model_ids)
        message = f"All models failed: [{models_str}]"
        if last_error:
            message += f" — last error: {last_error}"
        super().__init__(message)

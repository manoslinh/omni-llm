"""
Routing Strategy Abstract Base Class.

Defines the interface that all routing strategies must implement.
Strategies are pluggable — the ModelRouter delegates model selection
to whichever strategy is configured.
"""

from abc import ABC, abstractmethod

from .models import (
    CostEstimate,
    ModelSelection,
    RankedModel,
    RoutingContext,
    TaskType,
)


class RoutingStrategy(ABC):
    """
    Abstract base class for model routing strategies.

    A routing strategy decides which model to use for a given task,
    based on task type, context, budget, and model capabilities.

    Implementations must provide:
    - select_model: choose the best model for a task
    - estimate_cost: predict the cost of using a model for a task
    - rank_models: order all candidate models by suitability
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Human-readable name of this strategy.

        Returns:
            Strategy name (e.g., 'cost_optimized', 'quality_first')
        """
        ...

    @abstractmethod
    def select_model(
        self,
        task_type: TaskType,
        context: RoutingContext,
    ) -> ModelSelection | None:
        """
        Select the best model for the given task and context.

        Args:
            task_type: The type of task to route
            context: Routing context including budget, complexity, etc.

        Returns:
            ModelSelection with the chosen model and reasoning,
            or None if no suitable model is found (e.g., budget exhausted)

        Raises:
            NoEligibleModelError: If no model matches the task requirements
            BudgetExceededError: If budget is insufficient for any model
        """
        ...

    @abstractmethod
    def estimate_cost(
        self,
        task_type: TaskType,
        model_id: str,
        context: RoutingContext,
    ) -> CostEstimate:
        """
        Estimate the cost of using a specific model for a task.

        Args:
            task_type: The type of task
            model_id: The model to estimate cost for
            context: Routing context for token estimation

        Returns:
            CostEstimate with predicted token usage and cost

        Raises:
            ModelNotFoundError: If model_id is not in the known models
        """
        ...

    @abstractmethod
    def rank_models(
        self,
        task_type: TaskType,
        context: RoutingContext,
    ) -> list[RankedModel]:
        """
        Rank all candidate models for a given task.

        Models are returned sorted by suitability (best first).
        The ranking considers both cost and quality estimates.

        Args:
            task_type: The type of task to rank models for
            context: Routing context

        Returns:
            List of RankedModel sorted by score descending (best first).
            Empty list if no models qualify.
        """
        ...

"""
CostOptimizedStrategy — cheapest model that meets quality threshold.

Loads model capabilities and costs from existing YAML configs,
then selects the least expensive model whose strengths match
the task type and whose quality estimate meets the minimum threshold.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..providers.config import DEFAULT_PROVIDERS_CONFIG_PATH, ConfigLoader
from .errors import BudgetExceededError, NoEligibleModelError
from .models import (
    CostEstimate,
    ModelSelection,
    RankedModel,
    RoutingContext,
    TaskType,
)
from .provider_registry import ProviderRegistry
from .strategy import RoutingStrategy

if TYPE_CHECKING:
    from .budget import BudgetTracker

# Default models config path (relative to repo root)
DEFAULT_MODELS_CONFIG_PATH = Path(DEFAULT_PROVIDERS_CONFIG_PATH).parent / "models.yaml"

# Token estimation heuristic: base tokens per file for different complexities
_BASE_TOKENS_PER_FILE = 500
_COMPLEXITY_MULTIPLIER = {0.0: 0.5, 0.5: 1.0, 1.0: 2.0}
_OUTPUT_TOKEN_RATIO = 2.0  # Output ≈ 2x input for edit tasks


def _estimate_tokens(context: RoutingContext) -> tuple[int, int]:
    """
    Estimate input and output tokens from routing context.

    Uses a simple heuristic based on file count and complexity.
    """
    file_count = max(context.file_count, 1)  # At least 1 file assumed
    complexity = context.complexity

    # Interpolate complexity multiplier
    if complexity <= 0.5:
        mult = 0.5 + complexity  # 0.0→0.5, 0.5→1.0
    else:
        mult = 1.0 + (complexity - 0.5) * 2.0  # 0.5→1.0, 1.0→2.0

    input_tokens = int(file_count * _BASE_TOKENS_PER_FILE * mult)
    output_tokens = int(input_tokens * _OUTPUT_TOKEN_RATIO)

    return input_tokens, output_tokens


def _load_models_config(
    models_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load model definitions from models.yaml."""
    path = models_path or DEFAULT_MODELS_CONFIG_PATH
    data = ConfigLoader.load_yaml(path)
    result: dict[str, dict[str, Any]] = data.get("models", {})
    return result


def _load_routing_rules(
    models_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load routing rules from models.yaml."""
    path = models_path or DEFAULT_MODELS_CONFIG_PATH
    data = ConfigLoader.load_yaml(path)
    result: dict[str, dict[str, Any]] = data.get("routing", {})
    return result


def _load_cost_rates(
    providers_path: Path | None = None,
) -> dict[str, tuple[float, float]]:
    """Load cost rates from providers.yaml. Returns {model_id: (input_rate, output_rate)}."""
    path = providers_path or DEFAULT_PROVIDERS_CONFIG_PATH
    config = ConfigLoader.load_providers_config(path)
    rates: dict[str, tuple[float, float]] = {}
    for model_id, cost_cfg in config.cost_config.items():
        rates[model_id] = (cost_cfg.input_per_million, cost_cfg.output_per_million)
    return rates


# Map long-form model IDs to short-form keys used in models.yaml
_MODEL_ID_TO_SHORT: dict[str, str] = {
    "openai/gpt-4o": "gpt-4o",
    "openai/gpt-4o-mini": "gpt-4o-mini",
    "openai/gpt-4.1": "gpt-4.1",
    "openai/gpt-4.1-mini": "gpt-4.1-mini",
    "openai/o3-mini": "o3-mini",
    "anthropic/claude-sonnet-4-20250514": "claude-sonnet-4",
    "anthropic/claude-haiku-3-5-20241022": "claude-haiku-3.5",
    "google/gemini-2.5-pro-preview-03-25": "gemini-2.5-pro",
    "google/gemini-2.0-flash": "gemini-2.0-flash",
    "deepseek/deepseek-chat": "deepseek-chat",
    "deepseek/deepseek-coder": "deepseek-coder",
}

# Reverse mapping
_SHORT_TO_MODEL_ID: dict[str, str] = {v: k for k, v in _MODEL_ID_TO_SHORT.items()}

# Map TaskType to the strength keyword used in models.yaml
_TASK_TYPE_TO_STRENGTH: dict[TaskType, str] = {
    TaskType.ARCHITECTURE: "architecture",
    TaskType.CODING: "coding",
    TaskType.CODE_REVIEW: "code_review",
    TaskType.TESTING: "testing",
    TaskType.DOCUMENTATION: "writing",  # documentation models list "writing" as strength
    TaskType.SIMPLE_QUERY: "simple_tasks",
}


class CostOptimizedStrategy(RoutingStrategy):
    """
    Routing strategy that selects the cheapest model meeting quality threshold.

    Models are ranked by total estimated cost (ascending). The first model
    whose quality estimate meets the minimum threshold for the task type
    is selected.
    """

    def __init__(
        self,
        models_path: Path | None = None,
        providers_path: Path | None = None,
        budget_tracker: "BudgetTracker | None" = None,
        provider_registry: "ProviderRegistry | None" = None,
    ) -> None:
        """
        Initialize strategy by loading model and cost configs.

        Args:
            models_path: Path to models.yaml (uses default if None)
            providers_path: Path to providers.yaml (uses default if None)
            budget_tracker: Optional BudgetTracker for budget enforcement
            provider_registry: Optional ProviderRegistry for capability discovery
        """
        self._models: dict[str, dict[str, Any]] = _load_models_config(models_path)
        self._routing_rules: dict[str, dict[str, Any]] = _load_routing_rules(
            models_path
        )
        self._cost_rates: dict[str, tuple[float, float]] = _load_cost_rates(
            providers_path
        )
        self._budget_tracker = budget_tracker
        self._provider_registry = provider_registry

        # Enhance model data with provider registry capabilities if available
        if provider_registry:
            self._enhance_models_with_capabilities()

    @property
    def name(self) -> str:
        return "cost_optimized"

    def _enhance_models_with_capabilities(self) -> None:
        """Enhance model data with capabilities from provider registry."""
        if not self._provider_registry:
            return

        for model_short_id, model_cfg in self._models.items():
            # Get full model ID
            full_id = _SHORT_TO_MODEL_ID.get(model_short_id, model_short_id)

            # Find providers that support this model
            providers = self._provider_registry.get_providers_for_model(full_id)
            if not providers:
                continue

            # Get capabilities from the first provider (sorted by success rate)
            provider_name = providers[0]
            metadata = self._provider_registry.get_metadata(provider_name)
            if not metadata:
                continue

            # Add capabilities to model config
            if metadata.capabilities:
                if "capabilities" not in model_cfg:
                    model_cfg["capabilities"] = []

                # Add capabilities that aren't already listed
                existing_caps = set(model_cfg.get("capabilities", []))
                new_caps = {cap.value for cap in metadata.capabilities}
                all_caps = existing_caps.union(new_caps)
                model_cfg["capabilities"] = list(all_caps)

            # Add provider performance metrics
            if "performance" not in model_cfg:
                model_cfg["performance"] = {}

            perf = model_cfg["performance"]
            perf["avg_latency_ms"] = metadata.avg_latency_ms
            perf["success_rate"] = metadata.success_rate
            perf["status"] = metadata.status.value

    def _get_task_routing_rules(self, task_type: TaskType) -> dict[str, Any]:
        """Get routing rules for a task type from models.yaml."""
        task_rules: dict[str, dict[str, Any]] = self._routing_rules.get(
            "task_types", {}
        )
        result: dict[str, Any] = task_rules.get(task_type.value, {})
        return result

    def _model_matches_task(
        self,
        model_short_id: str,
        task_type: TaskType,
    ) -> bool:
        """Check if a model's strengths include the task type."""
        model_cfg = self._models.get(model_short_id, {})
        strengths: list[str] = model_cfg.get("strengths", [])
        strength_keyword = _TASK_TYPE_TO_STRENGTH.get(task_type, task_type.value)
        return strength_keyword in strengths

    def _get_quality_estimate(
        self,
        model_short_id: str,
        task_type: TaskType,
    ) -> float:
        """
        Estimate quality (0.0-1.0) for a model on a task type.

        Uses position in the priority list as a proxy:
        - First in priority list → 0.95
        - Second → 0.85
        - Third → 0.75
        - Not in list but matches strengths → 0.6
        - Doesn't match → 0.3
        """
        rules = self._get_task_routing_rules(task_type)
        priority: list[str] = rules.get("priority", [])

        if model_short_id in priority:
            idx = priority.index(model_short_id)
            return max(0.5, 0.95 - idx * 0.1)

        if self._model_matches_task(model_short_id, task_type):
            return 0.6

        return 0.3

    def _get_cost_per_token(
        self,
        model_short_id: str,
    ) -> tuple[float, float]:
        """Get (input_per_million, output_per_million) for a model."""
        # Try full model ID first
        full_id = _SHORT_TO_MODEL_ID.get(model_short_id)
        if full_id and full_id in self._cost_rates:
            return self._cost_rates[full_id]

        # Try short ID directly
        if model_short_id in self._cost_rates:
            return self._cost_rates[model_short_id]

        # Fallback: very expensive (should not be selected)
        return (100.0, 200.0)

    def estimate_cost(
        self,
        task_type: TaskType,
        model_id: str,
        context: RoutingContext,
    ) -> CostEstimate:
        """Estimate cost for a model on a task."""
        input_tokens, output_tokens = _estimate_tokens(context)
        input_rate, output_rate = self._get_cost_per_token(model_id)

        cost_usd = (
            (input_tokens / 1_000_000) * input_rate
            + (output_tokens / 1_000_000) * output_rate
        )

        return CostEstimate(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_cost_usd=cost_usd,
        )

    def rank_models(
        self,
        task_type: TaskType,
        context: RoutingContext,
    ) -> list[RankedModel]:
        """Rank all qualifying models by cost (cheapest first)."""
        ranked: list[RankedModel] = []

        for model_short_id, model_cfg in self._models.items():
            # Skip disabled / mock models
            provider = model_cfg.get("provider", "")
            if provider == "mock":
                continue

            quality = self._get_quality_estimate(model_short_id, task_type)
            cost_est = self.estimate_cost(task_type, model_short_id, context)

            # Composite score: blend quality and inverse cost
            # Higher score = better (high quality, low cost)
            # Normalize cost to 0-1 range (max $1 per task)
            cost_score = max(0.0, 1.0 - min(cost_est.total_cost_usd, 1.0))
            score = quality * 0.6 + cost_score * 0.4

            ranked.append(
                RankedModel(
                    model_id=model_short_id,
                    score=score,
                    cost_estimate=cost_est,
                    quality_estimate=quality,
                )
            )

        # Sort by cost ascending (cheapest first)
        ranked.sort(key=lambda m: m.cost_estimate.total_cost_usd)
        return ranked

    def select_model(
        self,
        task_type: TaskType,
        context: RoutingContext,
    ) -> ModelSelection | None:
        """Select the cheapest model that meets the quality threshold."""
        rules = self._get_task_routing_rules(task_type)
        min_quality: float = rules.get("min_quality", 0.5)

        ranked = self.rank_models(task_type, context)

        # Get budget remaining from context or budget tracker
        budget_remaining = context.budget_remaining
        if budget_remaining is None and self._budget_tracker is not None:
            status = self._budget_tracker.get_budget_status()
            budget_remaining = min(
                status["session"]["remaining"],
                status["daily"]["remaining"]
            )

        for candidate in ranked:
            # Skip models below quality threshold
            if candidate.quality_estimate < min_quality:
                continue

            # Check budget
            if budget_remaining is not None:
                if candidate.cost_estimate.total_cost_usd > budget_remaining:
                    continue

            # Found a suitable model
            reason = (
                f"Cheapest model meeting min_quality={min_quality} "
                f"for {task_type.value} "
                f"(cost=${candidate.cost_estimate.total_cost_usd:.6f}, "
                f"quality={candidate.quality_estimate:.2f})"
            )

            return ModelSelection(
                model_id=candidate.model_id,
                reason=reason,
                estimated_cost=candidate.cost_estimate,
                confidence=min(candidate.quality_estimate, 0.95),
            )

        # No model met the threshold — check if budget is the blocker
        if budget_remaining is not None and budget_remaining <= 0:
            raise BudgetExceededError(
                budget_remaining=budget_remaining,
                estimated_cost=0.0,
            )

        raise NoEligibleModelError(
            task_type.value,
            reason=(
                f"No model meets min_quality={min_quality} "
                f"for task type '{task_type.value}'"
            ),
        )

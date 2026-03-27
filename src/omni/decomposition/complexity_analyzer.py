"""Complexity analyzer for task decomposition.

Analyzes task complexity using multiple metrics:
- Token count estimation
- Dependency depth analysis
- Parallelizability scoring
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omni.task.models import ComplexityEstimate, Task, TaskGraph


class ComplexityAnalyzer:
    """Analyzes task complexity using multiple metrics.

    Provides methods to estimate:
    1. Token count for LLM processing
    2. Dependency depth in task graphs
    3. Parallelizability score for execution optimization
    """

    # Average tokens per word (rough estimate for English text)
    TOKENS_PER_WORD = 1.3

    # Token multipliers for different task types
    TASK_TYPE_MULTIPLIERS = {
        "code_generation": 2.0,
        "code_review": 1.5,
        "testing": 1.8,
        "refactoring": 2.2,
        "documentation": 1.2,
        "analysis": 1.7,
        "configuration": 1.1,
        "deployment": 1.4,
        "custom": 1.5,
    }

    def __init__(self) -> None:
        """Initialize the complexity analyzer."""
        pass

    def estimate_tokens(self, task: Task) -> int:
        """Estimate token count for a task description.

        Uses a simple heuristic based on word count and task type.

        Args:
            task: The task to analyze

        Returns:
            Estimated token count
        """
        # Count words in description
        words = re.findall(r'\b\w+\b', task.description)
        word_count = len(words)

        # Get task type multiplier
        task_type_str = str(task.task_type)
        multiplier = self.TASK_TYPE_MULTIPLIERS.get(
            task_type_str,
            self.TASK_TYPE_MULTIPLIERS["custom"]
        )

        # Estimate tokens
        estimated_tokens = int(word_count * self.TOKENS_PER_WORD * multiplier)

        # Add base tokens for task metadata
        estimated_tokens += 50  # Base tokens for task ID, status, etc.

        return max(estimated_tokens, 10)  # Minimum 10 tokens

    def analyze_dependency_depth(self, task_graph: TaskGraph, task_id: str) -> int:
        """Calculate the dependency depth of a task in the graph.

        Depth is the number of levels of dependencies from the root.

        Args:
            task_graph: The task graph containing the task
            task_id: ID of the task to analyze

        Returns:
            Dependency depth (0 for root tasks)
        """
        if task_id not in task_graph.tasks:
            raise ValueError(f"Task '{task_id}' not found in graph")

        # Get all dependencies recursively
        def get_depth(tid: str, visited: set[str] | None = None) -> int:
            if visited is None:
                visited = set()

            if tid in visited:
                # Cycle detected, return 0 to avoid infinite recursion
                return 0

            visited.add(tid)
            task = task_graph.tasks[tid]

            if not task.dependencies:
                return 0

            # Depth is 1 + max depth of dependencies
            max_dep_depth = 0
            for dep_id in task.dependencies:
                if dep_id in task_graph.tasks:
                    dep_depth = get_depth(dep_id, visited.copy())
                    max_dep_depth = max(max_dep_depth, dep_depth)

            return 1 + max_dep_depth

        return get_depth(task_id)

    def calculate_parallelizability_score(self, task_graph: TaskGraph) -> float:
        """Calculate how parallelizable a task graph is.

        Score ranges from 0.0 (completely sequential) to 1.0 (fully parallelizable).

        Args:
            task_graph: The task graph to analyze

        Returns:
            Parallelizability score between 0.0 and 1.0
        """
        if not task_graph.tasks:
            return 1.0  # Empty graph is trivially parallelizable

        # Count total tasks and edges
        total_tasks = task_graph.size
        total_edges = task_graph.edge_count

        if total_tasks <= 1:
            return 1.0  # Single task is trivially parallelizable

        # Parallelizability is inversely related to dependency density
        # Lower dependency density = more parallelizable
        max_possible_edges = total_tasks * (total_tasks - 1)
        dependency_density = total_edges / max_possible_edges if max_possible_edges > 0 else 0

        # Score calculation:
        # - High score when many tasks have no dependencies (roots)
        # - Low score when tasks are heavily chained
        root_count = len(task_graph.roots)
        root_ratio = root_count / total_tasks

        # Combined score: root ratio dominates, but dependency density reduces it
        parallelizability = root_ratio * (1.0 - dependency_density * 0.5)

        # Ensure score is in valid range
        return max(0.0, min(1.0, parallelizability))

    def analyze_task_complexity(self, task: Task, task_graph: TaskGraph | None = None) -> ComplexityEstimate:
        """Analyze a task's complexity and return a ComplexityEstimate.

        Args:
            task: The task to analyze
            task_graph: Optional task graph for dependency analysis

        Returns:
            ComplexityEstimate with computed metrics
        """
        from omni.task.models import ComplexityEstimate

        # Estimate tokens
        estimated_tokens = self.estimate_tokens(task)

        # Calculate dependency depth if task graph is provided
        dependency_depth = 0
        if task_graph and task.task_id in task_graph.tasks:
            dependency_depth = self.analyze_dependency_depth(task_graph, task.task_id)

        # Calculate complexity scores based on various factors
        # Code complexity: based on task type and description length
        code_complexity = self._calculate_code_complexity(task)

        # Integration complexity: affected by dependency depth
        integration_complexity = self._calculate_integration_complexity(task, dependency_depth)

        # Testing complexity: based on task type
        testing_complexity = self._calculate_testing_complexity(task)

        # Unknown factor: based on description ambiguity
        unknown_factor = self._calculate_unknown_factor(task)

        # Create complexity estimate
        complexity = ComplexityEstimate(
            code_complexity=code_complexity,
            integration_complexity=integration_complexity,
            testing_complexity=testing_complexity,
            unknown_factor=unknown_factor,
            estimated_tokens=estimated_tokens,
            reasoning=self._generate_reasoning(
                task, code_complexity, integration_complexity,
                testing_complexity, unknown_factor, dependency_depth
            )
        )

        return complexity

    def _calculate_code_complexity(self, task: Task) -> int:
        """Calculate code complexity score (1-10)."""
        base_score = 3  # Default moderate complexity

        # Task type affects complexity
        task_type_str = str(task.task_type)
        if task_type_str in ["code_generation", "refactoring"]:
            base_score += 2
        elif task_type_str in ["code_review", "testing"]:
            base_score += 1
        elif task_type_str in ["documentation", "configuration"]:
            base_score -= 1

        # Description length affects complexity
        word_count = len(re.findall(r'\b\w+\b', task.description))
        if word_count > 100:
            base_score += 2
        elif word_count > 50:
            base_score += 1
        elif word_count < 10:
            base_score -= 1

        return max(1, min(10, base_score))

    def _calculate_integration_complexity(self, task: Task, dependency_depth: int) -> int:
        """Calculate integration complexity score (1-10)."""
        base_score = 2  # Default low complexity

        # Dependency depth increases integration complexity
        if dependency_depth > 5:
            base_score += 3
        elif dependency_depth > 3:
            base_score += 2
        elif dependency_depth > 1:
            base_score += 1

        # Task type affects integration complexity
        task_type_str = str(task.task_type)
        if task_type_str in ["deployment", "refactoring"]:
            base_score += 2
        elif task_type_str in ["code_generation", "testing"]:
            base_score += 1

        return max(1, min(10, base_score))

    def _calculate_testing_complexity(self, task: Task) -> int:
        """Calculate testing complexity score (1-10)."""
        base_score = 2  # Default low complexity

        # Task type affects testing complexity
        task_type_str = str(task.task_type)
        if task_type_str in ["testing", "refactoring"]:
            base_score += 3
        elif task_type_str in ["code_generation", "deployment"]:
            base_score += 2
        elif task_type_str in ["documentation", "configuration"]:
            base_score -= 1

        return max(1, min(10, base_score))

    def _calculate_unknown_factor(self, task: Task) -> int:
        """Calculate unknown factor score (1-10)."""
        base_score = 2  # Default low unknown factor

        # Description ambiguity increases unknown factor
        description = task.description.lower()

        # Keywords that indicate uncertainty
        uncertain_keywords = [
            "maybe", "perhaps", "possibly", "unknown", "investigate",
            "research", "explore", "determine", "figure out", "how to"
        ]

        # Keywords that indicate clarity
        clear_keywords = [
            "implement", "create", "build", "fix", "update", "change",
            "add", "remove", "modify", "refactor"
        ]

        # Count uncertain keywords
        uncertain_count = sum(1 for keyword in uncertain_keywords if keyword in description)

        # Count clear keywords
        clear_count = sum(1 for keyword in clear_keywords if keyword in description)

        # Adjust score based on keyword counts
        base_score += uncertain_count * 2
        base_score -= clear_count * 1

        return max(1, min(10, base_score))

    def _generate_reasoning(
        self,
        task: Task,
        code_complexity: int,
        integration_complexity: int,
        testing_complexity: int,
        unknown_factor: int,
        dependency_depth: int
    ) -> str:
        """Generate reasoning text for the complexity estimate."""
        reasoning_parts = []

        # Code complexity reasoning
        if code_complexity >= 7:
            reasoning_parts.append("High code complexity due to task type and description.")
        elif code_complexity >= 4:
            reasoning_parts.append("Moderate code complexity.")
        else:
            reasoning_parts.append("Low code complexity.")

        # Integration complexity reasoning
        if dependency_depth > 0:
            reasoning_parts.append(f"Integration complexity increased by dependency depth of {dependency_depth}.")
        else:
            reasoning_parts.append("No dependencies, low integration complexity.")

        # Testing complexity reasoning
        if testing_complexity >= 7:
            reasoning_parts.append("High testing complexity required.")
        elif testing_complexity >= 4:
            reasoning_parts.append("Moderate testing complexity.")
        else:
            reasoning_parts.append("Low testing complexity.")

        # Unknown factor reasoning
        if unknown_factor >= 7:
            reasoning_parts.append("High uncertainty in task requirements.")
        elif unknown_factor >= 4:
            reasoning_parts.append("Some uncertainty in task requirements.")
        else:
            reasoning_parts.append("Clear task requirements.")

        return " ".join(reasoning_parts)

    def analyze_graph_complexity(self, task_graph: TaskGraph) -> dict[str, float]:
        """Analyze overall complexity of a task graph.

        Args:
            task_graph: The task graph to analyze

        Returns:
            Dictionary with complexity metrics for the entire graph
        """
        if not task_graph.tasks:
            return {
                "avg_complexity": 0.0,
                "max_complexity": 0.0,
                "parallelizability": 1.0,
                "total_estimated_tokens": 0,
            }

        # Analyze each task
        complexities = []
        total_tokens = 0

        for task in task_graph.tasks.values():
            complexity = self.analyze_task_complexity(task, task_graph)
            complexities.append(complexity.overall_score)
            total_tokens += complexity.estimated_tokens

        # Calculate parallelizability
        parallelizability = self.calculate_parallelizability_score(task_graph)

        return {
            "avg_complexity": sum(complexities) / len(complexities),
            "max_complexity": max(complexities),
            "parallelizability": parallelizability,
            "total_estimated_tokens": total_tokens,
        }

"""Tests for task matching and agent assignment."""

import pytest

from omni.coordination.agents import AgentCapability, AgentRegistry, AgentTier
from omni.coordination.matcher import (
    AgentAssignment,
    MatchConfidence,
    MatcherConfig,
    TaskMatcher,
)
from omni.task.models import ComplexityEstimate, Task, TaskType


class TestMatcherConfig:
    """Test MatcherConfig validation."""

    def test_valid_config(self):
        """Test valid configuration."""
        config = MatcherConfig(
            capability_weight=0.4,
            complexity_weight=0.25,
            cost_weight=0.2,
            priority_weight=0.15,
        )
        assert config.capability_weight == 0.4
        assert config.complexity_weight == 0.25
        assert config.cost_weight == 0.2
        assert config.priority_weight == 0.15

    def test_invalid_weight_sum(self):
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            MatcherConfig(
                capability_weight=0.5,
                complexity_weight=0.5,
                cost_weight=0.5,
                priority_weight=0.5,
            )


class TestTaskMatcher:
    """Test TaskMatcher functionality."""

    @pytest.fixture
    def registry(self):
        """Create a test registry."""
        return AgentRegistry()

    @pytest.fixture
    def matcher(self, registry):
        """Create a test matcher."""
        return TaskMatcher(registry)

    @pytest.fixture
    def simple_task(self):
        """Create a simple test task."""
        return Task(
            description="Write a function",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=3,
                integration_complexity=2,
                testing_complexity=2,
                unknown_factor=1,
                reasoning="Simple function",
            ),
        )

    @pytest.fixture
    def complex_task(self):
        """Create a complex test task."""
        return Task(
            description="Design system architecture",
            task_type=TaskType.ANALYSIS,
            complexity=ComplexityEstimate(
                code_complexity=8,
                integration_complexity=9,
                testing_complexity=7,
                unknown_factor=8,
                reasoning="Complex architecture design",
            ),
        )

    def test_match_simple_task(self, matcher, simple_task):
        """Test matching a simple task."""
        assignment = matcher.match(simple_task)

        assert isinstance(assignment, AgentAssignment)
        assert assignment.agent_id in ["intern", "coder"]
        assert assignment.score > 0
        assert assignment.reasoning
        assert "complexity_score" in assignment.metadata

        # Simple task should match intern or coder with good confidence
        assert assignment.confidence in [
            MatchConfidence.EXACT,
            MatchConfidence.STRONG,
            MatchConfidence.WEAK,
        ]

    def test_match_complex_task(self, matcher, complex_task):
        """Test matching a complex task."""
        assignment = matcher.match(complex_task)

        assert isinstance(assignment, AgentAssignment)
        # Complex task should go to thinker or reader
        assert assignment.agent_id in ["thinker", "reader"]
        assert assignment.score > 0

    def test_match_with_capabilities(self, matcher):
        """Test matching with explicit capabilities."""
        task = Task(
            description="Extract data from document",
            task_type=TaskType.ANALYSIS,
            complexity=ComplexityEstimate(
                code_complexity=2,
                integration_complexity=2,
                testing_complexity=1,
                unknown_factor=1,
            ),
        )

        # Request extraction capability
        assignment = matcher.match(
            task,
            required_capabilities={AgentCapability.EXTRACTION},
        )

        # Should match intern (has extraction capability)
        assert assignment.agent_id == "intern"
        assert AgentCapability.EXTRACTION in assignment.agent_profile.capabilities

    def test_match_batch(self, matcher, simple_task, complex_task):
        """Test batch matching."""
        tasks = [simple_task, complex_task]
        assignments = matcher.match_batch(tasks)

        assert len(assignments) == 2
        assert simple_task.task_id in assignments
        assert complex_task.task_id in assignments

        simple_assignment = assignments[simple_task.task_id]
        complex_assignment = assignments[complex_task.task_id]

        # Different tasks should get different agents
        assert simple_assignment.agent_id != complex_assignment.agent_id

    def test_score_agent(self, matcher, simple_task):
        """Test agent scoring."""
        registry = AgentRegistry()
        coder = registry.get("coder")
        intern = registry.get("intern")

        # Score coder for simple task
        score, reasoning = matcher._score_agent(
            coder,
            required_caps={AgentCapability.CODE_GENERATION},
            complexity_score=simple_task.effective_complexity.overall_score,
            task=simple_task,
        )

        assert 0 <= score <= 1
        assert reasoning
        assert "coder" in reasoning.lower()

        # Score intern for simple task
        score2, reasoning2 = matcher._score_agent(
            intern,
            required_caps={AgentCapability.CODE_GENERATION},
            complexity_score=simple_task.effective_complexity.overall_score,
            task=simple_task,
        )

        # Intern should score lower for code generation (doesn't have that capability)
        assert score > score2

    def test_extract_capabilities(self, matcher):
        """Test capability extraction."""
        from omni.decomposition.models import Subtask

        # Test with Subtask that has explicit capabilities
        subtask = Subtask(
            description="Test subtask",
            task_type=TaskType.CODE_GENERATION,
            required_capabilities=["code_generation", "testing"],
        )
        caps = matcher._extract_capabilities(subtask)
        assert AgentCapability.CODE_GENERATION in caps
        assert AgentCapability.TESTING in caps

        # Test with regular Task (infer from type)
        task = Task(
            description="Test task",
            task_type=TaskType.CODE_GENERATION,
        )
        caps = matcher._extract_capabilities(task)
        assert AgentCapability.CODE_GENERATION in caps

        # Test with vision context
        task_with_vision = Task(
            description="Analyze screenshot",
            task_type=TaskType.ANALYSIS,
            context={"content": "Look at this screenshot: image.png"},
        )
        caps = matcher._extract_capabilities(task_with_vision)
        assert AgentCapability.VISION in caps

        # Test with long context
        task_with_long = Task(
            description="Analyze large codebase",
            task_type=TaskType.ANALYSIS,
            context={"content": "This is a very long codebase exploration"},
        )
        caps = matcher._extract_capabilities(task_with_long)
        assert AgentCapability.LONG_CONTEXT in caps

    def test_fallback_assignment(self, matcher):
        """Test fallback assignment when no agents."""
        # Create empty registry
        empty_registry = AgentRegistry()
        empty_registry.agents = {}  # Clear all agents

        # Add at least one agent for fallback
        from omni.coordination.agents import AgentProfile
        fallback_agent = AgentProfile(
            agent_id="fallback",
            tier=AgentTier.CODER,
            model_id="test/model",
            display_name="Fallback",
            capabilities={"code_generation"},
        )
        empty_registry.register(fallback_agent)

        empty_matcher = TaskMatcher(empty_registry)

        task = Task(
            description="Test task",
            task_type=TaskType.CODE_GENERATION,
        )

        # Should still return an assignment (fallback)
        assignment = empty_matcher._fallback_assignment(task)
        assert isinstance(assignment, AgentAssignment)
        assert assignment.confidence == MatchConfidence.FALLBACK

    def test_custom_config(self):
        """Test matcher with custom configuration."""
        registry = AgentRegistry()
        config = MatcherConfig(
            capability_weight=0.5,
            complexity_weight=0.3,
            cost_weight=0.1,
            priority_weight=0.1,
            min_acceptable_score=0.4,
        )
        matcher = TaskMatcher(registry, config)

        task = Task(
            description="Test task",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=3,
                integration_complexity=2,
                testing_complexity=2,
                unknown_factor=1,
            ),
        )

        assignment = matcher.match(task)
        assert assignment.score >= 0  # Should have a score

    def test_confidence_levels(self, matcher):
        """Test different confidence levels."""

        # Create a task that perfectly matches coder
        perfect_task = Task(
            description="Write Python code",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=4,  # Within coder's range
                integration_complexity=3,
                testing_complexity=3,
                unknown_factor=2,
            ),
        )

        assignment = matcher.match(perfect_task)
        # Good match should have high confidence
        assert assignment.confidence in [
            MatchConfidence.EXACT,
            MatchConfidence.STRONG,
            MatchConfidence.WEAK,  # Acceptable too
        ]

        # Create a task with very low complexity (should match intern)
        simple_task = Task(
            description="Format code",
            task_type=TaskType.CONFIGURATION,
            complexity=ComplexityEstimate(
                code_complexity=1,
                integration_complexity=1,
                testing_complexity=1,
                unknown_factor=1,
            ),
        )

        assignment = matcher.match(simple_task)
        # Should match intern with good confidence
        assert assignment.agent_id == "intern"
        assert assignment.confidence in [
            MatchConfidence.EXACT,
            MatchConfidence.STRONG,
            MatchConfidence.WEAK,
        ]

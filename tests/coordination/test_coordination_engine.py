"""Tests for the main coordination engine."""

from typing import Any

import pytest

from omni.coordination.engine import (
    CoordinationConfig,
    CoordinationEngine,
    CoordinationObserver,
    CoordinationResult,
)
from omni.coordination.matcher import AgentAssignment
from omni.decomposition.models import Subtask, SubtaskType
from omni.task.models import ComplexityEstimate, TaskGraph, TaskType


class MockObserver(CoordinationObserver):
    """Mock observer for testing."""

    def __init__(self):
        self.events = []

    def on_agent_assigned(self, task_id: str, assignment: AgentAssignment) -> None:
        self.events.append(("agent_assigned", task_id, assignment.agent_id))

    def on_workflow_planned(self, plan: Any) -> None:
        self.events.append(("workflow_planned", plan.plan_id))

    def on_step_started(self, step_id: str, task_ids: list[str]) -> None:
        self.events.append(("step_started", step_id, task_ids))

    def on_step_completed(self, step_id: str, results: dict[str, Any]) -> None:
        self.events.append(("step_completed", step_id, list(results.keys())))

    def on_escalation(self, task_id: str, from_agent: str, to_agent: str, reason: str) -> None:
        self.events.append(("escalation", task_id, from_agent, to_agent, reason))


class TestCoordinationEngine:
    """Test CoordinationEngine functionality."""

    @pytest.fixture
    def simple_task_graph(self):
        """Create a simple task graph."""
        graph = TaskGraph(name="Test Graph")

        task1 = Subtask(
            description="Implement feature",
            task_type=TaskType.CODE_GENERATION,
            subtask_type=SubtaskType.IMPLEMENTATION,
            complexity=ComplexityEstimate(
                code_complexity=3,
                integration_complexity=2,
                testing_complexity=2,
                unknown_factor=1,
            ),
        )
        task2 = Subtask(
            description="Test feature",
            task_type=TaskType.TESTING,
            subtask_type=SubtaskType.VALIDATION,
            complexity=ComplexityEstimate(
                code_complexity=2,
                integration_complexity=2,
                testing_complexity=3,
                unknown_factor=1,
            ),
        )

        graph.add_task(task1)
        graph.add_task(task2)

        return graph

    @pytest.fixture
    def engine(self):
        """Create a coordination engine."""
        return CoordinationEngine()

    def test_engine_creation(self):
        """Test engine creation with default configuration."""
        engine = CoordinationEngine()
        assert engine.config is not None
        assert engine.registry is not None
        assert engine.matcher is not None
        assert engine.orchestrator is not None
        assert engine._observers == []

    def test_engine_with_custom_config(self):
        """Test engine with custom configuration."""
        config = CoordinationConfig(
            enable_reviews=False,
            max_parallel_per_step=3,
            auto_escalate_on_failure=False,
        )
        engine = CoordinationEngine(config=config)

        assert engine.config.enable_reviews is False
        assert engine.config.max_parallel_per_step == 3
        assert engine.config.auto_escalate_on_failure is False
        assert engine.orchestrator.enable_reviews is False
        assert engine.orchestrator.max_parallel_per_step == 3

    def test_coordinate_simple_graph(self, engine, simple_task_graph):
        """Test coordinating a simple task graph."""
        result = engine.coordinate(simple_task_graph, plan_id="test-plan")

        assert isinstance(result, CoordinationResult)
        assert result.plan.plan_id == "test-plan"
        assert result.task_graph == simple_task_graph
        assert len(result.assignments) == 2

        # Check assignments
        for _task_id, assignment in result.assignments.items():
            assert isinstance(assignment, AgentAssignment)
            assert assignment.agent_id in ["intern", "coder", "reader", "thinker"]
            assert assignment.score > 0
            assert assignment.reasoning

        # Check plan
        assert result.plan.total_steps > 0
        assert result.plan.task_graph_name == "Test Graph"
        assert result.total_agents_used > 0
        assert result.estimated_total_cost >= 0

    def test_coordinate_with_observer(self, simple_task_graph):
        """Test coordination with observer."""
        observer = MockObserver()
        engine = CoordinationEngine(observers=[observer])

        result = engine.coordinate(simple_task_graph)

        # Check that observer was called
        assert len(observer.events) > 0

        # Should have agent assignment events
        agent_events = [e for e in observer.events if e[0] == "agent_assigned"]
        assert len(agent_events) == len(simple_task_graph.tasks)

        # Should have workflow planned event
        planned_events = [e for e in observer.events if e[0] == "workflow_planned"]
        assert len(planned_events) == 1
        assert planned_events[0][1] == result.plan.plan_id

    def test_handle_failure_with_escalation(self):
        """Test handling task failure with escalation."""
        engine = CoordinationEngine()

        # Test escalation from intern
        new_assignment = engine.handle_failure(
            task_id="task-1",
            current_agent_id="intern",
            error="Failed to complete task",
        )

        assert new_assignment is not None
        assert new_assignment.agent_id == "coder"
        assert new_assignment.confidence == "fallback"
        assert "escalated from intern" in new_assignment.reasoning.lower()
        assert new_assignment.metadata["escalation"] is True
        assert new_assignment.metadata["original_agent"] == "intern"

    def test_handle_failure_no_escalation(self):
        """Test handling task failure without escalation."""
        config = CoordinationConfig(auto_escalate_on_failure=False)
        engine = CoordinationEngine(config=config)

        # With auto-escalation disabled
        new_assignment = engine.handle_failure(
            task_id="task-1",
            current_agent_id="intern",
            error="Failed",
        )

        assert new_assignment is None

    def test_handle_failure_at_top_tier(self):
        """Test handling failure when already at top tier."""
        engine = CoordinationEngine()

        # Thinker is already top tier
        new_assignment = engine.handle_failure(
            task_id="task-1",
            current_agent_id="thinker",
            error="Failed",
        )

        assert new_assignment is None  # No higher tier to escalate to

    def test_register_unregister_observer(self):
        """Test observer registration and unregistration."""
        engine = CoordinationEngine()
        observer1 = MockObserver()
        observer2 = MockObserver()

        # Register observers
        engine.register_observer(observer1)
        engine.register_observer(observer2)
        assert len(engine._observers) == 2

        # Unregister observer1
        engine.unregister_observer(observer1)
        assert len(engine._observers) == 1
        assert engine._observers[0] is observer2

        # Unregister observer2
        engine.unregister_observer(observer2)
        assert len(engine._observers) == 0

    def test_coordinate_empty_graph(self, engine):
        """Test coordinating an empty task graph."""
        empty_graph = TaskGraph(name="Empty Graph")
        result = engine.coordinate(empty_graph)

        assert isinstance(result, CoordinationResult)
        assert result.plan.total_steps == 0
        assert len(result.assignments) == 0
        assert result.total_agents_used == 0
        assert result.estimated_total_cost == 0.0

    def test_coordinate_complex_graph(self):
        """Test coordinating a more complex task graph."""
        graph = TaskGraph(name="Complex Graph")

        # Create tasks with different complexities and types
        tasks = [
            Subtask(
                description=f"Task {i}",
                task_type=TaskType.CODE_GENERATION if i < 2 else TaskType.ANALYSIS,
                subtask_type=SubtaskType.IMPLEMENTATION,
                complexity=ComplexityEstimate(
                    code_complexity=i * 2 + 1,  # Varying complexity: 1, 3, 5, 7, 9
                    integration_complexity=2,
                    testing_complexity=2,
                    unknown_factor=1,
                ),
            )
            for i in range(5)
        ]

        # Add tasks with dependencies
        for i, task in enumerate(tasks):
            if i == 1 or i == 2:
                task.dependencies = [tasks[0].task_id]
            elif i == 4:
                task.dependencies = [tasks[3].task_id]
            graph.add_task(task)

        engine = CoordinationEngine()
        result = engine.coordinate(graph)

        assert len(result.assignments) == 5
        assert result.plan.total_steps >= 2  # At least 2 waves due to dependencies

        # Different tasks should get different agents based on complexity
        agent_ids = [a.agent_id for a in result.assignments.values()]
        assert len(set(agent_ids)) > 1  # Should use multiple agents

    def test_observer_protocol_integration(self):
        """Test that observers receive all expected events."""
        observer = MockObserver()
        engine = CoordinationEngine(observers=[observer])

        # Create a task graph
        graph = TaskGraph(name="Observer Test")
        task = Subtask(
            description="Test task",
            task_type=TaskType.CODE_GENERATION,
            subtask_type=SubtaskType.IMPLEMENTATION,
            complexity=ComplexityEstimate(
                code_complexity=3,
                integration_complexity=2,
                testing_complexity=2,
                unknown_factor=1,
            ),
        )
        graph.add_task(task)

        # Coordinate
        _ = engine.coordinate(graph)

        # Check events
        assert any(e[0] == "agent_assigned" for e in observer.events)
        assert any(e[0] == "workflow_planned" for e in observer.events)

        # Test escalation event
        engine.handle_failure(
            task_id=task.task_id,
            current_agent_id="intern",
            error="Test failure",
        )

        assert any(e[0] == "escalation" for e in observer.events)

    def test_cost_estimation(self, engine, simple_task_graph):
        """Test cost estimation in coordination result."""
        result = engine.coordinate(simple_task_graph)

        # Cost should be sum of agent costs
        expected_cost = sum(
            a.agent_profile.cost_per_million_tokens
            for a in result.assignments.values()
        )
        assert result.estimated_total_cost == expected_cost

    def test_agents_used_count(self, engine, simple_task_graph):
        """Test counting of unique agents used."""
        result = engine.coordinate(simple_task_graph)

        # Count unique agents in assignments
        unique_agents = {a.agent_id for a in result.assignments.values()}
        assert result.total_agents_used == len(unique_agents)
        assert 1 <= result.total_agents_used <= 5  # Between 1 and all 5 agents

    def test_custom_registry(self):
        """Test engine with custom agent registry."""
        from omni.coordination.agents import AgentProfile, AgentRegistry, AgentTier

        # Create custom registry with only coder agent
        registry = AgentRegistry()
        registry.agents = {}  # Clear defaults

        custom_agent = AgentProfile(
            agent_id="custom-coder",
            tier=AgentTier.CODER,
            model_id="custom/model",
            display_name="Custom Coder",
            capabilities={"code_generation"},
        )
        registry.register(custom_agent)

        engine = CoordinationEngine(registry=registry)

        # Create task graph
        graph = TaskGraph(name="Custom Test")
        task = Subtask(
            description="Test",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=3,
                integration_complexity=2,
                testing_complexity=2,
                unknown_factor=1,
            ),
        )
        graph.add_task(task)

        result = engine.coordinate(graph)

        # Should use custom agent
        assignment = result.assignments[task.task_id]
        assert assignment.agent_id == "custom-coder"
        assert result.total_agents_used == 1

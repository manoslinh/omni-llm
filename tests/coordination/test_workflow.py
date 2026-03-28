"""Tests for workflow orchestration."""

import pytest

from omni.coordination.workflow import (
    WorkflowOrchestrator,
    WorkflowPlan,
    WorkflowStep,
    WorkflowStepType,
)
from omni.decomposition.models import Subtask, SubtaskType
from omni.task.models import ComplexityEstimate, TaskGraph, TaskType


class TestWorkflowStep:
    """Test WorkflowStep dataclass."""

    def test_workflow_step_creation(self):
        """Test basic WorkflowStep creation."""
        step = WorkflowStep(
            step_id="step-001",
            step_type=WorkflowStepType.SEQUENTIAL,
            task_ids=["task-1", "task-2"],
            agent_assignments={"task-1": "coder", "task-2": "reader"},
            depends_on=["step-000"],
        )
        assert step.step_id == "step-001"
        assert step.step_type == WorkflowStepType.SEQUENTIAL
        assert step.task_ids == ["task-1", "task-2"]
        assert step.agent_assignments == {"task-1": "coder", "task-2": "reader"}
        assert step.depends_on == ["step-000"]

    def test_is_parallel(self):
        """Test is_parallel property."""
        # Parallel step type
        parallel_step = WorkflowStep(
            step_id="step-001",
            step_type=WorkflowStepType.PARALLEL,
            task_ids=["task-1"],
            agent_assignments={"task-1": "coder"},
        )
        assert parallel_step.is_parallel

        # Sequential step with multiple tasks
        multi_task_step = WorkflowStep(
            step_id="step-002",
            step_type=WorkflowStepType.SEQUENTIAL,
            task_ids=["task-1", "task-2", "task-3"],
            agent_assignments={"task-1": "coder", "task-2": "coder", "task-3": "coder"},
        )
        assert multi_task_step.is_parallel

        # Sequential step with single task
        single_task_step = WorkflowStep(
            step_id="step-003",
            step_type=WorkflowStepType.SEQUENTIAL,
            task_ids=["task-1"],
            agent_assignments={"task-1": "coder"},
        )
        assert not single_task_step.is_parallel


class TestWorkflowPlan:
    """Test WorkflowPlan functionality."""

    def test_workflow_plan_creation(self):
        """Test basic WorkflowPlan creation."""
        steps = [
            WorkflowStep(
                step_id="step-001",
                step_type=WorkflowStepType.SEQUENTIAL,
                task_ids=["task-1"],
                agent_assignments={"task-1": "coder"},
            ),
            WorkflowStep(
                step_id="step-002",
                step_type=WorkflowStepType.PARALLEL,
                task_ids=["task-2", "task-3"],
                agent_assignments={"task-2": "reader", "task-3": "coder"},
                depends_on=["step-001"],
            ),
        ]

        plan = WorkflowPlan(
            plan_id="test-plan",
            steps=steps,
            task_graph_name="Test Graph",
        )

        assert plan.plan_id == "test-plan"
        assert plan.steps == steps
        assert plan.task_graph_name == "Test Graph"
        assert plan.total_steps == 2
        assert plan.parallel_steps == 1  # Only step-002 is parallel
        assert plan.review_steps == 0

    def test_get_step(self):
        """Test get_step method."""
        step1 = WorkflowStep(
            step_id="step-001",
            step_type=WorkflowStepType.SEQUENTIAL,
            task_ids=["task-1"],
            agent_assignments={"task-1": "coder"},
        )
        step2 = WorkflowStep(
            step_id="step-002",
            step_type=WorkflowStepType.PARALLEL,
            task_ids=["task-2"],
            agent_assignments={"task-2": "reader"},
        )

        plan = WorkflowPlan(
            plan_id="test-plan",
            steps=[step1, step2],
            task_graph_name="Test",
        )

        assert plan.get_step("step-001") == step1
        assert plan.get_step("step-002") == step2

        with pytest.raises(KeyError, match="not found"):
            plan.get_step("step-999")

    def test_get_execution_order(self):
        """Test execution order computation."""
        # Create a simple linear plan
        steps = [
            WorkflowStep(
                step_id="step-001",
                step_type=WorkflowStepType.SEQUENTIAL,
                task_ids=["task-1"],
                agent_assignments={"task-1": "coder"},
                depends_on=[],
            ),
            WorkflowStep(
                step_id="step-002",
                step_type=WorkflowStepType.SEQUENTIAL,
                task_ids=["task-2"],
                agent_assignments={"task-2": "reader"},
                depends_on=["step-001"],
            ),
            WorkflowStep(
                step_id="step-003",
                step_type=WorkflowStepType.SEQUENTIAL,
                task_ids=["task-3"],
                agent_assignments={"task-3": "thinker"},
                depends_on=["step-002"],
            ),
        ]

        plan = WorkflowPlan(
            plan_id="test-plan",
            steps=steps,
            task_graph_name="Test",
        )

        order = plan.get_execution_order()
        assert len(order) == 3
        assert order[0] == ["step-001"]
        assert order[1] == ["step-002"]
        assert order[2] == ["step-003"]

    def test_get_execution_order_parallel(self):
        """Test execution order with parallel steps."""
        # Create a plan with parallel branches
        steps = [
            WorkflowStep(
                step_id="step-001",
                step_type=WorkflowStepType.SEQUENTIAL,
                task_ids=["task-1"],
                agent_assignments={"task-1": "coder"},
                depends_on=[],
            ),
            WorkflowStep(
                step_id="step-002",
                step_type=WorkflowStepType.PARALLEL,
                task_ids=["task-2"],
                agent_assignments={"task-2": "reader"},
                depends_on=["step-001"],
            ),
            WorkflowStep(
                step_id="step-003",
                step_type=WorkflowStepType.PARALLEL,
                task_ids=["task-3"],
                agent_assignments={"task-3": "thinker"},
                depends_on=["step-001"],
            ),
            WorkflowStep(
                step_id="step-004",
                step_type=WorkflowStepType.SEQUENTIAL,
                task_ids=["task-4"],
                agent_assignments={"task-4": "coder"},
                depends_on=["step-002", "step-003"],
            ),
        ]

        plan = WorkflowPlan(
            plan_id="test-plan",
            steps=steps,
            task_graph_name="Test",
        )

        order = plan.get_execution_order()
        assert len(order) == 3
        assert order[0] == ["step-001"]
        assert set(order[1]) == {"step-002", "step-003"}  # Can run in parallel
        assert order[2] == ["step-004"]

    def test_summary(self):
        """Test plan summary."""
        steps = [
            WorkflowStep(
                step_id="step-001",
                step_type=WorkflowStepType.SEQUENTIAL,
                task_ids=["task-1"],
                agent_assignments={"task-1": "coder"},
            ),
            WorkflowStep(
                step_id="step-002",
                step_type=WorkflowStepType.REVIEW,
                task_ids=["task-1-review"],
                agent_assignments={"task-1-review": "reader"},
                depends_on=["step-001"],
            ),
            WorkflowStep(
                step_id="step-003",
                step_type=WorkflowStepType.PARALLEL,
                task_ids=["task-2", "task-3"],
                agent_assignments={"task-2": "coder", "task-3": "coder"},
                depends_on=["step-002"],
            ),
        ]

        plan = WorkflowPlan(
            plan_id="test-plan",
            steps=steps,
            task_graph_name="Test Graph",
        )

        summary = plan.summary()
        assert summary["plan_id"] == "test-plan"
        assert summary["total_steps"] == 3
        assert summary["parallel_steps"] == 1
        assert summary["review_steps"] == 1
        assert summary["execution_waves"] == 3  # Linear dependency


class TestWorkflowOrchestrator:
    """Test WorkflowOrchestrator functionality."""

    @pytest.fixture
    def simple_task_graph(self):
        """Create a simple task graph."""
        graph = TaskGraph(name="Simple Graph")

        # Add independent tasks
        task1 = Subtask(
            description="Task 1",
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
            description="Task 2",
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
    def dependent_task_graph(self):
        """Create a task graph with dependencies."""
        graph = TaskGraph(name="Dependent Graph")

        # Task 2 depends on Task 1
        task1 = Subtask(
            description="Implement feature",
            task_type=TaskType.CODE_GENERATION,
            subtask_type=SubtaskType.IMPLEMENTATION,
            complexity=ComplexityEstimate(
                code_complexity=4,
                integration_complexity=3,
                testing_complexity=2,
                unknown_factor=2,
            ),
        )
        task2 = Subtask(
            description="Test feature",
            task_type=TaskType.TESTING,
            subtask_type=SubtaskType.VALIDATION,
            complexity=ComplexityEstimate(
                code_complexity=3,
                integration_complexity=3,
                testing_complexity=4,
                unknown_factor=1,
            ),
            dependencies=[task1.task_id],
        )

        graph.add_task(task1)
        graph.add_task(task2)

        return graph

    def test_create_plan_simple(self, simple_task_graph):
        """Test creating a plan for independent tasks."""
        orchestrator = WorkflowOrchestrator(
            enable_reviews=False,
            max_parallel_per_step=5,
        )

        agent_assignments = dict.fromkeys(simple_task_graph.tasks.keys(), "coder")

        plan = orchestrator.create_plan(
            simple_task_graph,
            agent_assignments,
            plan_id="test-plan",
        )

        assert plan.plan_id == "test-plan"
        assert plan.task_graph_name == "Simple Graph"
        assert len(plan.steps) == 1  # Both tasks can run in parallel
        assert plan.steps[0].step_type == WorkflowStepType.PARALLEL
        assert len(plan.steps[0].task_ids) == 2

    def test_create_plan_dependent(self, dependent_task_graph):
        """Test creating a plan for dependent tasks."""
        orchestrator = WorkflowOrchestrator(
            enable_reviews=False,
            max_parallel_per_step=5,
        )

        agent_assignments = dict.fromkeys(dependent_task_graph.tasks.keys(), "coder")

        plan = orchestrator.create_plan(
            dependent_task_graph,
            agent_assignments,
        )

        assert len(plan.steps) == 2  # Two sequential steps
        assert plan.steps[0].task_ids == [list(dependent_task_graph.tasks.keys())[0]]
        assert plan.steps[1].task_ids == [list(dependent_task_graph.tasks.keys())[1]]
        assert plan.steps[1].depends_on == [plan.steps[0].step_id]

    def test_create_plan_with_reviews(self, simple_task_graph):
        """Test creating a plan with review steps."""
        orchestrator = WorkflowOrchestrator(
            enable_reviews=True,
            max_parallel_per_step=5,
        )

        # Assign intern to trigger review
        agent_assignments = dict.fromkeys(simple_task_graph.tasks.keys(), "intern")

        plan = orchestrator.create_plan(
            simple_task_graph,
            agent_assignments,
        )

        # Should have implementation step + review step
        assert len(plan.steps) == 2
        assert plan.steps[0].step_type in [WorkflowStepType.SEQUENTIAL, WorkflowStepType.PARALLEL]
        assert plan.steps[1].step_type == WorkflowStepType.REVIEW
        assert plan.steps[1].depends_on == [plan.steps[0].step_id]

    def test_compute_execution_waves(self, dependent_task_graph):
        """Test execution wave computation."""
        orchestrator = WorkflowOrchestrator(max_parallel_per_step=2)

        waves = orchestrator._compute_execution_waves(dependent_task_graph)
        assert len(waves) == 2  # Two sequential waves
        assert len(waves[0]) == 1  # First task
        assert len(waves[1]) == 1  # Second task (depends on first)

    def test_compute_execution_waves_parallel_limit(self):
        """Test execution waves with parallel limit."""
        graph = TaskGraph(name="Parallel Test")

        # Add 4 independent tasks
        for i in range(4):
            task = Subtask(
                description=f"Task {i}",
                task_type=TaskType.CODE_GENERATION,
                subtask_type=SubtaskType.IMPLEMENTATION,
                complexity=ComplexityEstimate(
                    code_complexity=2,
                    integration_complexity=2,
                    testing_complexity=2,
                    unknown_factor=1,
                ),
            )
            graph.add_task(task)

        orchestrator = WorkflowOrchestrator(max_parallel_per_step=2)
        waves = orchestrator._compute_execution_waves(graph)

        # With max_parallel_per_step=2, 4 tasks should be in 2 waves
        assert len(waves) == 2
        assert len(waves[0]) == 2
        assert len(waves[1]) == 2

    def test_classify_single_task(self):
        """Test single task classification."""
        orchestrator = WorkflowOrchestrator()

        # Implementation task
        impl_task = Subtask(
            description="Implement",
            task_type=TaskType.CODE_GENERATION,
            subtask_type=SubtaskType.IMPLEMENTATION,
        )
        step_type = orchestrator._classify_single_task(impl_task, "coder")
        assert step_type == WorkflowStepType.SEQUENTIAL

        # Validation task
        val_task = Subtask(
            description="Validate",
            task_type=TaskType.TESTING,
            subtask_type=SubtaskType.VALIDATION,
        )
        step_type = orchestrator._classify_single_task(val_task, "coder")
        assert step_type == WorkflowStepType.REVIEW

        # Regular task (not Subtask)
        from omni.task.models import Task
        regular_task = Task(
            description="Regular",
            task_type=TaskType.CODE_GENERATION,
        )
        step_type = orchestrator._classify_single_task(regular_task, "coder")
        assert step_type == WorkflowStepType.SEQUENTIAL

    def test_identify_review_candidates(self, simple_task_graph):
        """Test review candidate identification."""
        orchestrator = WorkflowOrchestrator()

        task_ids = list(simple_task_graph.tasks.keys())

        # With intern agent - should be reviewed
        agent_assignments = dict.fromkeys(task_ids, "intern")
        candidates = orchestrator._identify_review_candidates(
            task_ids, simple_task_graph, agent_assignments
        )
        assert len(candidates) == len(task_ids)

        # With thinker agent - no review needed (already top tier)
        agent_assignments = dict.fromkeys(task_ids, "thinker")
        candidates = orchestrator._identify_review_candidates(
            task_ids, simple_task_graph, agent_assignments
        )
        assert len(candidates) == 0

    def test_get_reviewer_agent(self):
        """Test reviewer agent selection."""
        orchestrator = WorkflowOrchestrator()

        # Intern → Coder
        reviewer = orchestrator._get_reviewer_agent("task-1", {"task-1": "intern"})
        assert reviewer == "coder"

        # Coder → Reader
        reviewer = orchestrator._get_reviewer_agent("task-2", {"task-2": "coder"})
        assert reviewer == "reader"

        # Reader → Thinker
        reviewer = orchestrator._get_reviewer_agent("task-3", {"task-3": "reader"})
        assert reviewer == "thinker"

        # Thinker → Thinker (self-review)
        reviewer = orchestrator._get_reviewer_agent("task-4", {"task-4": "thinker"})
        assert reviewer == "thinker"

        # Visual → Thinker
        reviewer = orchestrator._get_reviewer_agent("task-5", {"task-5": "visual"})
        assert reviewer == "thinker"

        # Unknown → Thinker (fallback)
        reviewer = orchestrator

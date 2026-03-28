"""
Workflow state machine for P2-15: Workflow Orchestration.

Main execution engine that drives workflow nodes through their
state transitions with full control flow support.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from .context import ExecutionError, NodeStatus, WorkflowContext
from .definition import WorkflowDefinition
from .evaluator import ExpressionEvaluator
from .nodes import NodeEdge, NodeType, WorkflowNode


class ExecutionEventType(StrEnum):
    """Types of events emitted during workflow execution."""

    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_SKIPPED = "node_skipped"
    BRANCH_TAKEN = "branch_taken"
    LOOP_ITERATION_START = "loop_iteration_start"
    LOOP_ITERATION_END = "loop_iteration_end"
    LOOP_COMPLETED = "loop_completed"
    LOOP_BREAK = "loop_break"
    TRY_ENTERED = "try_entered"
    CATCH_TRIGGERED = "catch_triggered"
    FINALLY_EXECUTED = "finally_executed"
    COMPENSATION_TRIGGERED = "compensation_triggered"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"


@dataclass
class ExecutionEvent:
    """An event emitted during workflow execution."""

    event_type: ExecutionEventType
    timestamp: datetime
    workflow_id: str
    execution_id: str
    node_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


ExecutionObserver = Callable[[ExecutionEvent], None]


@dataclass
class ExecutionResult:
    """Result of executing a workflow."""

    success: bool
    workflow_id: str
    execution_id: str
    context: WorkflowContext
    events: list[ExecutionEvent] = field(default_factory=list)
    error: str | None = None
    error_type: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert execution result to dictionary."""
        return {
            "success": self.success,
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "context": self.context.to_dict(),
            "events": [
                {
                    "event_type": event.event_type.value,
                    "timestamp": event.timestamp.isoformat(),
                    "workflow_id": event.workflow_id,
                    "execution_id": event.execution_id,
                    "node_id": event.node_id,
                    "data": event.data,
                }
                for event in self.events
            ],
            "error": self.error,
            "error_type": self.error_type,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }


class WorkflowStateMachine:
    """
    State machine that executes workflow definitions.

    This is the main execution engine for P2-15 workflows. It handles:
    - Node state transitions (PENDING → RUNNING → SUCCESS/FAILED)
    - Control flow (IF/ELSE, WHILE, FOR_EACH, TRY_CATCH)
    - Error propagation and compensation
    - Resource constraint enforcement
    - Event emission for observability
    """

    def __init__(
        self,
        definition: WorkflowDefinition,
        context: WorkflowContext,
        evaluator: ExpressionEvaluator | None = None,
        observers: list[ExecutionObserver] | None = None,
    ):
        """
        Initialize the state machine.

        Args:
            definition: The workflow definition to execute.
            context: The workflow context for tracking state.
            evaluator: Optional expression evaluator. Creates default if None.
            observers: Optional list of observers for execution events.
        """
        self.definition = definition
        self.context = context
        self.evaluator = evaluator or ExpressionEvaluator()
        self.observers = observers or []

        # Execution state
        self._execution_queue: list[str] = []  # Nodes to execute
        self._active_nodes: set[str] = set()  # Currently executing nodes
        self._completed_nodes: set[str] = set()  # Completed nodes
        self._failed_nodes: set[str] = set()  # Failed nodes
        self._events: list[ExecutionEvent] = []  # Collected events
        self._loop_continuations: dict[str, dict[str, Any]] = {}  # Loop state
        self._propagate_error_after_compensation: str | None = None  # Pending error

        # Initialize execution queue with entry node
        if definition.entry_node_id:
            self._execution_queue.append(definition.entry_node_id)

    def execute(self) -> ExecutionResult:
        """
        Execute the workflow.

        Returns:
            ExecutionResult with success/failure status and context.
        """
        started_at = datetime.now()

        # Emit workflow started event
        self._emit_event(
            ExecutionEventType.WORKFLOW_STARTED,
            node_id=None,
            data={"started_at": started_at.isoformat()},
        )

        try:
            # Main execution loop
            while self._execution_queue or self._active_nodes:
                # Process completed nodes first
                self._process_completed_nodes()

                # Start new nodes if we have capacity
                self._start_available_nodes()

                # If nothing is happening but we still have nodes in queue,
                # we might be waiting for external tasks to complete
                if not self._active_nodes and self._execution_queue:
                    # This would be where we'd wait for async tasks
                    # For now, we'll just process them synchronously
                    pass

            # Check if workflow completed successfully
            success = self._check_workflow_completion()

            # If a compensation error is pending, workflow is failed
            if self._propagate_error_after_compensation:
                success = False

            if success:
                self._emit_event(
                    ExecutionEventType.WORKFLOW_COMPLETED,
                    node_id=None,
                    data={"success": True},
                )
            else:
                self._emit_event(
                    ExecutionEventType.WORKFLOW_FAILED,
                    node_id=None,
                    data={"success": False},
                )

            completed_at = datetime.now()

            return ExecutionResult(
                success=success,
                workflow_id=self.definition.workflow_id,
                execution_id=self.context.execution_id,
                context=self.context,
                events=self._events,
                started_at=started_at,
                completed_at=completed_at,
            )

        except Exception as e:
            # Workflow execution failed with an unexpected error
            completed_at = datetime.now()

            self._emit_event(
                ExecutionEventType.WORKFLOW_FAILED,
                node_id=None,
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

            return ExecutionResult(
                success=False,
                workflow_id=self.definition.workflow_id,
                execution_id=self.context.execution_id,
                context=self.context,
                events=self._events,
                error=str(e),
                error_type=type(e).__name__,
                started_at=started_at,
                completed_at=completed_at,
            )

    def _process_completed_nodes(self) -> None:
        """Process nodes that have completed execution."""
        # This would normally check for completed async tasks
        # For now, we'll handle it in _execute_node
        pass

    def _start_available_nodes(self) -> None:
        """Start execution of available nodes."""
        # For simplicity, we'll execute nodes one at a time
        # In a real implementation, this would handle parallelism
        while self._execution_queue and len(self._active_nodes) == 0:
            node_id = self._execution_queue.pop(0)
            self._execute_node(node_id)

    def _execute_node(self, node_id: str) -> None:
        """
        Execute a single workflow node.

        This method handles the different node types and their
        control flow behaviors.
        """
        node = self.definition.get_node(node_id)

        # Mark node as active
        self._active_nodes.add(node_id)
        self.context.mark_node_started(node_id)

        self._emit_event(
            ExecutionEventType.NODE_STARTED,
            node_id=node_id,
            data={"node_type": node.node_type.value},
        )

        try:
            # Execute based on node type
            if node.node_type == NodeType.TASK:
                self._execute_task_node(node)
            elif node.node_type == NodeType.PARALLEL:
                self._execute_parallel_node(node)
            elif node.node_type == NodeType.SEQUENCE:
                self._execute_sequence_node(node)
            elif node.node_type == NodeType.IF:
                self._execute_if_node(node)
            elif node.node_type == NodeType.WHILE:
                self._execute_while_node(node)
            elif node.node_type == NodeType.FOR_EACH:
                self._execute_for_each_node(node)
            elif node.node_type == NodeType.TRY_CATCH:
                self._execute_try_catch_node(node)
            elif node.node_type == NodeType.COMPENSATE:
                self._execute_compensate_node(node)
            elif node.node_type == NodeType.SUB_WORKFLOW:
                self._execute_sub_workflow_node(node)
            else:
                raise ExecutionError(f"Unknown node type: {node.node_type}")

            # Mark node as completed — use discard for control-flow nodes
            # that manage their own lifecycle (loop nodes, TRY_CATCH)
            self._active_nodes.discard(node_id)

            # Only mark completed and schedule successors for non-loop/try_catch
            # nodes (loop and try_catch nodes handle this themselves)
            if node.node_type not in (
                NodeType.WHILE,
                NodeType.FOR_EACH,
                NodeType.TRY_CATCH,
            ):
                self._completed_nodes.add(node_id)
                self._schedule_successors(node)
                # Check if completing this node means a parent TRY_CATCH is done
                self._check_try_catch_completion(node_id)
            # Control-flow nodes (WHILE, FOR_EACH, TRY_CATCH) handle their own
            # lifecycle via _complete_loop_node, _complete_for_each_node,
            # _check_try_catch_completion, or _handle_try_catch_exception

        except Exception as e:
            # Node execution failed
            self._active_nodes.discard(node_id)
            self._failed_nodes.add(node_id)
            self.context.mark_node_failed(node_id, str(e), type(e).__name__)

            self._emit_event(
                ExecutionEventType.NODE_FAILED,
                node_id=node_id,
                data={"error": str(e), "error_type": type(e).__name__},
            )

            # Check if we're inside a TRY_CATCH block
            try_catch_node_id = self._find_active_try_catch()
            if try_catch_node_id:
                self._handle_try_catch_exception(try_catch_node_id, node_id, e)
            else:
                # Trigger compensation if configured
                self._trigger_compensation(node)

                # If compensation tasks were queued, let them execute
                # before propagating the error
                if self._execution_queue:
                    self._propagate_error_after_compensation = str(e)
                else:
                    raise

    def _execute_task_node(self, node: WorkflowNode) -> None:
        """Execute a TASK node."""
        # In a real implementation, this would delegate to P2-11/P2-12
        # For now, we'll simulate task execution
        if not node.task_id:
            raise ExecutionError(f"Task node '{node.node_id}' has no task_id")

        # Simulate task execution
        # TODO: Integrate with P2-11 ParallelEngine and P2-12 LLM Executor
        outputs = {"simulated": True, "task_id": node.task_id}

        self.context.mark_node_success(node.node_id, outputs)

        self._emit_event(
            ExecutionEventType.NODE_COMPLETED,
            node_id=node.node_id,
            data={"outputs": outputs},
        )

    def _execute_parallel_node(self, node: WorkflowNode) -> None:
        """Execute a PARALLEL node."""
        # Schedule all children for parallel execution
        for child_id in node.children:
            self._execution_queue.append(child_id)

        # Mark parallel node as successful (it just schedules children)
        self.context.mark_node_success(node.node_id, {"children": node.children})

        self._emit_event(
            ExecutionEventType.NODE_COMPLETED,
            node_id=node.node_id,
            data={"children": node.children},
        )

    def _execute_sequence_node(self, node: WorkflowNode) -> None:
        """Execute a SEQUENCE node."""
        # Schedule children in reverse order (so first child executes first)
        for child_id in reversed(node.children):
            self._execution_queue.insert(0, child_id)

        # Mark sequence node as successful (it just schedules children)
        self.context.mark_node_success(node.node_id, {"children": node.children})

        self._emit_event(
            ExecutionEventType.NODE_COMPLETED,
            node_id=node.node_id,
            data={"children": node.children},
        )

    def _execute_if_node(self, node: WorkflowNode) -> None:
        """Execute an IF node."""
        if not node.condition:
            raise ExecutionError(f"If node '{node.node_id}' has no condition")

        # Evaluate condition
        condition_result = self.evaluator.evaluate_condition(
            node.condition,
            self.context,
            node.node_id,
        )

        # Schedule appropriate branch
        if condition_result:
            branch_nodes = node.true_branch
            branch_name = "true"
        else:
            branch_nodes = node.false_branch
            branch_name = "false"

        # Schedule branch nodes in reverse order (so first executes first)
        for branch_id in reversed(branch_nodes):
            self._execution_queue.insert(0, branch_id)

        # Mark if node as successful
        self.context.mark_node_success(
            node.node_id,
            {
                "condition_result": condition_result,
                "branch_taken": branch_name,
                "true_branch": node.true_branch,
                "false_branch": node.false_branch,
            },
        )

        self._emit_event(
            ExecutionEventType.BRANCH_TAKEN,
            node_id=node.node_id,
            data={
                "condition": node.condition.expression,
                "result": condition_result,
                "branch": branch_name,
            },
        )

        self._emit_event(
            ExecutionEventType.NODE_COMPLETED,
            node_id=node.node_id,
            data={"condition_result": condition_result},
        )

    def _execute_while_node(self, node: WorkflowNode) -> None:
        """Execute a WHILE node using continuation-based looping."""
        if not node.loop_condition:
            raise ExecutionError(f"While node '{node.node_id}' has no loop condition")

        # Get or initialize continuation state
        cont = self._loop_continuations.get(node.node_id, {"iteration": 0})
        iteration = cont["iteration"]

        # Safety: check max iterations first
        if iteration >= node.max_iterations:
            self._emit_event(
                ExecutionEventType.LOOP_BREAK,
                node_id=node.node_id,
                data={"reason": "max_iterations_exceeded", "max_iterations": node.max_iterations},
            )
            self._complete_loop_node(node, iteration, completed=False)
            return

        # Evaluate loop condition
        condition_result = self.evaluator.evaluate_condition(
            node.loop_condition, self.context, node.node_id
        )

        if not condition_result:
            # Loop finished normally
            self._complete_loop_node(node, iteration, completed=True)
            return

        # Increment iteration
        iteration = self.context.increment_iteration(node.node_id)
        self._loop_continuations[node.node_id] = {"iteration": iteration}

        self._emit_event(
            ExecutionEventType.LOOP_ITERATION_START,
            node_id=node.node_id,
            data={"iteration": iteration},
        )

        # Schedule body nodes at front, then re-schedule self at back
        # Body nodes (insert(0)) execute before the re-scheduled loop (append)
        for body_id in reversed(node.loop_body):
            self._execution_queue.insert(0, body_id)
        self._execution_queue.append(node.node_id)

        # Remove from active so body can run
        self._active_nodes.discard(node.node_id)

    def _execute_for_each_node(self, node: WorkflowNode) -> None:
        """Execute a FOR_EACH node using continuation-based iteration."""
        if not node.collection_expression:
            raise ExecutionError(
                f"ForEach node '{node.node_id}' has no collection expression"
            )

        # Evaluate collection once (cached for subsequent iterations)
        if node.node_id not in self._loop_continuations:
            collection = self.evaluator.evaluate_collection(
                node.collection_expression, self.context, node.node_id
            )
            self._loop_continuations[node.node_id] = {"index": 0, "collection": collection}
        else:
            collection = self._loop_continuations[node.node_id]["collection"]

        cont = self._loop_continuations[node.node_id]
        index = cont["index"]

        if index >= len(collection):
            # All elements processed
            self._complete_for_each_node(node, len(collection))
            return

        element = collection[index]
        self.context.set_variable(node.element_variable, element)
        self.context.set_variable(node.index_variable, index)

        iteration = self.context.increment_iteration(node.node_id)
        self._loop_continuations[node.node_id]["index"] = index + 1

        self._emit_event(
            ExecutionEventType.LOOP_ITERATION_START,
            node_id=node.node_id,
            data={"iteration": iteration, "index": index, "element": str(element)},
        )

        # Schedule body at front, re-schedule self at back
        for body_id in reversed(node.loop_body):
            self._execution_queue.insert(0, body_id)
        self._execution_queue.append(node.node_id)

        self._active_nodes.discard(node.node_id)

    def _execute_try_catch_node(self, node: WorkflowNode) -> None:
        """Execute a TRY_CATCH node — schedule try body, handle errors in descendants."""
        self.context.push_to_stack(node.node_id)

        self._emit_event(ExecutionEventType.TRY_ENTERED, node_id=node.node_id, data={})

        # Schedule try body
        for try_id in reversed(node.try_body):
            self._execution_queue.insert(0, try_id)

        # Remove from active — completion is handled by _check_try_catch_completion
        # or by _handle_try_catch_exception
        self._active_nodes.discard(node.node_id)

    def _execute_compensate_node(self, node: WorkflowNode) -> None:
        """Execute a COMPENSATE node."""
        # Compensation nodes are executed when a previous node fails
        # For now, we'll just mark it as successful
        self.context.mark_node_success(node.node_id, {"compensation": True})

        self._emit_event(
            ExecutionEventType.COMPENSATION_TRIGGERED,
            node_id=node.node_id,
            data={},
        )

        self._emit_event(
            ExecutionEventType.NODE_COMPLETED,
            node_id=node.node_id,
            data={},
        )

    def _execute_sub_workflow_node(self, node: WorkflowNode) -> None:
        """Execute a SUB_WORKFLOW node."""
        # Sub-workflows would reference another workflow definition
        # For now, we'll simulate it
        self.context.mark_node_success(
            node.node_id,
            {
                "sub_workflow": True,
                "simulated": True,
            },
        )

        self._emit_event(
            ExecutionEventType.NODE_COMPLETED,
            node_id=node.node_id,
            data={"sub_workflow": True},
        )

    def _complete_loop_node(
        self, node: WorkflowNode, iterations: int, completed: bool
    ) -> None:
        """Complete a WHILE loop node."""
        self.context.mark_node_success(node.node_id, {
            "iterations": iterations,
            "completed": completed,
            "max_iterations": node.max_iterations,
        })
        self._completed_nodes.add(node.node_id)
        self._loop_continuations.pop(node.node_id, None)
        self.context.reset_iteration(node.node_id)

        self._emit_event(
            ExecutionEventType.LOOP_COMPLETED,
            node_id=node.node_id,
            data={"iterations": iterations, "completed": completed},
        )
        self._emit_event(
            ExecutionEventType.NODE_COMPLETED,
            node_id=node.node_id,
            data={"iterations": iterations},
        )
        self._schedule_successors(node)

    def _complete_for_each_node(self, node: WorkflowNode, total_elements: int) -> None:
        """Complete a FOR_EACH loop node."""
        self.context.mark_node_success(node.node_id, {
            "collection_size": total_elements,
            "iterations": total_elements,
            "element_variable": node.element_variable,
            "index_variable": node.index_variable,
        })
        self._completed_nodes.add(node.node_id)
        self._loop_continuations.pop(node.node_id, None)
        self.context.reset_iteration(node.node_id)

        # Clear iteration variables
        self.context.variables.pop(node.element_variable, None)
        self.context.variables.pop(node.index_variable, None)

        self._emit_event(
            ExecutionEventType.LOOP_COMPLETED,
            node_id=node.node_id,
            data={"iterations": total_elements},
        )
        self._emit_event(
            ExecutionEventType.NODE_COMPLETED,
            node_id=node.node_id,
            data={"collection_size": total_elements},
        )
        self._schedule_successors(node)

    def _find_active_try_catch(self) -> str | None:
        """Find an active TRY_CATCH ancestor on the execution stack."""
        for nid in reversed(self.context.execution_stack):
            if nid not in self.definition.nodes:
                continue
            ancestor = self.definition.get_node(nid)
            if ancestor.node_type == NodeType.TRY_CATCH:
                return nid
        return None

    def _handle_try_catch_exception(
        self, try_catch_id: str, failed_node_id: str, error: Exception
    ) -> None:
        """Route exception to a TRY_CATCH node's catch handler."""
        node = self.definition.get_node(try_catch_id)

        self.context.push_error(failed_node_id, str(error))

        self._emit_event(
            ExecutionEventType.CATCH_TRIGGERED,
            node_id=try_catch_id,
            data={
                "failed_node": failed_node_id,
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )

        # Find matching catch handler
        catch_handler = self._select_catch_handler(node, error)

        if catch_handler:
            self._execution_queue.insert(0, catch_handler.target_node_id)

        # Schedule finally body if not already queued
        if node.finally_body:
            for fid in reversed(node.finally_body):
                if fid not in self._completed_nodes and fid not in self._execution_queue:
                    self._execution_queue.append(fid)

        # Clear queued body nodes that shouldn't run after exception
        remaining_body = [
            bid for bid in node.try_body
            if bid not in self._completed_nodes and bid != failed_node_id
        ]
        for bid in remaining_body:
            if bid in self._execution_queue:
                self._execution_queue.remove(bid)

        # Mark TRY_CATCH as handled
        self._active_nodes.discard(try_catch_id)
        self._completed_nodes.add(try_catch_id)
        self.context.mark_node_success(try_catch_id, {
            "exception_caught": True,
            "error": str(error),
            "error_type": type(error).__name__,
            "failed_node": failed_node_id,
            "catch_handler": catch_handler.target_node_id if catch_handler else None,
        })

        # Pop from execution stack
        if self.context.peek_stack() == try_catch_id:
            self.context.pop_from_stack()

    def _select_catch_handler(
        self, try_catch_node: WorkflowNode, error: Exception
    ) -> NodeEdge | None:
        """Select the most specific catch handler for the given error."""
        if not try_catch_node.catch_handlers:
            return None

        # Sort by priority (highest first)
        handlers = sorted(
            try_catch_node.catch_handlers,
            key=lambda h: h.priority,
            reverse=True,
        )

        for handler in handlers:
            if handler.condition:
                # Condition-based matching
                eval_context = self.context.get_evaluation_context(try_catch_node.node_id)
                eval_context["error"] = str(error)
                eval_context["error_type"] = type(error).__name__
                try:
                    if handler.condition.evaluate(eval_context):
                        return handler
                except Exception:
                    continue
            else:
                # No condition = catch-all
                return handler

        return None

    def _check_try_catch_completion(self, completed_node_id: str) -> None:
        """Check if completing this node means a parent TRY_CATCH is done."""
        for stack_id in reversed(self.context.execution_stack):
            if stack_id not in self.definition.nodes:
                continue
            ancestor = self.definition.get_node(stack_id)
            if ancestor.node_type == NodeType.TRY_CATCH:
                # Check if all try_body nodes completed (success, failed-caught, or skipped)
                all_done = all(
                    (rid := self.context.get_node_result(bid))
                    and rid.status in (NodeStatus.SUCCESS, NodeStatus.FAILED, NodeStatus.SKIPPED)
                    for bid in ancestor.try_body
                )
                if all_done:
                    if self.context.peek_stack() == stack_id:
                        self.context.pop_from_stack()
                    if stack_id not in self._completed_nodes:
                        self._completed_nodes.add(stack_id)
                        self.context.mark_node_success(stack_id, {"exception_caught": False})
                        self._emit_event(
                            ExecutionEventType.NODE_COMPLETED,
                            node_id=stack_id,
                            data={"exception_caught": False},
                        )
                        self._schedule_successors(ancestor)
                break

    def _schedule_successors(self, node: WorkflowNode) -> None:
        """Schedule successor nodes based on edges."""
        for edge in node.edges:
            should_follow = False

            if edge.edge_type == "unconditional":
                should_follow = True
            elif edge.edge_type == "conditional" and edge.condition:
                should_follow = self.evaluator.evaluate_condition(
                    edge.condition,
                    self.context,
                    node.node_id,
                )
            elif edge.edge_type == "error":
                # Follow error edges only if node failed
                node_result = self.context.get_node_result(node.node_id)
                should_follow = node_result is not None and node_result.failed
            elif edge.edge_type == "compensation":
                # Follow compensation edges only if compensation is triggered
                # This would be determined by compensation logic
                pass

            if should_follow:
                self._execution_queue.append(edge.target_node_id)

    def _trigger_compensation(self, node: WorkflowNode) -> None:
        """Trigger compensation actions for a failed node."""
        for compensation in node.compensations:
            node_result = self.context.get_node_result(node.node_id)
            if node_result and node_result.status.value in compensation.trigger_on:
                self._execution_queue.append(compensation.action_node_id)

                self._emit_event(
                    ExecutionEventType.COMPENSATION_TRIGGERED,
                    node_id=node.node_id,
                    data={
                        "compensation_action": compensation.action_node_id,
                        "trigger": node_result.status.value,
                    },
                )

    def _check_workflow_completion(self) -> bool:
        """Check if the workflow has completed successfully."""
        # Check if any exit nodes are completed successfully
        if self.definition.exit_node_ids:
            for exit_id in self.definition.exit_node_ids:
                result = self.context.get_node_result(exit_id)
                if result and result.success:
                    return True
            return False

        # If no exit nodes defined, check if all nodes are completed
        for node_id in self.definition.nodes:
            result = self.context.get_node_result(node_id)
            if not result or result.status not in (
                NodeStatus.SUCCESS,
                NodeStatus.SKIPPED,
            ):
                return False

        return True

    def _emit_event(
        self,
        event_type: ExecutionEventType,
        node_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit an execution event to all observers."""
        event = ExecutionEvent(
            event_type=event_type,
            timestamp=datetime.now(),
            workflow_id=self.definition.workflow_id,
            execution_id=self.context.execution_id,
            node_id=node_id,
            data=data or {},
        )

        self._events.append(event)

        for observer in self.observers:
            try:
                observer(event)
            except Exception:
                # Don't let observer errors break execution
                pass

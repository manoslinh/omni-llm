# Orchestration Architecture Guide

## Overview

Omni-LLM's orchestration system enables intelligent coordination of multiple AI agents to solve complex development tasks. The system automatically decomposes tasks, routes them to appropriate models, executes them in parallel when possible, and integrates results.

## Architecture Components

### 1. Model Router
The Model Router is the brain of the orchestration system, responsible for selecting the most appropriate model for each task based on multiple factors:

```python
from omni.router import CostOptimizedStrategy, ModelRouter, RouterConfig

# Create router with cost-optimized strategy
config = RouterConfig()
router = ModelRouter(config)
router.register_strategy("cost_optimized", CostOptimizedStrategy())

# Router considers:
# 1. Task type (code generation, analysis, review, etc.)
# 2. Required capabilities (long context, reasoning, etc.)
# 3. Cost constraints (budget per task)
# 4. Quality requirements (accuracy, completeness)
# 5. Latency requirements (real-time vs batch)
```

**Key Features:**
- **Cost-aware routing**: Automatically selects cheapest capable model
- **Task-type matching**: Different models for different task types
- **Fallback chains**: If primary model fails, automatically tries alternatives
- **Real-time adaptation**: Adjusts routing based on performance metrics

### 2. Task Decomposition Flow

Complex tasks are automatically broken down into manageable subtasks:

```
User Request
    ↓
Task Analyzer (assesses complexity, dependencies)
    ↓
Decomposition Engine (breaks into subtasks)
    ↓
Dependency Graph Builder (creates execution order)
    ↓
Parallelizability Analyzer (identifies parallel opportunities)
```

**Example:**
```python
from omni.decomposition import TaskDecompositionEngine
from omni.decomposition.complexity_analyzer import ComplexityAnalyzer

decomposer = TaskDecompositionEngine()
analyzer = ComplexityAnalyzer()

task = "Refactor the authentication system to use OAuth2"
complexity = analyzer.analyze(task)  # Returns complexity score

if complexity.score > 7:
    # Complex task - decompose
    task_graph = decomposer.decompose(task)
    print(f"Decomposed into {task_graph.size} subtasks")
```

### 3. Multi-Agent Coordination

The coordination engine manages multiple agents working together:

```python
from omni.coordination import CoordinationEngine

coordinator = CoordinationEngine()

# Coordinate task execution
# (Agent matching and assignment handled internally)
result = await coordinator.coordinate(task_graph)
```

**Coordination Patterns:**
- **Supervisor-Worker**: One agent plans, others execute
- **Parallel Independent**: Multiple agents work on independent subtasks
- **Pipeline Sequential**: Agents work in sequence (output → input)
- **Review Cycle**: Implementer + reviewer pairs

### 4. Workflow Templates

Predefined workflow templates standardize common development processes:

**Template Structure:**
```yaml
name: "Code Review Workflow"
description: "Standard code review process with automated checks"
version: "1.1.0"

variables:
  filename:
    description: "File to review"
    required: true
    type: "string"
  strictness:
    description: "Review strictness level"
    default: "medium"
    type: "string"
    enum: ["low", "medium", "high"]

steps:
  - name: "static_analysis"
    task_type: "analysis"
    description: "Run static analysis on {filename}"
    agent: "intern"
    timeout: 300  # seconds

  - name: "security_scan"
    task_type: "security"
    description: "Security vulnerability scan"
    depends_on: ["static_analysis"]
    agent: "coder"
    condition: "{strictness} in ['medium', 'high']"

  - name: "code_review"
    task_type: "code_review"
    description: "Human-like code review of {filename}"
    depends_on: ["static_analysis", "security_scan"]
    agent: "reader"
    
  - name: "fix_implementation"
    task_type: "code_generation"
    description: "Implement fixes based on review"
    depends_on: ["code_review"]
    agent: "coder"
    condition: "has_issues"  # Dynamic condition
```

**Template Features:**
- **Variables**: Parameterize workflows
- **Conditions**: Conditional step execution
- **Dependencies**: Control execution order
- **Timeouts**: Prevent hanging tasks
- **Retry logic**: Automatic retry on failure

## Execution Flow

### Phase 1: Planning
1. **Task Analysis**: Understand requirements and constraints
2. **Decomposition**: Break into atomic subtasks
3. **Dependency Analysis**: Identify execution order
4. **Resource Allocation**: Assign agents and models
5. **Cost Estimation**: Predict total cost

### Phase 2: Execution
1. **Parallel Wave Execution**: Execute independent tasks simultaneously
2. **State Management**: Track progress and handle failures
3. **Result Collection**: Gather outputs from all agents
4. **Conflict Detection**: Identify conflicting changes

### Phase 3: Integration
1. **Result Merging**: Combine outputs from parallel execution
2. **Conflict Resolution**: Resolve conflicting changes
3. **Quality Verification**: Run verification pipeline
4. **Final Assembly**: Produce final output

## Example: Complete Orchestration Pipeline

```python
from omni.orchestration import WorkflowEngine

engine = WorkflowEngine()

# Load and execute a workflow template
template = engine.load_template("path/to/workflow.yaml")
result = engine.execute(
    template,
    variables={"feature_name": "user-authentication"}
)

print(f"Success: {result.success}")
print(f"Cost: ${result.total_cost:.4f}")
print(f"Summary: {result.summary}")
```

## Monitoring and Observability

The orchestration system provides comprehensive observability:

```python
from omni.observability import metrics

# Track costs and success rates per provider
# (Dashboard UI available via 'omni status' CLI command)
```

## Best Practices

### 1. Task Decomposition
- Decompose until subtasks are atomic (single responsibility)
- Identify clear dependencies between subtasks
- Balance decomposition overhead vs parallelization benefits

### 2. Agent Selection
- Match task complexity to agent capability
- Consider cost-performance tradeoffs
- Use cheaper agents for simple, high-volume tasks

### 3. Workflow Design
- Start with simple templates and customize as needed
- Use variables for flexibility
- Include error handling and retry logic
- Set appropriate timeouts for each step

### 4. Cost Management
- Set per-task and per-workflow budgets
- Monitor cost in real-time
- Use cost-optimized routing for non-critical tasks

## Troubleshooting

### Common Issues and Solutions:

1. **High Costs**
   - Use cheaper models for simple tasks
   - Implement budget enforcement
   - Review task decomposition (may be too fine-grained)

2. **Slow Execution**
   - Increase parallelization where possible
   - Check for unnecessary dependencies
   - Consider faster models with quality tradeoffs

3. **Quality Issues**
   - Use higher-quality models for critical tasks
   - Implement review steps in workflows
   - Add verification pipelines

4. **Agent Coordination Failures**
   - Simplify dependency graphs
   - Add timeout and retry logic
   - Implement fallback agents

## Advanced Topics

### Health Monitoring
Track provider health with circuit breakers and sliding-window metrics:

```python
from omni.router.health import HealthConfig, HealthManager

manager = HealthManager(HealthConfig(
    error_rate_threshold=0.5,
    recovery_timeout_seconds=60.0,
))
manager.register_provider("openai/gpt-4")

# Providers automatically circuit-break on repeated failures
# and recover via HALF_OPEN probes
```

### Budget Enforcement
Enforce per-session and per-day spending limits:

```python
from omni.router.budget import BudgetConfig, BudgetTracker

tracker = BudgetTracker(
    config=BudgetConfig(daily_limit=5.0, per_session_limit=1.0),
    session_id="my-session",
)

allowed, reason = tracker.check_budget(estimated_cost=0.05)
```

## Conclusion

The Omni-LLM orchestration system provides a powerful framework for coordinating multiple AI agents to solve complex development tasks. By intelligently decomposing tasks, routing to appropriate models, and executing in parallel, it enables efficient, cost-effective automation of software development workflows.

For more detailed information, see:
- [Workflow Templates Guide](workflow-templates.md)
- [API Reference](../src/omni/orchestration/__init__.py)
- [Example Scripts](../examples/)
"""
Interactive Demo Command for Omni-LLM.

Shows multi-agent orchestration in action with engaging visualizations
and educational explanations.

Note: This demo is 100% simulated/mocked and does not require
orchestration features to be installed. It demonstrates the concepts
and benefits of parallel execution without making actual API calls.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

console = Console()

# Constants
SEQUENTIAL_OVERHEAD_FACTOR = 1.3  # 30% overhead for sequential execution


class DemoScenario(Enum):
    """Available demo scenarios."""
    BUILD_WEB_APP = "build_web_app"
    DEBUG_COMPLEX_ISSUE = "debug_complex_issue"
    ANALYZE_CODEBASE = "analyze_codebase"
    CUSTOM_TASK = "custom_task"


@dataclass
class DemoConfig:
    """Configuration for demo runs."""
    scenario: DemoScenario
    mock_execution: bool = True
    show_progress: bool = True
    explain_steps: bool = True
    simulate_delay: bool = True
    delay_multiplier: float = 1.0


@dataclass
class DemoResult:
    """Results from a demo run."""
    scenario: DemoScenario
    success: bool
    total_agents: int
    total_tasks: int
    estimated_sequential_cost: float
    estimated_parallel_cost: float
    estimated_time_saved: float
    generated_files: int
    execution_time: float
    cost_savings_percentage: float = field(init=False)
    cost_savings_amount: float = field(init=False)

    def __post_init__(self) -> None:
        """Calculate derived fields."""
        self.cost_savings_amount = self.estimated_sequential_cost - self.estimated_parallel_cost
        if self.estimated_sequential_cost > 0:
            self.cost_savings_percentage = (self.cost_savings_amount / self.estimated_sequential_cost) * 100
        else:
            self.cost_savings_percentage = 0.0


class DemoRunner:
    """Main demo runner class."""

    def __init__(self, config: DemoConfig) -> None:
        """Initialize the demo runner."""
        self.config = config
        self.scenarios_dir = Path(__file__).parent.parent.parent / "examples" / "demo_scenarios"
        self.scenarios_dir.mkdir(parents=True, exist_ok=True)

    def _show_welcome(self) -> None:
        """Show welcome message."""
        welcome_text = """
        [bold cyan]Welcome to Omni-LLM Demo! 🚀[/bold cyan]

        Let me show you what multi-agent orchestration
        can do for you.

        You'll see:
        • Task decomposition into atomic subtasks
        • Parallel execution with progress visualization
        • Real cost savings calculations
        • Result integration and validation
        """
        console.print(Panel(welcome_text, border_style="cyan"))

    def _select_scenario(self) -> DemoScenario:
        """Let user select a demo scenario."""
        console.print("\n[bold]Choose a demo scenario:[/bold]")

        scenarios = [
            ("🏗️  Build a Simple Web App", DemoScenario.BUILD_WEB_APP,
             "Shows task decomposition, parallel execution of backend/frontend, cost savings visualization"),
            ("🐛  Debug a Complex Issue", DemoScenario.DEBUG_COMPLEX_ISSUE,
             "Multiple agents analyzing different aspects, collaborative problem solving, result integration"),
            ("📊  Analyze a Codebase", DemoScenario.ANALYZE_CODEBASE,
             "Parallel analysis of different modules, architecture review, technical debt assessment"),
            ("🎯  Custom Task", DemoScenario.CUSTOM_TASK,
             "Enter your own task to see how omni-llm would handle it"),
        ]

        for i, (name, _scenario, description) in enumerate(scenarios, 1):
            console.print(f"\n{i}. {name}")
            console.print(f"   [dim]{description}[/dim]")

        while True:
            try:
                choice = IntPrompt.ask("\nEnter your choice", default=1, show_default=True)
                if 1 <= choice <= len(scenarios):
                    return scenarios[choice - 1][1]
                else:
                    console.print(f"[red]Please enter a number between 1 and {len(scenarios)}[/red]")
            except ValueError:
                console.print("[red]Please enter a valid number[/red]")

    def _load_scenario_data(self, scenario: DemoScenario) -> dict[str, Any]:
        """Load scenario data from YAML file or generate default."""
        scenario_file = self.scenarios_dir / f"{scenario.value}.yaml"

        if scenario_file.exists():
            with open(scenario_file) as f:
                data: dict[str, Any] | None = yaml.safe_load(f)
                if data is None:
                    # Return empty dict if YAML file is empty
                    return {}
                return data

        # Generate default scenario data
        if scenario == DemoScenario.BUILD_WEB_APP:
            return {
                "name": "Build a Simple Web App",
                "description": "Build a simple web app with user authentication",
                "goal": "Create a full-stack web application with user registration, login, and a dashboard",
                "subtasks": [
                    {
                        "id": "backend",
                        "name": "Backend API",
                        "description": "Create Python/FastAPI backend with REST endpoints",
                        "type": "coding",
                        "estimated_tokens": 1500,
                        "complexity": 0.6,
                    },
                    {
                        "id": "auth",
                        "name": "Authentication System",
                        "description": "Implement JWT-based authentication with password hashing",
                        "type": "coding",
                        "estimated_tokens": 1200,
                        "complexity": 0.7,
                    },
                    {
                        "id": "frontend",
                        "name": "Frontend UI",
                        "description": "Create React frontend with responsive design",
                        "type": "coding",
                        "estimated_tokens": 2000,
                        "complexity": 0.5,
                    },
                    {
                        "id": "database",
                        "name": "Database Schema",
                        "description": "Design and implement PostgreSQL database schema",
                        "type": "coding",
                        "estimated_tokens": 800,
                        "complexity": 0.4,
                    },
                ],
                "dependencies": [
                    {"from": "database", "to": "backend"},
                    {"from": "backend", "to": "auth"},
                ],
                "cost_rates": {
                    "coding": {"input": 1.0, "output": 3.0},
                },
            }
        elif scenario == DemoScenario.DEBUG_COMPLEX_ISSUE:
            return {
                "name": "Debug a Complex Issue",
                "description": "Debug a complex distributed system issue",
                "goal": "Identify and fix a race condition in a distributed message queue system",
                "subtasks": [
                    {
                        "id": "logs",
                        "name": "Log Analysis",
                        "description": "Analyze system logs for error patterns",
                        "type": "analysis",
                        "estimated_tokens": 800,
                        "complexity": 0.5,
                    },
                    {
                        "id": "code",
                        "name": "Code Review",
                        "description": "Review relevant source code for race conditions",
                        "type": "code_review",
                        "estimated_tokens": 1200,
                        "complexity": 0.7,
                    },
                    {
                        "id": "tests",
                        "name": "Test Analysis",
                        "description": "Analyze test failures and coverage",
                        "type": "analysis",
                        "estimated_tokens": 600,
                        "complexity": 0.4,
                    },
                    {
                        "id": "fix",
                        "name": "Fix Implementation",
                        "description": "Implement and test the fix",
                        "type": "coding",
                        "estimated_tokens": 1000,
                        "complexity": 0.6,
                    },
                ],
                "dependencies": [
                    {"from": "logs", "to": "code"},
                    {"from": "code", "to": "tests"},
                    {"from": "tests", "to": "fix"},
                ],
                "cost_rates": {
                    "analysis": {"input": 0.8, "output": 2.4},
                    "code_review": {"input": 1.2, "output": 3.6},
                    "coding": {"input": 1.0, "output": 3.0},
                },
            }
        elif scenario == DemoScenario.ANALYZE_CODEBASE:
            return {
                "name": "Analyze a Codebase",
                "description": "Comprehensive analysis of a codebase",
                "goal": "Analyze a Python codebase for architecture, quality, and technical debt",
                "subtasks": [
                    {
                        "id": "architecture",
                        "name": "Architecture Review",
                        "description": "Review overall architecture and design patterns",
                        "type": "architecture",
                        "estimated_tokens": 1500,
                        "complexity": 0.8,
                    },
                    {
                        "id": "quality",
                        "name": "Code Quality Analysis",
                        "description": "Analyze code quality metrics and linting results",
                        "type": "analysis",
                        "estimated_tokens": 1000,
                        "complexity": 0.5,
                    },
                    {
                        "id": "security",
                        "name": "Security Review",
                        "description": "Identify security vulnerabilities and best practices",
                        "type": "analysis",
                        "estimated_tokens": 1200,
                        "complexity": 0.7,
                    },
                    {
                        "id": "dependencies",
                        "name": "Dependency Analysis",
                        "description": "Analyze dependencies and version compatibility",
                        "type": "analysis",
                        "estimated_tokens": 800,
                        "complexity": 0.4,
                    },
                ],
                "dependencies": [],  # All can run in parallel
                "cost_rates": {
                    "architecture": {"input": 2.0, "output": 6.0},
                    "analysis": {"input": 0.8, "output": 2.4},
                },
            }
        else:  # CUSTOM_TASK
            return {
                "name": "Custom Task",
                "description": "User-defined task",
                "goal": "",
                "subtasks": [],
                "dependencies": [],
                "cost_rates": {
                    "coding": {"input": 1.0, "output": 3.0},
                    "analysis": {"input": 0.8, "output": 2.4},
                    "code_review": {"input": 1.2, "output": 3.6},
                    "architecture": {"input": 2.0, "output": 6.0},
                },
            }

    def _show_task_decomposition(self, scenario_data: dict[str, Any]) -> None:
        """Show task decomposition visualization."""
        if self.config.explain_steps:
            console.print("\n[bold cyan]1. Task Decomposition[/bold cyan]")
            console.print("[dim]Breaking the main goal into atomic, manageable subtasks[/dim]")

        goal = scenario_data["goal"]
        subtasks = scenario_data["subtasks"]

        # Show original task
        task_panel = Panel(
            f"[bold]Original Task:[/bold] \"{goal}\"",
            border_style="blue",
            padding=(1, 2),
        )
        console.print(task_panel)

        # Show decomposition tree
        if subtasks:
            console.print("\n📋 [bold]Decomposition Tree:[/bold]")

            for i, subtask in enumerate(subtasks, 1):
                emoji = "📝" if subtask["type"] == "coding" else "🔍" if subtask["type"] == "analysis" else "🏗️"
                console.print(f"   {emoji} {subtask['name']}")
                console.print(f"      [dim]{subtask['description']}[/dim]")

                if i < len(subtasks):
                    console.print("      │")

    def _show_parallel_execution(self, scenario_data: dict[str, Any]) -> tuple[Progress, dict[str, TaskID], list[list[str]]]:
        """Show parallel execution visualization."""
        if self.config.explain_steps:
            console.print("\n[bold cyan]2. Parallel Execution[/bold cyan]")
            console.print("[dim]Executing subtasks in parallel with dependency resolution[/dim]")

        subtasks = scenario_data["subtasks"]
        dependencies = scenario_data.get("dependencies", [])

        # Create dependency groups (waves)
        task_ids = [st["id"] for st in subtasks]
        dependency_map = {dep["to"]: dep["from"] for dep in dependencies}

        # Simple wave calculation (for demo purposes)
        waves = []
        remaining = set(task_ids)

        while remaining:
            # Find tasks with no dependencies or whose dependencies are done
            wave = []
            for task_id in list(remaining):
                if task_id not in dependency_map or dependency_map[task_id] not in remaining:
                    wave.append(task_id)

            if not wave:  # Circular dependency protection
                break

            waves.append(wave)
            remaining -= set(wave)

        # Create progress display
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        )

        # Create tasks in progress
        task_progress_map = {}
        for subtask in subtasks:
            task_id = progress.add_task(
                f"[cyan]{subtask['name']}[/cyan]",
                total=100,
                visible=False,  # Start hidden
            )
            task_progress_map[subtask["id"]] = task_id

        # Show execution waves
        console.print(f"\n⚡ [bold]Execution Plan ({len(waves)} waves):[/bold]")
        for i, wave in enumerate(waves, 1):
            wave_tasks = [st for st in subtasks if st["id"] in wave]
            console.print(f"   Wave {i}: {len(wave)} parallel tasks")
            for task in wave_tasks:
                console.print(f"     • {task['name']}")

        console.print("\n")
        return progress, task_progress_map, waves

    def _simulate_execution(
        self,
        progress: Progress,
        task_progress_map: dict[str, TaskID],
        waves: list[list[str]],
        scenario_data: dict[str, Any]
    ) -> tuple[float, int]:
        """Simulate task execution with progress updates."""
        subtasks = scenario_data["subtasks"]
        total_time = 0.0
        generated_files = 0

        with Live(progress, refresh_per_second=10):
            # Process each wave
            for wave_num, wave in enumerate(waves, 1):
                if self.config.explain_steps:
                    progress.console.print(f"\n[bold]Wave {wave_num} execution...[/bold]")

                # Show tasks in this wave
                for task_id in wave:
                    progress_task_id = task_progress_map[task_id]
                    progress.update(progress_task_id, visible=True)

                # Simulate parallel execution
                wave_tasks = [st for st in subtasks if st["id"] in wave]
                for subtask in wave_tasks:
                    progress_task_id = task_progress_map[subtask["id"]]

                    # Simulate work with progress updates
                    for i in range(0, 101, 10):
                        if self.config.simulate_delay:
                            time.sleep(0.1 * self.config.delay_multiplier)
                        progress.update(progress_task_id, completed=i)

                    # Count generated files (simulated)
                    if subtask["type"] == "coding":
                        generated_files += 2  # Simulate 2 files per coding task

                # Wave completion delay
                if self.config.simulate_delay:
                    time.sleep(0.5 * self.config.delay_multiplier)

                total_time += len(wave_tasks) * 1.0  # Simulate 1 second per task

        return total_time, generated_files

    def _calculate_costs(self, scenario_data: dict[str, Any], parallel_time: float) -> tuple[float, float]:
        """Calculate sequential vs parallel costs."""
        subtasks = scenario_data["subtasks"]

        # Calculate token costs
        total_input_tokens = 0
        total_output_tokens = 0

        for subtask in subtasks:
            estimated_tokens = subtask.get("estimated_tokens", 1000)

            # Split tokens between input/output (rough estimate)
            input_tokens = int(estimated_tokens * 0.4)
            output_tokens = int(estimated_tokens * 0.6)

            total_input_tokens += input_tokens
            total_output_tokens += output_tokens

        # Calculate costs per million tokens
        # Use average rates for demo
        avg_input_rate = 1.0  # $1 per million input tokens
        avg_output_rate = 3.0  # $3 per million output tokens

        # Convert tokens to millions for cost calculation
        input_tokens_millions = total_input_tokens / 1_000_000
        output_tokens_millions = total_output_tokens / 1_000_000

        # Parallel execution cost (what we actually use)
        parallel_cost = (input_tokens_millions * avg_input_rate +
                        output_tokens_millions * avg_output_rate)

        # Sequential execution would be ~30% more expensive due to context switching
        # and inability to optimize across tasks
        sequential_cost = parallel_cost * SEQUENTIAL_OVERHEAD_FACTOR

        return sequential_cost, parallel_cost

    def _show_cost_comparison(
        self,
        sequential_cost: float,
        parallel_cost: float,
        execution_time: float,
        generated_files: int
    ) -> None:
        """Show cost savings visualization."""
        if self.config.explain_steps:
            console.print("\n[bold cyan]3. Cost Analysis[/bold cyan]")
            console.print("[dim]Comparing sequential vs parallel execution costs[/dim]")

        savings = sequential_cost - parallel_cost
        savings_percent = (savings / sequential_cost * 100) if sequential_cost > 0 else 0

        # Create cost comparison table
        table = Table(title="💰 Cost Analysis", show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Sequential", style="red")
        table.add_column("Parallel", style="green")
        table.add_column("Savings", style="bold yellow")

        table.add_row(
            "Execution Cost",
            f"${sequential_cost:.4f}",
            f"${parallel_cost:.4f}",
            f"${savings:.4f} ({savings_percent:.1f}%)"
        )

        # Estimated time (sequential would be longer)
        sequential_time = execution_time * 1.5  # 50% longer sequentially
        time_saved = sequential_time - execution_time

        table.add_row(
            "Execution Time",
            f"{sequential_time:.1f}s",
            f"{execution_time:.1f}s",
            f"{time_saved:.1f}s saved"
        )

        table.add_row(
            "Files Generated",
            f"{generated_files}",
            f"{generated_files}",
            "Same output"
        )

        console.print(table)

    def _show_result_integration(self, result: DemoResult) -> None:
        """Show result integration and final summary."""
        if self.config.explain_steps:
            console.print("\n[bold cyan]4. Result Integration[/bold cyan]")
            console.print("[dim]Combining results from all agents into final output[/dim]")

        success_text = f"""
        [bold green]🎉 Demo Complete![/bold green]

        • {result.total_agents} agents worked {'in parallel' if result.total_agents > 1 else ''}
        • {result.total_tasks} tasks decomposed and executed
        • {result.generated_files} files generated
        • ${result.cost_savings_amount:.4f} saved ({result.cost_savings_percentage:.1f}% reduction!)
        • Completed in {result.execution_time:.1f} seconds

        [bold]Ready to try with your own tasks?[/bold]
        Run: [cyan]omni orchestrate "your goal here"[/cyan]
        """

        console.print(Panel(success_text, border_style="green"))

    def _get_custom_task(self) -> dict[str, Any]:
        """Get custom task from user."""
        console.print("\n[bold]Enter your custom task:[/bold]")

        goal = Prompt.ask("What would you like to accomplish?")

        # Estimate complexity based on goal length
        goal_length = len(goal)
        if goal_length < 50:
            complexity = 0.3
            subtask_count = 2
        elif goal_length < 100:
            complexity = 0.5
            subtask_count = 3
        else:
            complexity = 0.7
            subtask_count = 4

        # Generate simulated subtasks
        subtasks = []
        subtask_types = ["research", "planning", "coding", "testing", "documentation"]

        for i in range(subtask_count):
            subtask_type = subtask_types[i % len(subtask_types)]
            subtask_name = f"{subtask_type.title()} Phase"
            subtask_desc = f"Handle {subtask_type} aspects of: {goal[:50]}..."

            subtasks.append({
                "id": f"subtask_{i+1}",
                "name": subtask_name,
                "description": subtask_desc,
                "type": subtask_type,
                "estimated_tokens": 800 + (i * 200),
                "complexity": complexity * (0.8 + (i * 0.1)),
            })

        return {
            "name": "Custom Task",
            "description": "User-defined task",
            "goal": goal,
            "subtasks": subtasks,
            "dependencies": [],  # Simple linear for custom tasks
            "cost_rates": {
                "research": {"input": 0.7, "output": 2.1},
                "planning": {"input": 0.8, "output": 2.4},
                "coding": {"input": 1.0, "output": 3.0},
                "testing": {"input": 0.9, "output": 2.7},
                "documentation": {"input": 0.6, "output": 1.8},
            },
        }

    def run(self) -> DemoResult:
        """Run the demo."""
        self._show_welcome()

        # Select scenario
        scenario = self._select_scenario()
        self.config.scenario = scenario

        # Load scenario data
        if scenario == DemoScenario.CUSTOM_TASK:
            scenario_data = self._get_custom_task()
        else:
            scenario_data = self._load_scenario_data(scenario)

        # Show task decomposition
        self._show_task_decomposition(scenario_data)

        # Show parallel execution setup
        progress, task_progress_map, waves = self._show_parallel_execution(scenario_data)

        # Simulate execution
        start_time = time.time()
        execution_time, generated_files = self._simulate_execution(
            progress, task_progress_map, waves, scenario_data
        )
        actual_execution_time = time.time() - start_time

        # Calculate costs
        sequential_cost, parallel_cost = self._calculate_costs(scenario_data, execution_time)

        # Show cost comparison
        self._show_cost_comparison(
            sequential_cost,
            parallel_cost,
            execution_time,
            generated_files
        )

        # Create result
        result = DemoResult(
            scenario=scenario,
            success=True,
            total_agents=len(scenario_data["subtasks"]),
            total_tasks=len(scenario_data["subtasks"]),
            estimated_sequential_cost=sequential_cost,
            estimated_parallel_cost=parallel_cost,
            estimated_time_saved=execution_time * 0.5,  # 50% time saved estimate
            generated_files=generated_files,
            execution_time=actual_execution_time,
        )

        # Show final results
        self._show_result_integration(result)

        return result


def run_demo(fast: bool = False, silent: bool = False, scenario: str | None = None) -> None:
    """
    Interactive demo of Omni-LLM's multi-agent orchestration.

    Shows task decomposition, parallel execution, and cost savings
    in an engaging, educational format.
    """
    # Create config
    config = DemoConfig(
        scenario=DemoScenario(scenario) if scenario else DemoScenario.BUILD_WEB_APP,
        mock_execution=True,
        show_progress=True,
        explain_steps=not silent,
        simulate_delay=not fast,
        delay_multiplier=0.5 if fast else 1.0,
    )

    # Run demo
    runner = DemoRunner(config)

    try:
        result = runner.run()

        if result.success:
            console.print("\n[green]✅ Demo completed successfully![/green]")
        else:
            console.print("\n[yellow]⚠️  Demo completed with warnings[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Demo cancelled by user[/yellow]")
    except Exception as e:
        console.print(f"[red]❌ Demo failed: {e}[/red]")
        raise

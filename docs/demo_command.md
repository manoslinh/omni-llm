# Omni-LLM Demo Command

The `omni demo` command is an interactive showcase of Omni-LLM's multi-agent orchestration capabilities. It's designed to help users understand the value of parallel AI agent execution through engaging visualizations and educational explanations.

## Quick Start

```bash
# Run the interactive demo
omni demo

# Run in fast mode (no delays)
omni demo --fast

# Run without explanations
omni demo --silent

# Run a specific scenario
omni demo --scenario build_web_app
```

## Available Scenarios

### 1. 🏗️ Build a Simple Web App
**Focus:** Task decomposition and parallel execution
- Shows how a complex goal is broken into atomic subtasks
- Demonstrates parallel execution of backend, frontend, auth, and database tasks
- Visualizes cost savings from parallel vs sequential execution

### 2. 🐛 Debug a Complex Issue
**Focus:** Dependency management and collaborative problem solving
- Shows sequential task execution with dependencies
- Demonstrates how multiple agents analyze different aspects of a problem
- Highlights result integration and validation

### 3. 📊 Analyze a Codebase
**Focus:** Maximum parallelization
- Shows completely parallel execution of architecture, quality, security, and dependency analysis
- Demonstrates the power of parallel execution when tasks are independent
- Visualizes maximum cost savings potential

### 4. 🎯 Custom Task
**Focus:** User-defined scenarios
- Enter your own task to see how Omni-LLM would handle it
- Automatic complexity estimation and task decomposition
- Customized cost calculations based on your input

## Demo Features

### Task Decomposition Visualization
```
📋 Original Task: "Build a simple web app with user authentication"
├── 📝 Backend API (Python/FastAPI)
├── 🔐 Authentication system
├── 🎨 Frontend UI (React)
└── 🗄️ Database schema
```

### Parallel Execution Progress
```
⚡ Executing 4 agents in parallel:
• Agent 1: Backend API      [██████░░░░] 60%
• Agent 2: Authentication   [████████░░] 80%
• Agent 3: Frontend UI      [███░░░░░░░] 30%
• Agent 4: Database         [██████████] 100%
```

### Cost Savings Analysis
```
💰 Cost Analysis:
• Sequential execution: $0.45 (estimated)
• Parallel execution:   $0.18 (actual)
• Savings:             $0.27 (60% reduction!)
```

### Result Integration
```
🎉 Demo Complete!
• 4 agents worked in parallel
• Generated 12 files
• Saved 60% on costs
• Completed in 2.3 minutes

Ready to try with your own tasks? Run:
$ omni orchestrate "your goal here"
```

## Technical Implementation

### Files
- `src/omni/cli/demo.py` - Main demo runner implementation
- `src/omni/cli/main.py` - CLI command integration
- `examples/demo_scenarios/` - YAML scenario definitions
- `tests/test_demo.py` - Unit and integration tests

### Key Components
1. **DemoRunner** - Main orchestrator class
2. **DemoConfig** - Configuration dataclass
3. **DemoScenario** - Scenario enumeration
4. **DemoResult** - Results dataclass

### Dependencies
- `rich` - Terminal formatting and progress bars
- `click` - CLI framework
- `pyyaml` - Scenario file parsing

## Educational Value

The demo command teaches users about:

1. **Task Decomposition** - How complex goals are broken into manageable pieces
2. **Dependency Analysis** - Understanding task relationships and execution order
3. **Parallel Execution** - The benefits of running multiple agents simultaneously
4. **Cost Optimization** - How parallel execution reduces API costs
5. **Result Integration** - How agent outputs are combined into final results

## Testing

Run the demo tests:
```bash
pytest tests/test_demo.py -v
```

Test specific functionality:
```bash
# Test scenario loading
python3 -c "from omni.cli.demo import DemoRunner, DemoConfig, DemoScenario; \
config = DemoConfig(scenario=DemoScenario.BUILD_WEB_APP); \
runner = DemoRunner(config); \
print('Demo system functional')"
```

## Integration with Omni-LLM

The demo command integrates with existing Omni-LLM components:

- Uses the same task decomposition logic as the orchestration engine
- Follows the same cost calculation patterns
- Demonstrates real orchestration concepts (though with simulated execution)
- Provides a bridge to the full `omni orchestrate` command

## Future Enhancements

Potential improvements for the demo command:

1. **Real API Integration** - Option to use actual API calls (with user consent)
2. **More Scenarios** - Additional pre-built demo scenarios
3. **Custom Scenario Files** - Load scenarios from user-defined YAML files
4. **Performance Metrics** - Real-time performance tracking
5. **Export Results** - Save demo results for comparison

## Conclusion

The `omni demo` command is a powerful educational tool that demonstrates the value of multi-agent orchestration. By showing concrete examples of task decomposition, parallel execution, and cost savings, it helps users understand how Omni-LLM can accelerate their development workflow while reducing costs.
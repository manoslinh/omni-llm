# Omni-LLM

**The orchestration OS for AI-assisted development**

> Stop choosing between models. Use the best one for each task. Save 40-60%.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
*Note: GitHub Actions badges will appear after repository creation*

Omni-LLM is a CLI tool that orchestrates multiple LLMs for coding tasks, automatically routing each task to the most cost-effective model that meets quality requirements.

## Why Omni-LLM?

| Problem | Omni-LLM Solution |
|---------|-------------------|
| **Vendor lock-in** | Works with any LLM (OpenAI, Anthropic, Google, DeepSeek, local models) |
| **Cost opacity** | Real-time cost tracking and predictive routing |
| **One-size-fits-all models** | Task-aware routing (Claude for architecture, DeepSeek for boilerplate) |
| **Manual context management** | Smart RepoMap + semantic search + compression |
| **Limited verification** | Multi-layer pipeline (lint + test + type-check + security) |

## Quick Start

```bash
# Install
pipx install omni-llm

# Configure your API keys
omni config set openai.api_key sk-...
omni config set anthropic.api_key sk-...

# Use it!
omni "add error handling to parser.py"
```

## Key Features

### 🎯 **Smart Model Routing**
- **Cost-aware**: Automatically picks cheapest capable model
- **Task-aware**: Different models for different task types
- **Fallback chains**: If one model fails, try another

### 💰 **Cost Optimization**
- **Predictive costing**: Estimate cost before sending
- **Budget enforcement**: Set per-project, per-session limits
- **Detailed breakdown**: See exactly what you spent on each task

### 🏗️ **Multi-Agent Orchestration** (Phase 2+)
- **Supervisor-worker pattern**: One agent plans, others execute
- **Parallel execution**: Multiple agents work simultaneously
- **Conflict resolution**: Smart merging of parallel work

### 🔧 **Developer Experience**
- **Git-native**: Every change is reversible via git
- **Context-aware**: RepoMap understands your codebase structure
- **Verification pipeline**: Lint + test + type-check + security scan

## Architecture

```
CLI → Orchestration → Agent/Model Providers → Infrastructure
```

### Core Components:
1. **Model Router**: Cost/quality-aware model selection
2. **Edit Loop**: send → parse → apply → verify → reflect cycle
3. **RepoMap**: PageRank + tree-sitter for codebase understanding
4. **Verification Pipeline**: Multi-layer quality checks
5. **Git Integration**: Worktree isolation, AI attribution, undo

## Orchestration Examples

### Single Agent with Smart Routing
```python
from omni.router import ModelRouter
from omni.task.models import Task, TaskType

router = ModelRouter()
task = Task(
    description="Add error handling to the authentication module",
    task_type=TaskType.CODE_GENERATION
)

# Router automatically selects best model based on task type and cost
selected_model = router.select_model(task)
print(f"Selected model: {selected_model}")
# Output: deepseek/deepseek-chat (cost-effective for code generation)
```

### Multi-Agent Parallel Execution
```python
from omni.coordination import CoordinationEngine
from omni.decomposition import TaskDecompositionEngine

# Decompose complex task into subtasks
decomposer = TaskDecompositionEngine()
task_graph = decomposer.decompose("Refactor the entire codebase for performance")

# Coordinate multiple agents to work in parallel
coordinator = CoordinationEngine()
workflow_plan = coordinator.coordinate(task_graph)

# Execute in parallel waves
for wave in workflow_plan.get_execution_waves():
    print(f"Executing wave with {len(wave)} parallel tasks")
```

### Workflow from Template
```python
from omni.orchestration import WorkflowEngine

engine = WorkflowEngine()

# Load a predefined workflow template
template = engine.load_template("examples/workflow_templates/code_review_workflow.yaml")

# Execute with custom parameters
result = engine.execute(template, {
    "filename": "src/auth.py",
    "reviewer": "senior-coder",
    "strictness": "high"
})

print(f"Workflow completed: {result.success}")
```

### Workflow Template Authoring
Create reusable workflow templates in YAML:

```yaml
# examples/workflow_templates/feature_implementation.yaml
name: "Feature Implementation Workflow"
description: "Standard workflow for implementing new features"
version: "1.0.0"

variables:
  feature_name:
    description: "Name of the feature to implement"
    required: true
    type: "string"
  add_tests:
    description: "Whether to include tests"
    default: true
    type: "boolean"

steps:
  - name: "requirements_analysis"
    task_type: "analysis"
    description: "Analyze requirements for {feature_name}"
    agent: "thinker"

  - name: "implementation"
    task_type: "code_generation"
    description: "Implement {feature_name}"
    depends_on: ["requirements_analysis"]
    agent: "coder"

  - name: "testing"
    task_type: "testing"
    description: "Test {feature_name}"
    depends_on: ["implementation"]
    condition: "{add_tests}"
    agent: "intern"

  - name: "code_review"
    task_type: "code_review"
    description: "Review implementation of {feature_name}"
    depends_on: ["implementation", "testing"]
    agent: "reader"
```

## Supported Models

- **OpenAI**: GPT-4, GPT-4.1, GPT-3.5
- **Anthropic**: Claude 3.5 Sonnet, Claude 3 Haiku
- **Google**: Gemini 1.5 Pro, Gemini Flash
- **DeepSeek**: DeepSeek Chat, DeepSeek Coder
- **Local**: Ollama, LM Studio, vLLM
- **100+ more** via LiteLLM

## Project Status

**Phase 0: Foundation** (Weeks 1-4) - ✅ **Complete**
- [x] Project scaffold + CI/CD
- [x] ModelProvider interface + LiteLLM backend
- [x] EditLoop service (core cycle)
- [x] Git integration
- [x] Basic CLI

**Phase 1: Core Engine** (Weeks 5-12) - ✅ **Complete**
- [x] Model Router
- [x] Additional edit formats
- [x] Verification pipeline
- [x] Configuration system
- [x] Observability dashboard

**Phase 2: Orchestration** (Weeks 13-24) - ✅ **Complete**
- [x] Multi-agent coordination
- [x] Task decomposition
- [x] Parallel execution
- [x] Workflow templates

**Phase 3: Advanced Features** (Weeks 25-36) - **Planning**
- [ ] Advanced optimization algorithms
- [ ] Self-improving routing
- [ ] Cross-repository coordination
- [ ] Enterprise features

## Development

```bash
# Clone and install in development mode
git clone https://github.com/manoslinh/omni-llm
cd omni-llm
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .

# Run type checker
mypy src/omni
```

## License

MIT - See [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](docs/contributing.md) for guidelines.

---

*Built with ❤️ by developers who hate vendor lock-in.*
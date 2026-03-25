# Omni-LLM

**The orchestration OS for AI-assisted development**

> Stop choosing between models. Use the best one for each task. Save 40-60%.

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

## Supported Models

- **OpenAI**: GPT-4, GPT-4.1, GPT-3.5
- **Anthropic**: Claude 3.5 Sonnet, Claude 3 Haiku
- **Google**: Gemini 1.5 Pro, Gemini Flash
- **DeepSeek**: DeepSeek Chat, DeepSeek Coder
- **Local**: Ollama, LM Studio, vLLM
- **100+ more** via LiteLLM

## Project Status

**Phase 0: Foundation** (Weeks 1-4) - In Progress
- [ ] Project scaffold + CI/CD
- [ ] ModelProvider interface + LiteLLM backend
- [ ] EditLoop service (core cycle)
- [ ] Git integration
- [ ] Basic CLI

**Phase 1: Core Engine** (Weeks 5-12)
- [ ] Model Router
- [ ] Additional edit formats
- [ ] Verification pipeline
- [ ] Configuration system
- [ ] Observability dashboard

**Phase 2: Orchestration** (Weeks 13-24)
- [ ] Multi-agent coordination
- [ ] Task decomposition
- [ ] Parallel execution
- [ ] Workflow templates

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
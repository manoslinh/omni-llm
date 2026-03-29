# Omni-LLM Project Context
*Last updated: 2026-03-29 20:25 UTC*

## Elevator Pitch

**Omni-LLM is the orchestration OS for AI-assisted development.** It's a CLI tool that runs multiple LLMs in parallel, automatically routing each subtask to the most cost-effective model that meets quality requirements. Think "Aider meets Kubernetes" — you describe what you want, Omni-LLM decomposes the work, fans it out to specialized agents on isolated git worktrees, verifies the results, and integrates them back. **Save 40-60% on API costs while getting better results than any single model.**

---

## Current Phase: Phase 2 COMPLETE ✅ → Phase 2.5 POLISH (NEXT)

The original Phase 2 plan (22 tickets across 5 sub-phases) has been executed with significant scope evolution. **16 of 22 original tickets are complete**, and 6 additional components not in the original plan were built to address real implementation needs. The remaining 6 original tickets (P2-18 Conflict Resolver, P2-19 Result Integrator, P2-20 Workflow Templates, P2-21 E2E Tests, P2-22 Docs) have been **deferred to Phase 3** in favor of the more urgent UX polish work in Phase 2.5.

### Phase 2 Completion Summary

| Sub-phase | Original Scope | Status | Notes |
|-----------|---------------|--------|-------|
| **2.1** Model Router | P2-01 to P2-06 | ✅ COMPLETE | All 6 tickets merged |
| **2.2** Task Decomposition | P2-07 to P2-10 | ✅ COMPLETE | All 4 tickets merged |
| **2.3** Multi-Agent Coordination | P2-11 to P2-15 | ✅ REDEFINED | Scope evolved → coordination engine + execution + scheduling (all merged) |
| **2.4** Parallel Execution | P2-16 to P2-19 | ✅ REDEFINED | Replaced by execution engine + observability + scheduling; P2-18/P2-19 deferred to Phase 3 |
| **2.5** Workflow Templates | P2-20 to P2-22 | ⏸️ DEFERRED | Deferred to Phase 3; new Phase 2.5 = onboarding polish |

---

## All Merged Tickets (16 total)

### Phase 2.1: Model Router (6/6) ✅

| # | Ticket | PR | Status |
|---|--------|-----|--------|
| P2-01 | RoutingStrategy ABC + data models | #30 | ✅ Merged |
| P2-02 | CostOptimizedStrategy implementation | #31 | ✅ Merged |
| P2-03 | Model Router Service facade | #33 | ✅ Merged |
| P2-04 | Provider Registry & Capability Discovery | #35 | ✅ Merged |
| P2-05 | Health Monitoring & Circuit Breaker | #36 | ✅ Merged |
| P2-06 | Budget Enforcement system | #34 | ✅ Merged |

### Phase 2.2: Task Decomposition (4/4) ✅

| # | Ticket | PR | Status |
|---|--------|-----|--------|
| P2-07 | Task decomposition data models | #32 | ✅ Merged |
| P2-08 | Task Decomposition Engine | #39 | ✅ Merged |
| P2-09 | Complexity Analyzer | #37 | ✅ Merged |
| P2-10 | Task Graph Visualizer | #38 | ✅ Merged |

### Phase 2.3-2.4: Execution & Observability (6 PRs, redefined scope) ✅

| PR | Component | Status |
|----|-----------|--------|
| #40 | P2-11 Parallel Execution Engine (architecture) | ✅ Merged |
| #41 | P2-11 Parallel Execution Engine (implementation) | ✅ Merged |
| #42 | P2-12 LLM Integration & Tiered Routing | ✅ Merged |
| #43 | P2-13 Observability & Live Visualization | ✅ Merged |
| #44 | P2-14 Coordination Engine | ✅ Merged |
| #45 | P2-15 Scheduling & Resource Management | ✅ Merged |
| #46 | P2-16 Advanced Scheduling Policies | ✅ Merged |

---

## Scope Evolution Analysis

The project organically evolved beyond the original 22-ticket plan. Here's what changed and why:

### What Was Redefined

| Original Ticket | What It Became | Reason |
|----------------|---------------|--------|
| **P2-11** Message Bus | Parallel Execution Engine (architecture + impl) | Direct message bus less useful than full execution engine with async orchestration |
| **P2-12** Agent Registry | LLM Integration & Tiered Routing | Agent registry folded into coordination engine; focus shifted to LLM task execution |
| **P2-13** Base Agent Class | Observability & Live Visualization | Agent abstraction absorbed by coordination engine; observability became critical need |
| **P2-14** Supervisor Agent | Coordination Engine | Implemented as full coordination engine with agent matching, workflow orchestration |
| **P2-15** Worker Agent | Scheduling & Resource Management | Worker concept merged into execution engine; scheduling became the gap |
| **P2-16** Git Worktree Manager | Advanced Scheduling Policies | Git worktree concept deferred; scheduling policies more immediately useful |
| **P2-17** Parallel Execution Engine | *(absorbed into P2-11)* | Built directly as part of execution engine |
| **P2-18** Conflict Resolver | **NOT BUILT** | Deferred — requires real-world merge conflict patterns |
| **P2-19** Result Integrator | **NOT BUILT** | Deferred — depends on conflict resolver |

### Components Built Beyond Original Plan

These weren't in the 22-ticket plan but were built because they were needed:

- **Scheduling Policies** (`src/omni/scheduling/policies.py`) — FIFO, Priority, Deadline, Cost-Aware, Fair, Balanced policies
- **Predictive Scheduling** (`src/omni/scheduling/predictive.py`) — WorkloadTracker for pattern-based scheduling
- **Resource Pool** (`src/omni/scheduling/resource_pool.py`) — Global resource management (API quotas, concurrency limits)
- **Schedule Adjuster** (`src/omni/execution/adjuster.py`) — Adaptive concurrency control
- **Execution DB** (`src/omni/execution/db.py`) — SQLite persistence for execution state
- **Mermaid Visualization** (`src/omni/observability/mermaid.py`) — Live diagram generation

---

## Detailed Implementation Status

### ✅ Fully Implemented

| Module | Files | Lines | Description |
|--------|-------|-------|-------------|
| `src/omni/router/` | 8 files | ~1,500 | Complete Model Router: strategy ABC, cost-optimized routing, provider registry, health monitoring, budget enforcement |
| `src/omni/decomposition/` | 6 files | ~2,370 | Task decomposition engine, complexity analyzer, visualizer, multiple decomposition strategies |
| `src/omni/execution/` | 8 files | ~2,820 | Parallel execution engine, scheduler, executor, adjuster, SQLite persistence, config |
| `src/omni/observability/` | 7 files | ~2,620 | Live ASCII dashboard, Mermaid diagrams, execution replay, metrics, tuning, CLI |
| `src/omni/coordination/` | 4 files | ~800+ | Agent registry, capability matching, workflow orchestration, coordination engine |
| `src/omni/scheduling/` | 4 files | ~1,040 | 6 scheduling policies, predictive workload tracking, resource pool management |
| `src/omni/providers/` | 6 files | ~600+ | LiteLLM adapter, cost tracker, config, mock provider, base provider |
| `src/omni/core/` | 7 files | ~800+ | Edit loop, edit applier, verifier pipeline (lint + test), edit block parser |
| `src/omni/git/` | 2 files | ~300 | Git repository integration with AI attribution |
| `src/omni/cli/` | 2 files | ~200 | CLI entry point with execute subcommands |
| `src/omni/models/` | 3 files | ~200 | Provider interface, LiteLLM provider, mock provider |

**Total:** 63 source files, ~16,700 lines of Python

### ✅ Tests (37 test files)

| Test File | Coverage Area |
|-----------|--------------|
| `test_router.py` | Model router integration |
| `test_routing_strategy.py` | Strategy ABC + data models |
| `test_cost_optimized.py` | Cost-optimized routing |
| `test_health.py` | Health monitoring & circuit breaker |
| `test_budget.py` | Budget enforcement |
| `test_provider_registry.py` | Provider registry |
| `test_decomposition.py` | Task decomposition engine |
| `test_complexity_analyzer.py` | Complexity analysis |
| `test_decomposition_visualizer.py` | Task graph visualization |
| `test_execution_engine.py` | Parallel execution engine |
| `test_execution_scheduler.py` | Task scheduling |
| `test_execution_executor.py` | LLM task executor |
| `test_execution_db.py` | SQLite persistence |
| `test_execution_config.py` | Execution configuration |
| `test_execution_models.py` | Execution data models |
| `test_observability.py` | Dashboard & metrics |
| `test_scheduling_policies.py` | Scheduling policies |
| `test_scheduling_integration.py` | Scheduling integration |
| `test_predictive_module.py` | Predictive workload tracking |
| `test_resource_pool.py` | Resource pool |
| `test_resource_pool_integration.py` | Resource pool integration |
| `test_schedule_adjuster.py` | Adaptive scheduling |
| `test_schedule_adjuster_integration.py` | Adjuster integration |
| `test_editblock.py` | Edit block parser |
| `test_edit_loop.py` | Edit loop service |
| `test_verifiers.py` | Verification pipeline |
| `test_lint_verifier.py` | Lint verifier |
| `test_providers.py` | Provider integration |
| `test_provider.py` | Provider base |
| `test_litellm_adapter.py` | LiteLLM adapter |
| `test_cost_tracker.py` | Cost tracking |
| `test_provider_config.py` | Provider configuration |
| `test_task_models.py` | Task data models |
| `test_timeout_*.py` (3) | Timeout handling |
| `test_router_provider_registry_integration.py` | Router + registry integration |

### ❌ Not Yet Built

| Component | Original Ticket | Description | Priority |
|-----------|----------------|-------------|----------|
| **Conflict Resolver** | P2-18 | Smart merge of parallel agent work on same files | High |
| **Result Integrator** | P2-19 | Aggregate and validate results from parallel execution | High |
| **Workflow Template Engine** | P2-20 | YAML-defined multi-step workflow definitions | Medium |
| **E2E Integration Tests** | P2-21 | Full pipeline tests (decompose → execute → integrate) | Medium |
| **Documentation & Examples** | P2-22 | User-facing docs, API reference, workflow examples | Medium |
| **Git Worktree Manager** | P2-16 (original) | Automated worktree lifecycle for parallel agent isolation | Medium |

### ⚠️ Partially Implemented

| Component | Status | Notes |
|-----------|--------|-------|
| `src/omni/git/repository.py` | Basic | Core git operations exist but no worktree lifecycle management |
| `docs/` | Architecture docs only | 8 architecture/design docs, no user-facing documentation |
| `examples/` | Demo scripts | 14 demo scripts showing individual features, no end-to-end workflow |

---

## Project Structure

```
src/omni/
├── __init__.py
├── cli/                    # CLI entry point
│   ├── __init__.py
│   └── main.py             # `omni` command with execute subcommands
├── coordination/           # Multi-agent coordination (P2-14)
│   ├── __init__.py         # Agent registry, capability matching
│   ├── engine.py           # CoordinationEngine
│   ├── matcher.py          # TaskMatcher, AgentAssignment
│   └── workflow.py         # WorkflowOrchestrator
├── core/                   # Edit loop & verification pipeline
│   ├── __init__.py
│   ├── edit_applier.py
│   ├── edit_loop.py
│   ├── models.py
│   ├── verifier.py
│   └── verifiers/          # Lint + test verifiers
├── decomposition/          # Task decomposition (P2-07 to P2-10)
│   ├── __init__.py
│   ├── complexity_analyzer.py
│   ├── engine.py           # TaskDecompositionEngine
│   ├── models.py           # Task, TaskGraph, TaskType
│   ├── strategies.py       # Decomposition strategies
│   └── visualizer.py       # TaskGraphVisualizer (Mermaid)
├── edits/                  # Edit block parser
│   ├── __init__.py
│   └── editblock.py
├── execution/              # Parallel execution engine (P2-11, P2-12)
│   ├── __init__.py
│   ├── adjuster.py         # ScheduleAdjuster
│   ├── config.py           # ExecutionConfig, ExecutionCallbacks
│   ├── db.py               # ExecutionDB (SQLite persistence)
│   ├── engine.py           # ParallelExecutionEngine
│   ├── executor.py         # TaskExecutor, LLMTaskExecutor
│   ├── models.py           # ExecutionResult, ExecutionMetrics
│   └── scheduler.py        # Scheduler
├── git/                    # Git integration
│   ├── __init__.py
│   └── repository.py       # GitRepository
├── models/                 # Provider interface
│   ├── __init__.py
│   ├── litellm_provider.py
│   ├── mock_provider.py
│   └── provider.py
├── observability/          # Visualization & monitoring (P2-13)
│   ├── __init__.py
│   ├── cli.py              # `omni execute` commands
│   ├── dashboard.py        # Live ASCII dashboard
│   ├── mermaid.py          # Mermaid snapshot generation
│   ├── mermaid_simple.py   # HTML animation generator
│   ├── metrics.py          # Performance metrics & bottleneck detection
│   ├── replay.py           # Execution replay
│   └── tuning.py           # Adaptive concurrency control
├── providers/              # LLM provider layer
│   ├── __init__.py
│   ├── base.py
│   ├── config.py
│   ├── cost_tracker.py
│   ├── litellm_adapter.py
│   └── mock_provider.py
├── router/                 # Model routing (P2-01 to P2-06)
│   ├── __init__.py
│   ├── budget.py           # Budget enforcement
│   ├── cost_optimized.py   # CostOptimizedStrategy
│   ├── errors.py
│   ├── health.py           # Health monitoring & circuit breaker
│   ├── models.py           # Routing data models
│   ├── provider_registry.py # Provider Registry & Capability Discovery
│   ├── router.py           # ModelRouter facade
│   └── strategy.py         # RoutingStrategy ABC
├── scheduling/             # Scheduling & resources (P2-15, P2-16)
│   ├── __init__.py
│   ├── policies.py         # 6 scheduling policies
│   ├── predictive.py       # WorkloadTracker
│   └── resource_pool.py    # ResourcePool
└── task/                   # Task models
    ├── __init__.py
    └── models.py

configs/
├── budget.yaml             # Budget limits configuration
├── models.yaml             # Model capabilities & routing config
├── providers.yaml          # Provider API keys & cost rates
└── verifiers.yaml          # Verifier pipeline config

tests/                      # 37 test files
docs/                       # 8 architecture/design docs
examples/                   # 14 demo scripts
```

---

## Recent Activity

| Date (UTC) | PR | Description |
|------------|-----|-------------|
| 2026-03-28 | #46 | P2-16: Advanced Scheduling Policies |
| 2026-03-28 | #45 | P2-15: Scheduling & Resource Management |
| 2026-03-28 | #44 | P2-14: Coordination Engine |
| 2026-03-28 | #43 | P2-13: Observability & Live Visualization |
| 2026-03-28 | #42 | P2-12: LLM Integration & Tiered Routing |
| 2026-03-28 | #41 | P2-11: Parallel Execution Engine (implementation) |
| 2026-03-27 | #40 | P2-11: Parallel Execution Engine (architecture) |
| 2026-03-27 | #39 | P2-08: Task Decomposition Engine |
| 2026-03-27 | #38 | P2-10: Task Graph Visualizer |
| 2026-03-27 | #37 | P2-09: Complexity Analyzer |
| 2026-03-27 | #36 | P2-05: Health Monitoring & Circuit Breaker |
| 2026-03-27 | #35 | P2-04: Provider Registry & Capability Discovery |
| 2026-03-26 | #34 | P2-06: Budget Enforcement |
| 2026-03-26 | #33 | P2-03: Model Router Service |
| 2026-03-26 | #32 | P2-07: Task decomposition data models |
| 2026-03-26 | #31 | P2-02: CostOptimizedStrategy |
| 2026-03-26 | #30 | P2-01: RoutingStrategy ABC |

---

## Strategic Analysis: Phase 2.5 vs Phase 3

### The Core Problem

Omni-LLM has a brilliant engine under the hood — multi-agent orchestration, cost-optimized routing, scheduling policies, 1029 tests — but the first-run experience is:

```
$ pip install omni-llm
$ omni orchestrate "build a REST API"
❌ Orchestration features not available
Install with: pip install -e '.[orchestration]'
$ omni config
Configuration management coming soon!
For now, set environment variables:
  - OPENAI_API_KEY
  - ANTHROPIC_API_KEY
```

**This is a death sentence for adoption.** Users try it once, hit a wall, leave forever.

### Decision: Phase 2.5 BEFORE Phase 3 — MANDATORY

| Question | Answer |
|----------|--------|
| Implement Phase 2.5 before Phase 3? | **YES — non-negotiable** |
| Release v1.0 now? | **NO — wait for Phase 2.5** |
| Minimum viable polish? | **Setup wizard + model add + demo (3 commands)** |
| Balance tech vs UX? | **Phase 2.5 is the bridge — 2 weeks max** |

**Rationale:**
1. **First impressions are irreversible.** A bad `pip install` experience poisons the well. Beta users who leave won't come back for v1.1.
2. **The differentiator is invisible without models.** Multi-agent orchestration means nothing if users can't connect even one model. The gap between "engine exists" and "user experiences magic" is exactly Phase 2.5.
3. **Phase 3 features are multipliers, not prerequisites.** Daemon mode, web dashboard, plugins — these multiply the value of an already-working experience. Without that base experience, they multiply zero.
4. **Two weeks is nothing compared to the cost of a bad launch.** Phase 2 took 72 hours. Phase 2.5 is smaller scope, focused on UX shell around existing engine.

### Competitive Context

| Feature | OpenFlow | Omni-LLM (now) | Omni-LLM (post-2.5) |
|---------|----------|-----------------|----------------------|
| Setup | Slick wizard | Manual env vars | Interactive wizard |
| Model config | One-click | YAML editing | Multiple-choice add |
| First run | Immediate | Blocked | Guided demo |
| Differentiator | Simplicity | Multi-agent | Multi-agent + easy setup |

**Our unique value:** No other CLI tool orchestrates multiple LLMs in parallel with cost optimization. But that value is locked behind a technical setup wall. Phase 2.5 unlocks it.

---

## Phase 2.5: ONBOARDING POLISH (2 weeks)

**Goal:** Transform "engine exists" → "user experiences multi-agent magic in 2 minutes"

### Ticket Breakdown

#### P2.5-01: Interactive Setup Wizard (`omni setup`)
**Priority:** CRITICAL | **Estimate:** 3 days | **Role:** Coder

Interactive first-run experience:
- Detect installed providers (check for API keys)
- Walk user through adding first provider:
  ```
  $ omni setup
  🚀 Welcome to Omni-LLM! Let's get you set up.

  Which AI providers do you want to use?
  [1] OpenAI (GPT-4, GPT-3.5)
  [2] Anthropic (Claude)
  [3] Google (Gemini)
  [4] DeepSeek
  [5] Ollama (local, free)
  [6] Add custom provider

  Enter numbers (comma-separated): 1,2

  → OpenAI API key: [hidden input]
  → Anthropic API key: [hidden input]

  ✅ Configured 2 providers with 12 models!
  💡 Try: omni demo  (see multi-agent orchestration in action)
  ```
- Save to `~/.omni/config.yaml` (not environment variables)
- Validate keys with a lightweight test call
- Skip if already configured (idempotent)
- **This is the single highest-impact change**

#### P2.5-02: Model Management (`omni models add/status`)
**Priority:** CRITICAL | **Estimate:** 2 days | **Role:** Coder

Replace YAML editing with CLI commands:

- `omni models add` — Interactive model selection:
  ```
  $ omni models add
  Available models from your providers:

  OPENAI:
    [1] gpt-4o          — Best reasoning, $2.50/1M in
    [2] gpt-4o-mini     — Fast + cheap, $0.15/1M in
    [3] gpt-3.5-turbo   — Budget, $0.50/1M in

  ANTHROPIC:
    [4] claude-sonnet-4-20250514 — Balanced, $3.00/1M in
    [5] claude-haiku-20250114   — Fast, $0.25/1M in

  Select models to enable: 1,2,4,5
  ✅ Added 4 models to your roster
  ```
- `omni models status` — Visual dashboard:
  ```
  $ omni models status
  ┌─────────────────────┬──────────┬───────────┬──────────┬─────────┐
  │ Model               │ Provider │ Cost/1M   │ Health   │ Enabled │
  ├─────────────────────┼──────────┼───────────┼──────────┼─────────┤
  │ gpt-4o              │ openai   │ $2.50 in  │ ✅ Ready │ Yes     │
  │ gpt-4o-mini         │ openai   │ $0.15 in  │ ✅ Ready │ Yes     │
  │ claude-sonnet-4     │ anthropic│ $3.00 in  │ ✅ Ready │ Yes     │
  │ claude-haiku        │ anthropic│ $0.25 in  │ ✅ Ready │ Yes     │
  └─────────────────────┴──────────┴───────────┴──────────┴─────────┘
  4 models active · Est. monthly budget: $50.00
  ```
- `omni models remove <name>` — Remove from roster
- `omni models test <name>` — Quick connectivity/capability test

#### P2.5-03: Model Capability Auto-Detection
**Priority:** HIGH | **Estimate:** 2 days | **Role:** Coder

- Query LiteLLM model database for capabilities (context window, vision, function calling, cost)
- Auto-populate `strengths` and `weaknesses` based on model family
- Don't force users to manually specify what's publicly known
- Cache results locally; refresh weekly
- Override mechanism for power users (`omni models set <model> strength coding`)

#### P2.5-04: Guided First-Run Demo (`omni demo`)
**Priority:** HIGH | **Estimate:** 2 days | **Role:** Coder

Interactive showcase of multi-agent orchestration:
```
$ omni demo
🎭 Omni-LLM Multi-Agent Demo
============================

This demo shows how Omni-LLM orchestrates multiple AI models.

📝 Task: "Review this Python function and suggest improvements"

🔄 Decomposing task...
   → Found 3 subtasks:
     1. Code style analysis (→ gpt-4o-mini, cheap)
     2. Security review (→ claude-sonnet-4, thorough)
     3. Performance analysis (→ gpt-4o, deep)

⚡ Executing in parallel...
   [████████████████████] 3/3 complete

📊 Results:
   • gpt-4o-mini: Found 2 style issues ($0.0003)
   • claude-sonnet-4: Found 1 security concern ($0.008)
   • gpt-4o: Found 3 optimization opportunities ($0.012)

💰 Total cost: $0.0203 (vs $0.045 with single model — saved 55%)

✅ Demo complete! Run `omni orchestrate "your task"` to start.
```

Uses mock or real providers depending on configuration. Shows the **value proposition visually**: decomposition, parallel execution, cost savings.

#### P2.5-05: Sensible Defaults & Zero-Config Start
**Priority:** HIGH | **Estimate:** 1 day | **Role:** Coder

- `omni orchestrate "task"` should work with ZERO prior config if at least one API key is set
- Auto-detect available providers from environment variables (backward compat)
- Default routing strategy: cost-optimized (already implemented)
- Default to mock provider if no keys found, with clear message:
  ```
  $ omni orchestrate "hello world"
  ⚠️  No API keys found. Running in demo mode with mock provider.
  💡 Run `omni setup` to connect real AI models.
  ```
- Remove the "Orchestration features not installed" wall entirely — the features are THERE, just need models

#### P2.5-06: Quick-Start Documentation
**Priority:** MEDIUM | **Estimate:** 1 day | **Role:** Intern

- Rewrite README.md with 60-second quickstart:
  ```
  pip install omni-llm
  omni setup
  omni demo
  omni orchestrate "build a REST API with tests"
  ```
- Getting-started guide (docs/quickstart.md)
- Troubleshooting common issues
- Architecture overview for contributors

### Phase 2.5 Summary

| Ticket | Description | Days | Priority |
|--------|-------------|------|----------|
| P2.5-01 | Setup wizard (`omni setup`) | 3 | CRITICAL |
| P2.5-02 | Model management CLI | 2 | CRITICAL |
| P2.5-03 | Capability auto-detection | 2 | HIGH |
| P2.5-04 | Guided demo (`omni demo`) | 2 | HIGH |
| P2.5-05 | Zero-config defaults | 1 | HIGH |
| P2.5-06 | Quick-start docs | 1 | MEDIUM |
| **Total** | | **~11 days** | |

**Target:** 2 weeks (with parallel agent execution of independent tickets)

---

## User Journey: Install → Multi-Agent Magic (5 steps, <3 minutes)

```
Step 1: INSTALL
  $ pip install omni-llm
  (one command, works everywhere)

Step 2: SETUP (omni setup — 60 seconds)
  → Interactive wizard asks which providers
  → User enters API keys (hidden input)
  → Keys validated, models auto-detected
  → Config saved to ~/.omni/config.yaml

Step 3: VERIFY (omni models status — 5 seconds)
  → Visual dashboard shows available models
  → Health checks confirm connectivity
  → User sees: "4 models ready"

Step 4: DEMO (omni demo — 30 seconds)
  → Shows multi-agent orchestration live
  → Decomposition → parallel execution → cost savings
  → User thinks: "Holy shit, this actually works"

Step 5: USE (omni orchestrate "..." — immediate)
  → Real task, real models, real results
  → User is hooked
```

**Key insight:** Step 4 is the "aha moment." Without it, users don't understand WHY they need multiple models. The demo converts curiosity into conviction.

---

## Phase 2.5 Implementation Priority (Recommended Order)

### Sprint 1 (Week 1): "Make it work"
1. **P2.5-05** Zero-config defaults (1 day) — Remove the wall FIRST
2. **P2.5-01** Setup wizard (3 days) — The core UX
3. **P2.5-02** Model management CLI (2 days) — Ongoing model management

### Sprint 2 (Week 2): "Make it shine"
4. **P2.5-03** Capability auto-detection (2 days) — Smart defaults
5. **P2.5-04** Guided demo (2 days) — The "aha moment"
6. **P2.5-06** Quick-start docs (1 day) — Capture the converted

**Rationale for this order:**
- P2.5-05 first: Immediately removes the "features not available" error. Even an imperfect experience beats a wall.
- P2.5-01 + P2.5-02 in week 1: These are the core UX. Can't ship without them.
- P2.5-03 + P2.5-04 in week 2: Polish on top of working core.
- P2.5-06 last: Docs describe what exists; write them after the features stabilize.

---

## Post Phase 2.5: Roadmap

### Phase 3: Advanced Orchestration (8-12 weeks)
Deferred from earlier plan — these multiply a working experience:

1. **Conflict Resolver** — Smart merge of parallel agent work on same files
2. **Result Integrator** — Aggregate and validate results from parallel execution
3. **Git Worktree Manager** — Automated worktree lifecycle for agent isolation
4. **Workflow Template Engine** — YAML-defined multi-step workflow definitions
5. **E2E Integration Tests** — Full pipeline tests (decompose → execute → integrate)

### Phase 4: Platform (12+ weeks)
- Persistent daemon mode
- Web dashboard
- Plugin system (third-party strategies, verifiers, providers)
- Multi-repo support

### v1.0 Release Criteria
- [x] Multi-agent orchestration engine
- [x] Cost-optimized model routing
- [x] Parallel execution with scheduling
- [ ] Interactive setup wizard ← Phase 2.5
- [ ] Model management CLI ← Phase 2.5
- [ ] Guided demo ← Phase 2.5
- [ ] Conflict resolution ← Phase 3
- [ ] Result integration ← Phase 3
- [ ] User documentation ← Phase 2.5 + 3

**Recommendation:** v1.0 release AFTER Phase 2.5 + Phase 3 (Conflict Resolver + Result Integrator). The engine is ready; the UX polish and the last two missing pieces make it release-worthy.

---

## Decision Framework for Emmanouil

### The One Question That Matters

> "Can a user go from `pip install` to seeing multi-agent magic in under 3 minutes?"

If no → Phase 2.5 is required. No exceptions.

### Decision Matrix

| Scenario | Ship v1.0 now? | Do Phase 2.5? | Do Phase 3 first? |
|----------|----------------|----------------|-------------------|
| Want early adopters / beta feedback | Maybe (alpha only) | YES | No |
| Want to compete with OpenFlow | No | YES (mandatory) | After 2.5 |
| Want a polished first release | No | YES | After 2.5 |
| Want to demo to investors/stakeholders | No | YES (the demo command!) | After 2.5 |
| Internal use only / tool for yourself | Yes (you know the setup) | Nice to have | Your call |

### Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Phase 2.5 takes longer than 2 weeks | Medium | Hard scope: 6 tickets, no feature creep |
| Users still don't understand multi-agent | High | The `omni demo` command shows it visually |
| Competitor launches similar feature | Medium | Our engine is 16,700 lines deep — hard to replicate |
| Phase 2.5 blocks Phase 3 work | Low | Phase 3 tickets can be designed in parallel |

### What NOT To Do

- ❌ Don't build a web UI for Phase 2.5 (that's Phase 4)
- ❌ Don't add new orchestration features during 2.5 (polish only)
- ❌ Don't perfect the wizard — get it working, iterate later
- ❌ Don't skip the demo — it's the conversion tool
- ❌ Don't release v1.0 without setup wizard — first impressions stick

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Phase 2 duration | ~72 hours (2026-03-26 to 2026-03-29) |
| Phase 2 tickets completed | 16/22 original + 6 additional = 22 total |
| PRs merged | 17 (#30 through #46) |
| Source files | 63 |
| Lines of code | ~16,700 |
| Test files | 37 |
| Tests passing | 1029/1029 |
| Example scripts | 14 |
| Architecture docs | 8 |

---

## CI/CD & Quality Gate

```bash
# Pre-PR checks (all must pass):
ruff check .                              # Linting
mypy src/omni --ignore-missing-imports    # Type checking
pytest tests/ -v                          # Tests
```

---

## Protocol Being Followed

1. **Isolated worktrees** for each agent task under `projects/omni-llm-worktrees/branches/`
2. **Branch naming:** `branches/YYYYMMDD_role-name_task`
3. **Review process:** Implementer → Reviewer (same/higher tier) → Fixes if needed → PR
4. **Merge rules:** Only Emmanouil merges, CI must be green, no auto-merge
5. **Agent roles:** Thinker (architecture), Coder (implementation), Intern (simple tasks)

---

## Timezone Context

- **UTC:** Current time reference
- **Athens (Emmanouil):** UTC+2
- **Quiet hours:** 23:00-08:00 Athens time (avoid PRs/notifications)

---

*This file tracks transient project context for Omni-LLM development.*
*For long-term lessons, see workspace/MEMORY.md.*
*For daily logs, see workspace/memory/YYYY-MM-DD.md.*

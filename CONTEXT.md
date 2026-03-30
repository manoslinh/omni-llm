# Omni-LLM Project Context
*Last updated: 2026-03-30 22:00 UTC*

## Elevator Pitch

**Omni-LLM is the orchestration OS for AI-assisted development.** CLI tool that runs multiple LLMs in parallel, routing each subtask to the most cost-effective model. Decomposes work, fans out to specialized agents on isolated git worktrees, verifies results, integrates them back. **Save 40-60% on API costs while getting better results than any single model.**

---

## Current Phase: Phase 2.5 POLISH (IN PROGRESS)

Phase 2 complete (16/22 original tickets + 6 additional). Phase 2.5 focuses on onboarding UX. P2.5-01 (setup wizard), P2.5-02 (model management), P2.5-04 (demo command) are implemented. Remaining: P2.5-03 (capability auto-detection), P2.5-05 (zero-config defaults), P2.5-06 (quick-start docs).

---

## Codebase Metrics (as of 2026-03-30)

| Metric | Value |
|--------|-------|
| Python source files | ~80 under src/omni/ |
| Total LOC (source) | ~27,192 |
| Modules | 16 packages |
| Test files | 61 |
| Test functions | 1,074 |
| Async tests | 215 |
| Example scripts | 26+ |
| Architecture docs | 16 in docs/ |
| PRs merged (Phase 2) | 17 (#30-#46) |
| Latest PR | #61 (omni models add/status) |

---

## Architecture Overview

**Pattern**: Modular monolith with layered architecture, facade pattern, strategy pattern.

### Module Map

| Module | LOC | Responsibility |
|--------|-----|----------------|
| `workflow/` | 4,131 | State machines, templates, orchestrators, node definitions |
| `router/` | 3,723 | Cost-aware model selection, strategies, health, budget, provider registry |
| `observability/` | 2,626 | Metrics, dashboards, Mermaid diagrams, tuning |
| `decomposition/` | 2,477 | Task decomposition, complexity analysis, strategies |
| `execution/` | 2,456 | Parallel task engine, scheduling, DB persistence |
| `cli/` | 2,182 | CLI entry points, demo, setup wizard |
| `orchestration/` | 1,654 | Result integration, conflict resolution, workflow templates |
| `providers/` | 1,483 | Provider base classes, LiteLLM adapter, cost tracker |
| `core/` | 1,484 | Edit loop, verification pipeline, models |
| `git/` | 1,144 | Repository management, worktree isolation |
| `coordination/` | 1,122 | Agent matching, workflow planning, coordination engine |
| `scheduling/` | 1,085 | Scheduling policies (FIFO, priority, deadline-aware, cost-aware, fair, balanced) |
| `models/` | 792 | Provider protocol definitions |
| `task/` | 484 | Task and TaskGraph data models (pure domain, zero internal deps) |
| `edits/` | 347 | SEARCH/REPLACE block parser |

### Dependency Flow (Acyclic)

```
cli → models, providers, observability, task, coordination, decomposition, orchestration, router
coordination → task, decomposition
decomposition → task
execution → scheduling, git (conditional)
core → core.verifier
```

No circular dependencies. `task/` is the foundational pure domain layer.

### Key Design Patterns

| Pattern | Location |
|---------|----------|
| Facade | `ModelRouter`, `CoordinationEngine`, `ParallelExecutionEngine` |
| Strategy | `RoutingStrategy` ABC with pluggable implementations |
| Circuit Breaker | `CircuitBreaker` in `router/health.py` (CLOSED/OPEN/HALF_OPEN) |
| Pipeline | `VerificationPipeline` chains multiple `Verifier` instances |
| Observer/Protocol | `CoordinationObserver` protocol for event-driven coordination |
| Registry | `ProviderRegistry`, `AgentRegistry` with indexed capability lookups |

---

## Known Architecture Issues (Priority Ordered)

### P0 — Security

- **`eval()` in `orchestration/workflow.py`**: `_evaluate_condition` uses Python `eval()` on condition strings. Documented with security warning but unmitigated. Vulnerability if templates come from untrusted sources.

### P0 — Architecture

- **Duplicate `ModelProvider` ABC**: Two incompatible provider contracts exist:
  - `omni.models.provider.ModelProvider` — used by CLI (`complete()`, `get_capabilities()`, `list_models()`)
  - `omni.providers.base.ModelProvider` — used by router (`chat_completion()`, `stream_chat_completion()`)
  - These must be unified before the interfaces calcify.

### P1 — Code Quality

- **16 files exceed the 500-line project limit**: Worst offenders: `router/health.py` (889), `cli/main.py` (846), `workflow/state_machine.py` (839), `router/router.py` (747), `router/budget.py` (708)
- **Code duplication**: Router capability mapping duplicated verbatim in two methods in `router.py`; `register` and `register_provider` in `provider_registry.py` do the same thing; cost calculation duplicated in `executor.py`
- **Deprecated API**: `asyncio.get_event_loop()` in `edit_applier.py` (deprecated since Python 3.10)
- **Monkey-patching**: `scheduler.py` sets `task_future._started_at` on `asyncio.Task` objects

### P1 — Testing

- **`omni/core/edit_applier.py`** — core module with zero test coverage
- **No coverage measurement in CI** — `pytest-cov` installed but never invoked
- **Release workflow publishes to PyPI without running tests**
- **Single Python version in CI (3.12)** despite claiming 3.11/3.13 support

### P2 — Architecture

- **Three overlapping orchestration modules**: `coordination/`, `orchestration/`, `workflow/` have blurred boundaries and confusing naming overlap (`WorkflowOrchestrator` exists in both `coordination.workflow` and `workflow.orchestrator`)
- **Missing dependency injection**: `CoordinationEngine` creates its own `AgentRegistry`, `TaskMatcher`, `WorkflowOrchestrator` internally
- **Several Phase 2 placeholders remain**: `ConflictResolver._reconstruct_file_content` returns `None`; `ParallelExecutionEngine.resume` raises `NotImplementedError`; `WorkflowEngine.execute` returns mock results

### P2 — Testing

- **`omni/git/repository.py`** — only indirect coverage
- **`omni/observability/replay.py`, `cli.py`, `mermaid_simple.py`** — no tests
- **Duplicate test files**: `test_worktree.py` vs `test_worktree_fixed.py`; `test_schedule_adjuster.py` vs `scheduling/test_adjuster.py`
- **No root `conftest.py`** for shared fixtures
- **Import path inconsistency**: Mixed `from omni.*` and `from src.omni.*` across tests
- **`pytest.ini` overrides `pyproject.toml`**: `testpaths`, `python_classes`, `python_functions` from pyproject.toml are effectively ignored

### P3 — Minor

- **Mixed sync/async**: `ResultIntegrator._run_verification_sync` wraps async with `asyncio.run()`, will fail if already in event loop
- **`_Money` type fragility**: Decimal subclass in `budget.py` overrides `__eq__` to compare with floats
- **Empty `__init__.py` files**: Several packages export nothing, requiring consumers to know internal structure

---

## Documentation Audit (2026-03-30)

### Critical Finding: NOT READY FOR OPEN-SOURCE

A 3-agent documentation audit identified severe issues across 34 documentation files.

### Files to DELETE Before Open-Sourcing (14 root files)

| File | Reason |
|------|--------|
| `CONTEXT.md` | Personal info (owner name, timezone), competitive analysis, strategic decisions, investor mentions |
| `PHASE2_PLAN.md` | Internal planning with agent/model assignments, effort estimates |
| `P2-11-ARCHITECTURE.md` | Internal architecture doc with AI model attribution |
| `P2-11-REVIEW.md` | Internal review artifact with model attribution ("deepseek/deepseek-chat") |
| `REVIEW_REPORT.md` | Exposes security vulnerabilities explicitly; lists what's NOT implemented |
| `REVIEW_REPORT_P2-02.md` | Internal review artifact with model attribution |
| `COMPLETION_SUMMARY.md` | Operational artifact exposing internal infrastructure paths and usernames |
| `DEMO_IMPLEMENTATION_SUMMARY.md` | Redundant with docs/demo_command.md |
| `IMPLEMENTATION_SUMMARY.md` | Redundant with docs/P2-16-IMPLEMENTATION.md |
| `BRANCH_CLEANUP_REPORT.md` | Operational artifact with infrastructure paths |
| `CLEANUP_INSTRUCTIONS.md` | Redundant with above |
| `GITHUB_SETUP_SUMMARY.md` | Contains personal email, obsolete setup artifact |
| `README-worktree.md` | Transient worktree artifact with infrastructure paths |
| `pr_body_p2-16.txt` | PR artifact exposing internal agent workflow |

Also delete: `pr_body.json`, `setup_github_repo.sh`, `create_private_repo.sh`, `scripts/delete_merged_branches.sh`, `test_simple.py` (root)

### Files to RELOCATE

| File | Action |
|------|--------|
| `README-execution.md` | Move to `docs/execution-engine.md` |

### docs/ Files Needing Sanitization (Before Open-Source)

| File | Issue |
|------|-------|
| `docs/P2-14-ARCHITECTURE.md` | Author attribution "Thinker (mimo-v2-pro)" — remove |
| `docs/P2-15-ARCHITECTURE.md` | Same author attribution — remove |
| `docs/P2-16-ARCHITECTURE.md` | Same author attribution — remove |
| `docs/P2-16-ORIGINAL-ARCHITECTURE.md` | Author "Athena (mimo-v2-pro)" — remove; rename to `worktree-manager.md` |
| `docs/LLMTASKEXECUTOR.md` | Exposes internal model IDs (mimo, moonshot) — generalize |
| `docs/SCHEDULING_POLICIES.md` | Contains local paths `cd projects/omni-llm` — fix |
| `docs/SCHEDULE_ADJUSTER.md` | Wrong import path (`omni.scheduling.adjuster` → `omni.execution.adjuster`) |
| `docs/setup_wizard.md` | 3 broken cross-reference links to non-existent docs |
| `docs/models_commands.md` | 1 incomplete link (`[Routing Documentation]` no URL) |
| `docs/PREDICTIVE_MODULE.md` | Uses `from src.omni.` prefix — normalize to `from omni.` |
| `CHANGELOG.md` | Unreleased section lists features that are placeholders (ResultIntegrator) — fix |
| `README.md` | Remove line 10 note about badges appearing after repo creation |

### docs/ Architecture Files: Sprint Naming

All P2-* architecture docs use internal sprint identifiers meaningless to external users. Rename:
- `P2-14-ARCHITECTURE.md` → `coordination-engine.md`
- `P2-15-ARCHITECTURE.md` → `workflow-orchestration.md`
- `P2-16-ARCHITECTURE.md` → `scheduling-architecture.md`
- `P2-16-IMPLEMENTATION.md` → `scheduling-overview.md`

### Missing Documentation

- No `docs/README.md` or `docs/index.md` to guide users
- No "Contributing" guide for open-source contributors
- No standalone budget tracking or conflict resolution examples

### examples/ Issues

- 3 non-examples to remove: `simple_demo.py` (generic asyncio test), `mutable_default_demo.py` (generic Python test), `editloop_mutable_default_demo.py` (internal test)
- 2 broken imports: `multi_agent_parallel.py` imports `omni.coordination.resource_pool` (doesn't exist); `verifier_usage.py` imports `omni.core.verifiers` (missing `s`)
- Import path inconsistency: mix of `from src.omni.` and `from omni.` across examples

### Config/Scripts Security Audit

- **No hardcoded API keys found** — `providers.yaml` correctly uses env var references
- **Personal info exposure**: GitHub username `manoslinh` in `setup_github_repo.sh`; name "Emmanouil" in `pr_body.json`
- **`.gitignore` junk entries**: lines 179-181 contain `=4.0.0`, `=6.0.0`, `None` — broken paste artifacts
- **Missing `.gitignore` entries**: `test_simple.py`, `CLAUDE.md`, `.claude/`, `.claude-flow/` (root dirs are untracked)
- `configs/models.yaml` line 241: verify `ai@omni-llm.dev` email is intentional for public use

---

## Recommended Post-Cleanup Documentation Structure

```
README.md                          (public landing page)
CHANGELOG.md                      (release history — sanitized)
LICENSE
docs/
  README.md                       (NEW — documentation index)
  orchestration.md                 (architecture overview — KEEP)
  workflow-templates.md            (template authoring guide — KEEP)
  health-monitoring.md             (circuit breaker docs — KEEP)
  execution-engine.md              (moved from README-execution.md)
  scheduling-overview.md           (renamed from P2-16-IMPLEMENTATION)
  scheduling-policies.md           (KEEP — fix paths)
  predictive-module.md             (KEEP — fix imports)
  schedule-adjuster.md             (KEEP — fix import path)
  result-integrator.md             (KEEP — update phase language)
  setup-wizard.md                  (KEEP — fix dead links)
  demo-command.md                  (KEEP)
  models-commands.md               (KEEP — fix link)
  llm-task-executor.md             (KEEP — sanitize model names)
  coordination-engine.md           (sanitized from P2-14-ARCHITECTURE)
  workflow-orchestration.md        (sanitized from P2-15-ARCHITECTURE)
  scheduling-architecture.md       (sanitized from P2-16-ARCHITECTURE)
  worktree-manager.md              (sanitized from P2-16-ORIGINAL-ARCHITECTURE)
```

---

## Project Structure

```
src/omni/
├── __init__.py
├── cli/                    # CLI: setup wizard, demo, model management
│   ├── main.py             # `omni` command (846 LOC — needs split)
│   ├── demo.py             # `omni demo` (688 LOC)
│   └── setup.py            # `omni setup` (647 LOC)
├── coordination/           # Multi-agent coordination
│   ├── agents.py           # AgentRegistry, AgentProfile
│   ├── engine.py           # CoordinationEngine facade
│   ├── matcher.py          # TaskMatcher, AgentAssignment
│   └── workflow.py         # WorkflowOrchestrator
├── core/                   # Edit loop & verification
│   ├── edit_applier.py     # File I/O, search-replace (NO TESTS)
│   ├── edit_loop.py        # EditLoop orchestration (445 LOC)
│   ├── models.py
│   ├── verifier.py         # VerificationPipeline
│   └── verifiers/          # Lint + test verifiers
├── decomposition/          # Task decomposition
│   ├── complexity_analyzer.py
│   ├── engine.py           # TaskDecompositionEngine (604 LOC)
│   ├── models.py
│   ├── strategies.py       # Decomposition strategies (691 LOC)
│   └── visualizer.py
├── edits/
│   └── editblock.py        # SEARCH/REPLACE parser
├── execution/              # Parallel execution
│   ├── adjuster.py         # ScheduleAdjuster (569 LOC)
│   ├── config.py
│   ├── db.py               # SQLite persistence
│   ├── engine.py           # ParallelExecutionEngine (474 LOC)
│   ├── executor.py         # TaskExecutor protocol + LLM/Mock impls
│   ├── models.py
│   └── scheduler.py        # Scheduler with deadlock detection
├── git/
│   ├── repository.py       # GitRepository (indirect tests only)
│   └── worktree.py         # Worktree isolation (563 LOC)
├── models/                 # Provider interface (DUPLICATE — see issues)
│   ├── litellm_provider.py
│   ├── mock_provider.py
│   └── provider.py         # ModelProvider ABC #1
├── observability/
│   ├── cli.py              # `omni execute` commands (NO TESTS)
│   ├── dashboard.py        # Live ASCII dashboard
│   ├── mermaid.py          # Mermaid diagram generation
│   ├── mermaid_simple.py   # HTML animation (NO TESTS)
│   ├── metrics.py          # Performance metrics (560 LOC)
│   ├── replay.py           # Execution replay (NO TESTS)
│   └── tuning.py           # Adaptive concurrency
├── orchestration/
│   ├── conflicts.py        # ConflictResolver (471 LOC, placeholder)
│   ├── integrator.py       # ResultIntegrator (484 LOC)
│   ├── workflow.py         # WorkflowEngine (eval() security issue)
│   └── workflow_models.py
├── providers/              # Provider layer
│   ├── base.py             # ModelProvider ABC #2 (DUPLICATE)
│   ├── config.py           # ConfigLoader
│   ├── cost_tracker.py
│   ├── litellm_adapter.py
│   └── mock_provider.py
├── router/
│   ├── budget.py           # BudgetTracker (708 LOC, thread-safe)
│   ├── cost_optimized.py   # CostOptimizedStrategy
│   ├── errors.py           # RouterError hierarchy (NO TESTS)
│   ├── health.py           # CircuitBreaker + HealthManager (889 LOC)
│   ├── models.py
│   ├── provider_registry.py # ProviderRegistry (628 LOC, dup methods)
│   ├── router.py           # ModelRouter facade (747 LOC, dup methods)
│   └── strategy.py         # RoutingStrategy ABC
├── scheduling/
│   ├── models.py           # (NO TESTS)
│   ├── policies.py         # 6 scheduling policies
│   ├── predictive.py       # WorkloadTracker
│   └── resource_pool.py    # ResourcePool
├── task/
│   └── models.py           # Task, TaskGraph (pure domain)
└── workflow/
    ├── state_machine.py    # (839 LOC)
    ├── templates.py        # (702 LOC)
    ├── orchestrator.py     # (548 LOC)
    └── resources.py        # (505 LOC)

configs/
├── budget.yaml             # Budget limits (some overlap with providers.yaml)
├── models.yaml             # Model capabilities & routing
├── providers.yaml          # Provider API keys (env var refs, no secrets)
└── verifiers.yaml          # Verifier pipeline

tests/                      # 61 test files, 1,074 test functions
  coordination/             # 4 files
  scheduling/               # 5 files (has own conftest.py with import hack)
  workflow/                 # 9 files
  test_*.py                 # 43 root-level files (some duplicates)
```

---

## Phase 2.5 Ticket Status

| Ticket | Description | Status |
|--------|-------------|--------|
| P2.5-01 | Setup wizard (`omni setup`) | ✅ Implemented (PR #?) |
| P2.5-02 | Model management CLI (`omni models add/status`) | ✅ Implemented (PR #61) |
| P2.5-03 | Capability auto-detection | ❌ Not built |
| P2.5-04 | Guided demo (`omni demo`) | ✅ Implemented |
| P2.5-05 | Zero-config defaults | ❌ Not built |
| P2.5-06 | Quick-start docs | ❌ Not built |

---

## Phase 2 Merged PRs

| PR | Component | Status |
|----|-----------|--------|
| #30-#36 | Phase 2.1: Model Router (6 PRs) | ✅ Merged |
| #32, #37-#39 | Phase 2.2: Task Decomposition (4 PRs) | ✅ Merged |
| #40-#46 | Phase 2.3-2.4: Execution, Coordination, Scheduling (7 PRs) | ✅ Merged |
| #61 | P2.5: omni models add/status | ✅ Merged |

---

## What's NOT Built Yet

| Component | Priority | Notes |
|-----------|----------|-------|
| Capability auto-detection (P2.5-03) | HIGH | Query LiteLLM for model capabilities |
| Zero-config defaults (P2.5-05) | HIGH | Remove "features not available" wall |
| Quick-start docs (P2.5-06) | MEDIUM | README rewrite, quickstart guide |
| Conflict Resolver | HIGH | `_reconstruct_file_content` returns None |
| Result Integrator verification | MEDIUM | `_run_verification` always passes |
| Git Worktree Manager lifecycle | MEDIUM | Basic git ops exist, no lifecycle |
| E2E Integration Tests | MEDIUM | No full pipeline tests |
| Execution resume | LOW | Raises NotImplementedError |

---

## CI/CD

```bash
# Pre-PR checks (all must pass):
ruff check .                              # Linting
mypy src/omni --ignore-missing-imports    # Type checking (strict mode)
pytest tests/ -v                          # Tests (1,074 functions)
```

**CI gaps**: No coverage reporting, no multi-Python-version matrix, release workflow skips tests.

---

## Development Protocol

1. **Isolated worktrees** for each agent task
2. **Branch naming**: `branches/YYYYMMDD_role-name_task`
3. **Review**: Implementer → Reviewer → Fixes → PR
4. **Merge rules**: Owner merges only, CI must be green

---

*This file is for LLM context loading. Not intended for human readers.*
*For user-facing docs, see README.md and docs/.*

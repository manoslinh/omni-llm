# Workflow Template Authoring Guide

## Overview

Workflow templates are YAML files that define reusable, parameterized workflows for common development tasks. They enable standardization, consistency, and automation of complex multi-agent processes.

## Template Structure

### Basic Template

```yaml
# Required fields
name: "Template Name"
description: "Brief description of what this template does"
version: "1.0.0"  # Semantic versioning

# Optional metadata
author: "Your Name"
created: "2024-01-01"
tags: ["code-review", "refactoring", "automation"]

# Template variables (parameterization)
variables:
  variable_name:
    description: "What this variable controls"
    required: true  # or false
    type: "string"  # string, number, boolean, array, object
    default: "default_value"  # if not required
    # For enums:
    # enum: ["option1", "option2", "option3"]
    # For validation:
    # pattern: "^[a-z]+$"  # regex pattern
    # min: 1  # for numbers/arrays
    # max: 10  # for numbers/arrays

# Workflow steps
steps:
  - name: "step_name"  # Unique identifier
    task_type: "task_type"  # See task types below
    description: "What this step does"
    # Additional step configuration...
```

## Variable Types

### String Variables
```yaml
variables:
  filename:
    description: "Name of the file to process"
    required: true
    type: "string"
    pattern: "^[a-zA-Z0-9_.-]+$"  # Optional validation

  environment:
    description: "Deployment environment"
    type: "string"
    default: "development"
    enum: ["development", "staging", "production"]
```

### Number Variables
```yaml
variables:
  timeout_seconds:
    description: "Maximum execution time in seconds"
    type: "number"
    default: 300
    min: 60
    max: 3600

  retry_count:
    description: "Number of retry attempts"
    type: "number"
    default: 3
    min: 0
    max: 10
```

### Boolean Variables
```yaml
variables:
  include_tests:
    description: "Whether to include test generation"
    type: "boolean"
    default: true

  strict_mode:
    description: "Enable strict validation"
    type: "boolean"
    default: false
```

### Array Variables
```yaml
variables:
  files:
    description: "List of files to process"
    type: "array"
    items:
      type: "string"
    default: []

  environments:
    description: "Environments to deploy to"
    type: "array"
    items:
      type: "string"
      enum: ["dev", "staging", "prod"]
    default: ["dev"]
```

### Object Variables
```yaml
variables:
  config:
    description: "Configuration object"
    type: "object"
    properties:
      log_level:
        type: "string"
        enum: ["debug", "info", "warn", "error"]
        default: "info"
      max_concurrent:
        type: "number"
        default: 5
    default:
      log_level: "info"
      max_concurrent: 5
```

## Step Configuration

### Basic Step
```yaml
steps:
  - name: "analyze"
    task_type: "analysis"
    description: "Analyze requirements and constraints"
    agent: "thinker"  # Optional: specify agent
    model: "mimo/mimo-v2-pro"  # Optional: specify model
    timeout: 600  # Optional: timeout in seconds
    retry: 2  # Optional: retry attempts
```

### Step with Dependencies
```yaml
steps:
  - name: "design"
    task_type: "design"
    description: "Design solution architecture"
    # No dependencies - can start immediately

  - name: "implement"
    task_type: "code_generation"
    description: "Implement the design"
    depends_on: ["design"]  # Wait for design to complete

  - name: "test"
    task_type: "testing"
    description: "Test the implementation"
    depends_on: ["implement"]  # Wait for implementation
```

### Conditional Steps
```yaml
steps:
  - name: "security_scan"
    task_type: "security"
    description: "Run security scan"
    condition: "{security_level} == 'high'"  # Only run if condition true

  - name: "performance_test"
    task_type: "testing"
    description: "Run performance tests"
    condition: "not {skip_perf_tests}"  # Can use boolean variables
```

### Parallel Steps
```yaml
steps:
  - name: "lint_frontend"
    task_type: "analysis"
    description: "Lint frontend code"
    # No dependencies between these three - run in parallel

  - name: "lint_backend"
    task_type: "analysis"
    description: "Lint backend code"

  - name: "security_check"
    task_type: "security"
    description: "Security checks"

  - name: "merge_results"
    task_type: "integration"
    description: "Merge all results"
    depends_on: ["lint_frontend", "lint_backend", "security_check"]  # Wait for all
```

### Looping Steps
```yaml
steps:
  - name: "process_files"
    task_type: "code_generation"
    description: "Process each file"
    for_each: "{files}"  # Loop over array variable
    loop_variable: "file"  # Current item available as {file}
    
  - name: "aggregate"
    task_type: "integration"
    description: "Aggregate all results"
    depends_on: ["process_files"]  # Wait for all loop iterations
```

## Task Types

### Analysis Tasks
- `analysis`: General analysis and requirements gathering
- `design`: Solution design and architecture
- `planning`: Execution planning and resource allocation

### Code Generation Tasks
- `code_generation`: Writing new code
- `refactoring`: Refactoring existing code
- `bug_fix`: Fixing bugs in existing code
- `documentation`: Writing documentation

### Validation Tasks
- `code_review`: Reviewing code for quality
- `testing`: Writing and running tests
- `security`: Security analysis and scanning
- `performance`: Performance testing and optimization

### Integration Tasks
- `integration`: Merging multiple results
- `deployment`: Deployment and release tasks
- `monitoring`: Setting up monitoring and alerts

### Administrative Tasks
- `configuration`: System configuration
- `cleanup`: Cleanup and maintenance tasks
- `reporting`: Generating reports and documentation

## Agent Assignment

### Explicit Agent Assignment
```yaml
steps:
  - name: "simple_task"
    task_type: "configuration"
    agent: "intern"  # Always use intern for this step
    model: "mimo/mimo-v2-flash"  # Specific model

  - name: "complex_task"
    task_type: "architecture"
    agent: "thinker"  # Always use thinker
    # Model will be chosen based on agent's default
```

### Dynamic Agent Assignment
```yaml
steps:
  - name: "implementation"
    task_type: "code_generation"
    # No agent specified - system chooses based on:
    # 1. Task type
    # 2. Complexity
    # 3. Available agents
    # 4. Cost constraints
```

### Agent Capability Matching
The system automatically matches tasks to agents based on:
1. **Required capabilities**: Task declares needed capabilities
2. **Agent profiles**: Agents declare their capabilities
3. **Cost optimization**: Choose cost-effective capable agent
4. **Load balancing**: Distribute work evenly

## Advanced Features

### Template Inheritance
```yaml
# base_template.yaml
name: "Base Workflow"
description: "Base template with common steps"
version: "1.0.0"

variables:
  project_name:
    description: "Name of the project"
    required: true
    type: "string"

steps:
  - name: "setup"
    task_type: "configuration"
    description: "Setup project {project_name}"

# specialized_template.yaml
extends: "base_template.yaml"  # Inherit from base

name: "Specialized Workflow"
description: "Extended workflow with additional steps"

steps:
  # Inherits all steps from base_template.yaml
  - name: "additional_step"
    task_type: "analysis"
    description: "Additional analysis for {project_name}"
    depends_on: ["setup"]  # Can depend on inherited steps
```

### Template Composition
```yaml
# code_review_template.yaml
name: "Code Review"
description: "Standard code review process"
# ... code review steps ...

# deployment_template.yaml  
name: "Deployment"
description: "Standard deployment process"
# ... deployment steps ...

# full_pipeline.yaml
name: "Full CI/CD Pipeline"
description: "Complete pipeline from code review to deployment"

steps:
  - include: "code_review_template.yaml"
    with:
      strictness: "high"
      
  - include: "deployment_template.yaml"
    with:
      environment: "production"
    depends_on: ["code_review_template"]  # Reference included template
```

### Error Handling
```yaml
steps:
  - name: "risky_operation"
    task_type: "code_generation"
    description: "Risky operation that might fail"
    on_error:
      action: "retry"  # retry, skip, fail, or continue
      max_attempts: 3
      delay: 10  # seconds between retries
      fallback_step: "safe_alternative"  # Step to run if all retries fail

  - name: "safe_alternative"
    task_type: "code_generation"
    description: "Safe alternative approach"
    # Only runs if risky_operation fails after all retries
```

### Timeouts and Resource Limits
```yaml
steps:
  - name: "long_running"
    task_type: "analysis"
    description: "Long-running analysis task"
    timeout: 3600  # 1 hour timeout
    max_tokens: 100000  # Token limit
    memory_limit: "2GB"  # Memory limit
    
  - name: "quick_check"
    task_type: "validation"
    description: "Quick validation check"
    timeout: 60  # 1 minute timeout
    max_tokens: 1000  # Small token limit
```

## Example Templates

### Code Review Workflow
```yaml
name: "Code Review Workflow"
description: "Comprehensive code review with automated checks"
version: "2.1.0"

variables:
  filename:
    description: "File to review"
    required: true
    type: "string"
  author:
    description: "Code author (for personalized feedback)"
    type: "string"
  strictness:
    description: "Review strictness level"
    type: "string"
    default: "medium"
    enum: ["light", "medium", "strict"]

steps:
  - name: "syntax_check"
    task_type: "analysis"
    description: "Check syntax and basic structure of {filename}"
    agent: "intern"
    timeout: 120

  - name: "style_review"
    task_type: "code_review"
    description: "Review code style and conventions"
    depends_on: ["syntax_check"]
    agent: "coder"
    condition: "{strictness} != 'light'"

  - name: "logic_review"
    task_type: "code_review"
    description: "Review business logic and algorithms"
    depends_on: ["syntax_check"]
    agent: "thinker"
    condition: "{strictness} == 'strict'"

  - name: "security_scan"
    task_type: "security"
    description: "Security vulnerability scan"
    depends_on: ["syntax_check"]
    agent: "coder"

  - name: "generate_feedback"
    task_type: "documentation"
    description: "Generate review feedback for {author}"
    depends_on: ["style_review", "logic_review", "security_scan"]
    agent: "reader"
```

### Feature Implementation Workflow
```yaml
name: "Feature Implementation Workflow"
description: "End-to-end feature implementation"
version: "1.2.0"

variables:
  feature_name:
    description: "Name of the feature to implement"
    required: true
    type: "string"
  complexity:
    description: "Estimated complexity"
    type: "string"
    default: "medium"
    enum: ["simple", "medium", "complex"]
  include_tests:
    description: "Whether to include tests"
    type: "boolean"
    default: true
  include_docs:
    description: "Whether to include documentation"
    type: "boolean"
    default: true

steps:
  - name: "requirements_analysis"
    task_type: "analysis"
    description: "Analyze requirements for {feature_name}"
    agent: "thinker"
    condition: "{complexity} != 'simple'"

  - name: "design"
    task_type: "design"
    description: "Design {feature_name} implementation"
    depends_on: ["requirements_analysis"]
    agent: "thinker"
    condition: "{complexity} == 'complex'"

  - name: "implementation"
    task_type: "code_generation"
    description: "Implement {feature_name}"
    depends_on: ["design"]
    agent: "coder"

  - name: "testing"
    task_type: "testing"
    description: "Test {feature_name}"
    depends_on: ["implementation"]
    agent: "intern"
    condition: "{include_tests}"

  - name: "documentation"
    task_type: "documentation"
    description: "Document {feature_name}"
    depends_on: ["implementation"]
    agent: "reader"
    condition: "{include_docs}"

  - name: "integration"
    task_type: "integration"
    description: "Integrate {feature_name} with existing codebase"
    depends_on: ["implementation", "testing", "documentation"]
    agent: "coder"
```

### Refactoring Workflow
```yaml
name: "Refactoring Workflow"
description: "Safe refactoring with validation"
version: "1.1.0"

variables:
  target_code:
    description: "Code to refactor (file or module)"
    required: true
    type: "string"
  refactoring_type:
    description: "Type of refactoring"
    required: true
    type: "string"
    enum: ["extract_method", "rename", "inline", "move", "general"]
  safety_level:
    description: "Safety precautions level"
    type: "string"
    default: "high"
    enum: ["low", "medium", "high"]

steps:
  - name: "pre_refactor_analysis"
    task_type: "analysis"
    description: "Analyze {target_code} before refactoring"
    agent: "reader"

  - name: "create_backup"
    task_type: "configuration"
    description: "Create backup of {target_code}"
    depends_on: ["pre_refactor_analysis"]
    agent: "intern"
    condition: "{safety_level} != 'low'"

  - name: "perform_refactoring"
    task_type: "refactoring"
    description: "Perform {refactoring_type} refactoring on {target_code}"
    depends_on: ["pre_refactor_analysis", "create_backup"]
    agent: "coder"

  - name: "validate_refactoring"
    task_type: "testing"
    description: "Validate refactoring didn't break functionality"
    depends_on: ["perform_refactoring"]
    agent: "intern"

  - name: "compare_results"
    task_type: "analysis"
    description: "Compare pre and post refactoring"
    depends_on: ["perform_refactoring", "validate_refactoring"]
    agent: "reader"
    condition: "{safety_level} == 'high'"

  - name: "cleanup_backup"
    task_type: "cleanup"
    description: "Clean up backup files"
    depends_on: ["compare_results"]
    agent: "intern"
    condition: "{safety_level} != 'low'"
```

## Best Practices

### 1. Start Simple
Begin with minimal templates and add complexity gradually:
- Start with 3-5 steps
- Add variables as needed
- Test thoroughly before adding advanced features

### 2. Use Meaningful Names
- Step names: `verb_noun` format (e.g., `analyze_requirements`)
- Variables: descriptive (e.g., `target_filename` not `file1`)
- Templates: indicate purpose (e.g., `api_endpoint_implementation`)

### 3. Parameterize Effectively
- Identify what varies between executions
- Make those aspects variables
- Provide sensible defaults
- Include validation where appropriate

### 4. Handle Errors Gracefully
- Include timeouts for all steps
- Add retry logic for flaky operations
- Provide fallback steps for critical failures
- Log errors comprehensively

### 5. Optimize for Parallelism
- Identify independent steps
- Minimize unnecessary dependencies
- Use `depends_on` only when truly needed
- Consider batch processing for similar operations

### 6. Document Thoroughly
- Describe what the template does
- Document all variables
- Explain complex steps
- Include usage examples

### 7. Version Control
- Use semantic versioning
- Document changes between versions
- Maintain backward compatibility when possible
- Deprecate old versions gracefully

## Template Validation

### Syntax Validation
```bash
# Validate template syntax
omni workflow validate template.yaml

# Validate with specific variables
omni workflow validate template.yaml --variables '{"filename": "test.py"}'
```

### Dry Run Execution
```bash
# Dry run without actual execution
omni workflow run template.yaml --dry-run --variables '{"target": "src/"}'
```

### Template Testing
Create test cases for your templates:
```yaml
# test_cases.yaml
test_cases:
  - name: "Simple case"
    variables:
      filename: "simple.py"
      strict
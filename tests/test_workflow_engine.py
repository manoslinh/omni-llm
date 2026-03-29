"""
Comprehensive tests for the workflow template engine.
"""

import tempfile
import os
from pathlib import Path
import pytest
import yaml

from omni.orchestration.workflow import WorkflowEngine
from omni.orchestration.workflow_models import (
    TaskType, VariableDef, WorkflowStep, WorkflowTemplate
)


class TestWorkflowModels:
    """Test workflow model classes."""
    
    def test_variable_def_validation(self):
        """Test VariableDef validation."""
        # Valid variable definitions
        var1 = VariableDef(name="test", description="Test", default="value", required=False, type="string")
        assert var1.validate_value("test") is True
        assert var1.validate_value(None) is True  # Not required
        
        var2 = VariableDef(name="required_var", description="Required", required=True, type="string")
        assert var2.validate_value(None) is False  # Required but None
        assert var2.validate_value("value") is True
        
        # Type validation
        var3 = VariableDef(name="number_var", type="number")
        assert var3.validate_value(42) is True
        assert var3.validate_value("not a number") is False
        
        var4 = VariableDef(name="bool_var", type="boolean")
        assert var4.validate_value(True) is True
        assert var4.validate_value(False) is True
        assert var4.validate_value("true") is False
    
    def test_workflow_step_creation(self):
        """Test WorkflowStep creation and validation."""
        step = WorkflowStep(
            name="test_step",
            task_type=TaskType.CODE_GENERATION,
            description_template="Test {variable}",
            files=["{file_path}"],
            depends_on=["previous_step"],
            model_override="coder",
            condition="{enabled}"
        )
        
        assert step.name == "test_step"
        assert step.task_type == TaskType.CODE_GENERATION
        assert "{variable}" in step.description_template
        assert "{file_path}" in step.files[0]
        assert "previous_step" in step.depends_on
        assert step.model_override == "coder"
        assert step.condition == "{enabled}"
        
        # Test variable substitution
        substituted = step.substitute_variables({
            "variable": "substituted",
            "file_path": "/path/to/file.py",
            "enabled": "true"
        })
        
        assert "substituted" in substituted.description_template
        assert "/path/to/file.py" in substituted.files[0]
        assert "true" == substituted.condition
    
    def test_workflow_step_validation(self):
        """Test WorkflowStep validation."""
        # Valid step
        step = WorkflowStep(
            name="valid_step",
            task_type=TaskType.CODE_GENERATION,
            description_template="Valid description"
        )
        assert step.validate() == []
        
        # Invalid step - empty name
        step = WorkflowStep(
            name="",
            task_type=TaskType.CODE_GENERATION,
            description_template="Description"
        )
        assert "Step name cannot be empty" in step.validate()[0]
        
        # Invalid step - empty description
        step = WorkflowStep(
            name="test",
            task_type=TaskType.CODE_GENERATION,
            description_template=""
        )
        assert "Step description cannot be empty" in step.validate()[0]
        
        # Invalid step - self-dependency
        step = WorkflowStep(
            name="self_dep",
            task_type=TaskType.CODE_GENERATION,
            description_template="Description",
            depends_on=["self_dep"]
        )
        assert "cannot depend on itself" in step.validate()[0]
    
    def test_workflow_template_creation(self):
        """Test WorkflowTemplate creation."""
        variables = {
            "file_path": VariableDef(name="file_path", description="File to process", required=True)
        }
        
        steps = [
            WorkflowStep(
                name="step1",
                task_type=TaskType.ANALYSIS,
                description_template="Analyze {file_path}"
            ),
            WorkflowStep(
                name="step2",
                task_type=TaskType.CODE_GENERATION,
                description_template="Process {file_path}",
                depends_on=["step1"]
            )
        ]
        
        template = WorkflowTemplate(
            name="Test Workflow",
            description="Test workflow template",
            version="1.0.0",
            variables=variables,
            steps=steps
        )
        
        assert template.name == "Test Workflow"
        assert len(template.variables) == 1
        assert len(template.steps) == 2
        assert template.steps[1].depends_on == ["step1"]
    
    def test_workflow_template_validation(self):
        """Test WorkflowTemplate validation."""
        # Valid template
        template = WorkflowTemplate(
            name="Valid",
            description="Valid template",
            version="1.0.0",
            steps=[
                WorkflowStep(
                    name="step1",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Step 1"
                )
            ]
        )
        assert template.validate() == []
        
        # Invalid template - empty name
        template = WorkflowTemplate(name="", description="Test", version="1.0.0")
        assert "Template name cannot be empty" in template.validate()[0]
        
        # Invalid template - empty description
        template = WorkflowTemplate(name="Test", description="", version="1.0.0")
        assert "Template description cannot be empty" in template.validate()[0]
        
        # Invalid template - bad version
        template = WorkflowTemplate(name="Test", description="Test", version="1.0")
        assert "Invalid version format" in template.validate()[0]
        
        # Invalid template - duplicate step names
        template = WorkflowTemplate(
            name="Test",
            description="Test",
            version="1.0.0",
            steps=[
                WorkflowStep(
                    name="duplicate",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Step 1"
                ),
                WorkflowStep(
                    name="duplicate",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Step 2"
                )
            ]
        )
        assert "Duplicate step name" in template.validate()[0]
        
        # Invalid template - circular dependencies
        template = WorkflowTemplate(
            name="Test",
            description="Test",
            version="1.0.0",
            steps=[
                WorkflowStep(
                    name="step1",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Step 1",
                    depends_on=["step2"]
                ),
                WorkflowStep(
                    name="step2",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Step 2",
                    depends_on=["step1"]
                )
            ]
        )
        assert "circular dependencies" in template.validate()[0]
    
    def test_workflow_template_variable_substitution(self):
        """Test variable substitution in workflow templates."""
        template = WorkflowTemplate(
            name="Test",
            description="Test {var1} and {var2}",
            version="1.0.0",
            variables={
                "var1": VariableDef(name="var1", default="default1"),
                "var2": VariableDef(name="var2", required=True)
            },
            steps=[
                WorkflowStep(
                    name="step1",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Process {var1} and {var2}"
                )
            ]
        )
        
        # Test with all variables provided
        substituted = template.substitute_variables({"var1": "value1", "var2": "value2"})
        assert "value1 and value2" in substituted.description
        assert "Process value1 and value2" in substituted.steps[0].description_template
        
        # Test with default value
        substituted = template.substitute_variables({"var2": "value2"})
        assert "default1 and value2" in substituted.description
        
        # Test missing required variable
        with pytest.raises(ValueError, match="Required variable"):
            template.substitute_variables({"var1": "value1"})
    
    def test_workflow_template_execution_order(self):
        """Test execution order calculation."""
        # Linear workflow
        template = WorkflowTemplate(
            name="Linear",
            description="Linear workflow",
            version="1.0.0",
            steps=[
                WorkflowStep(name="step1", task_type=TaskType.CODE_GENERATION, description_template="Step 1"),
                WorkflowStep(name="step2", task_type=TaskType.CODE_GENERATION, description_template="Step 2", depends_on=["step1"]),
                WorkflowStep(name="step3", task_type=TaskType.CODE_GENERATION, description_template="Step 3", depends_on=["step2"])
            ]
        )
        
        order = template.get_execution_order()
        assert order == [["step1"], ["step2"], ["step3"]]
        
        # Parallel workflow
        template = WorkflowTemplate(
            name="Parallel",
            description="Parallel workflow",
            version="1.0.0",
            steps=[
                WorkflowStep(name="step1", task_type=TaskType.CODE_GENERATION, description_template="Step 1"),
                WorkflowStep(name="step2", task_type=TaskType.CODE_GENERATION, description_template="Step 2"),
                WorkflowStep(name="step3", task_type=TaskType.CODE_GENERATION, description_template="Step 3", depends_on=["step1", "step2"])
            ]
        )
        
        order = template.get_execution_order()
        assert set(order[0]) == {"step1", "step2"}
        assert order[1] == ["step3"]
        
        # Complex workflow
        template = WorkflowTemplate(
            name="Complex",
            description="Complex workflow",
            version="1.0.0",
            steps=[
                WorkflowStep(name="A", task_type=TaskType.CODE_GENERATION, description_template="A"),
                WorkflowStep(name="B", task_type=TaskType.CODE_GENERATION, description_template="B", depends_on=["A"]),
                WorkflowStep(name="C", task_type=TaskType.CODE_GENERATION, description_template="C", depends_on=["A"]),
                WorkflowStep(name="D", task_type=TaskType.CODE_GENERATION, description_template="D", depends_on=["B", "C"])
            ]
        )
        
        order = template.get_execution_order()
        assert order[0] == ["A"]
        assert set(order[1]) == {"B", "C"}
        assert order[2] == ["D"]


class TestWorkflowEngine:
    """Test WorkflowEngine class."""
    
    def test_engine_initialization(self):
        """Test WorkflowEngine initialization."""
        engine = WorkflowEngine()
        assert engine.coordination_engine is None
        
        # Test with mock coordination engine
        mock_coord = object()
        engine = WorkflowEngine(coordination_engine=mock_coord)
        assert engine.coordination_engine is mock_coord
    
    def test_load_template_from_yaml(self):
        """Test loading a template from YAML."""
        engine = WorkflowEngine()
        
        # Create a temporary YAML file
        yaml_content = """
name: "Test Workflow"
description: "Test workflow from YAML"
version: "1.0.0"

variables:
  file_path:
    description: "File to process"
    required: true
    type: "string"

steps:
  - name: "analyze"
    task_type: "analysis"
    description: "Analyze {file_path}"
    files: ["{file_path}"]
    
  - name: "process"
    task_type: "code_generation"
    description: "Process {file_path}"
    files: ["{file_path}"]
    depends_on: ["analyze"]
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            template = engine.load_template(temp_path)
            
            assert template.name == "Test Workflow"
            assert template.description == "Test workflow from YAML"
            assert template.version == "1.0.0"
            assert len(template.variables) == 1
            assert len(template.steps) == 2
            assert template.steps[0].name == "analyze"
            assert template.steps[0].task_type == TaskType.ANALYSIS
            assert template.steps[1].name == "process"
            assert template.steps[1].depends_on == ["analyze"]
            
            # Test validation
            errors = engine.validate_template(template)
            assert errors == []
            
        finally:
            os.unlink(temp_path)
    
    def test_load_template_invalid_yaml(self):
        """Test loading invalid YAML."""
        engine = WorkflowEngine()
        
        # Create invalid YAML
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: [yaml: content")
            temp_path = f.name
        
        try:
            with pytest.raises(yaml.YAMLError):
                engine.load_template(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_load_template_missing_file(self):
        """Test loading non-existent template file."""
        engine = WorkflowEngine()
        
        with pytest.raises(FileNotFoundError):
            engine.load_template("/nonexistent/path/template.yaml")
    
    def test_load_template_invalid_structure(self):
        """Test loading template with invalid structure."""
        engine = WorkflowEngine()
        
        # Template with invalid task type
        yaml_content = """
name: "Invalid"
description: "Invalid template"
version: "1.0.0"

steps:
  - name: "invalid_step"
    task_type: "invalid_task_type"
    description: "Invalid step"
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError, match="Invalid task type"):
                engine.load_template(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_execute_template_mock(self):
        """Test executing a template (mock execution)."""
        engine = WorkflowEngine()
        
        template = WorkflowTemplate(
            name="Test Execution",
            description="Test workflow execution",
            version="1.0.0",
            steps=[
                WorkflowStep(
                    name="step1",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Step 1"
                )
            ]
        )
        
        result = engine.execute(template, {})
        
        assert result.success is True
        assert "Test Execution" in result.commit_message
        assert "Mock execution" in result.warnings[0]
        assert result.metadata["workflow_name"] == "Test Execution"
        assert result.metadata["mock_execution"] is True
    
    def test_execute_with_variables(self):
        """Test executing a template with variable substitution."""
        engine = WorkflowEngine()
        
        template = WorkflowTemplate(
            name="Test",
            description="Test {var1}",
            version="1.0.0",
            variables={
                "var1": VariableDef(name="var1", required=True),
                "var2": VariableDef(name="var2", default="default")
            },
            steps=[
                WorkflowStep(
                    name="step1",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Process {var1} and {var2}"
                )
            ]
        )
        
        result = engine.execute(template, {"var1": "value1"})
        assert result.success is True
    
    def test_execute_missing_required_variable(self):
        """Test executing template with missing required variable."""
        engine = WorkflowEngine()
        
        template = WorkflowTemplate(
            name="Test",
            description="Test",
            version="1.0.0",
            variables={
                "required_var": VariableDef(name="required_var", required=True)
            },
            steps=[]
        )
        
        with pytest.raises(ValueError, match="Required variable"):
            engine.execute(template, {})
    
    def test_condition_evaluation(self):
        """Test condition evaluation in workflow steps."""
        engine = WorkflowEngine()
        
        # Test with variable in context
        context = {"enabled": True, "count": 5}
        
        # Simple variable check
        assert engine._evaluate_condition("{enabled}", context) is True
        assert engine._evaluate_condition("{count}", context) is True
        assert engine._evaluate_condition("{missing}", context) is False
        
        # Test Python expression
        assert engine._evaluate_condition("True", context) is True
        assert engine._evaluate_condition("False", context) is False
        assert engine._evaluate_condition("count > 3", context) is True
        assert engine._evaluate_condition("count < 3", context) is False
        
        # Test complex expression with variables
        assert engine._evaluate_condition("{enabled} and count > 3", context) is True
        assert engine._evaluate_condition("{enabled} and count < 3", context) is False
    
    def test_create_task_graph(self):
        """Test TaskGraph creation from workflow template."""
        engine = WorkflowEngine()
        
        template = WorkflowTemplate(
            name="Test Graph",
            description="Test task graph creation",
            version="1.0.0",
            steps=[
                WorkflowStep(
                    name="step1",
                    task_type=TaskType.ANALYSIS,
                    description_template="Analyze"
                ),
                WorkflowStep(
                    name="step2",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Generate",
                    depends_on=["step1"]
                )
            ]
        )
        
        task_graph = engine._create_task_graph(template, {})
        
        assert task_graph.name == "workflow-Test Graph"
        assert task_graph.size == 2
        
        task1 = task_graph.get_task("workflow-Test Graph-step1")
        assert task1.description == "Analyze"
        assert task1.task_type.value == "analysis"
        
        task2 = task_graph.get_task("workflow-Test Graph-step2")
        assert task2.description == "Generate"
        assert task2.task_type.value == "code_generation"
        assert "workflow-Test Graph-step1" in task2.dependencies
    
    def test_create_task_graph_with_condition(self):
        """Test TaskGraph creation with conditional steps."""
        engine = WorkflowEngine()
        
        template = WorkflowTemplate(
            name="Test Conditional",
            description="Test conditional steps",
            version="1.0.0",
            steps=[
                WorkflowStep(
                    name="step1",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Always run"
                ),
                WorkflowStep(
                    name="step2",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Conditional run",
                    condition="{run_step2}"
                )
            ]
        )
        
        # Test with condition true
        context = {"run_step2": True}
        task_graph = engine._create_task_graph(template, context)
        assert task_graph.size == 2
        
        # Test with condition false
        context = {"run_step2": False}
        task_graph = engine._create_task_graph(template, context)
        assert task_graph.size == 1
        assert "workflow-Test Conditional-step1" in task_graph.tasks
        assert "workflow-Test Conditional-step2" not in task_graph.tasks
    
    def test_task_type_mapping(self):
        """Test mapping between workflow TaskType and core TaskType."""
        engine = WorkflowEngine()
        
        # Test all mappings
        test_cases = [
            (TaskType.CODE_GENERATION, "code_generation"),
            (TaskType.CODE_REVIEW, "code_review"),
            (TaskType.TESTING, "testing"),
            (TaskType.REFACTORING, "refactoring"),
            (TaskType.DOCUMENTATION, "documentation"),
            (TaskType.ANALYSIS, "analysis"),
            (TaskType.CONFIGURATION, "configuration"),
            (TaskType.DEPLOYMENT, "deployment"),
            (TaskType.CUSTOM, "custom"),
        ]
        
        for workflow_type, expected_core_type in test_cases:
            core_type = engine._map_task_type(workflow_type)
            assert core_type.value == expected_core_type


class TestIntegration:
    """Integration tests for workflow engine."""
    
    def test_example_templates_load(self):
        """Test that example templates can be loaded."""
        engine = WorkflowEngine()
        
        example_dir = Path(__file__).parent.parent / "examples" / "workflow_templates"
        
        if not example_dir.exists():
            pytest.skip("Example templates directory not found")
        
        for template_file in example_dir.glob("*.yaml"):
            try:
                template = engine.load_template(str(template_file))
                errors = engine.validate_template(template)
                assert errors == [], f"Template {template_file} validation failed: {errors}"
                
                # Test basic properties
                assert template.name
                assert template.description
                assert template.version
                
                # Test variable substitution with dummy values
                dummy_vars = {}
                for var_name, var_def in template.variables.items():
                    if var_def.required:
                        # Provide dummy values for required variables
                        if var_def.type == "string":
                            dummy_vars[var_name] = "test_value"
                        elif var_def.type == "number":
                            dummy_vars[var_name] = 42
                        elif var_def.type == "boolean":
                            dummy_vars[var_name] = True
                        elif var_def.type == "list":
                            dummy_vars[var_name] = []
                        elif var_def.type == "dict":
                            dummy_vars[var_name] = {}
                
                substituted = template.substitute_variables(dummy_vars)
                assert substituted is not None
                
            except Exception as e:
                pytest.fail(f"Failed to load template {template_file}: {e}")
    
    def test_workflow_engine_in_package(self):
        """Test that workflow engine can be imported and used."""
        from omni.orchestration import WorkflowEngine, WorkflowTemplate, WorkflowStep, TaskType
        
        # Create a simple workflow
        template = WorkflowTemplate(
            name="Import Test",
            description="Test import functionality",
            version="1.0.0",
            steps=[
                WorkflowStep(
                    name="test_step",
                    task_type=TaskType.CODE_GENERATION,
                    description_template="Test step"
                )
            ]
        )
        
        # Create engine and validate
        engine = WorkflowEngine()
        errors = engine.validate_template(template)
        assert errors == []
        
        # Execute (mock)
        result = engine.execute(template, {})
        assert result.success is True
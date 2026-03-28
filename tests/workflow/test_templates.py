"""
Tests for workflow templates.
"""

import pytest

from src.omni.workflow.definition import WorkflowDefinition
from src.omni.workflow.nodes import NodeType
from src.omni.workflow.templates import (
    TemplateParameter,
    TemplateRegistry,
    WorkflowTemplate,
    get_template,
    get_template_registry,
    list_templates,
)


class TestTemplateRegistry:
    """Tests for TemplateRegistry."""

    def test_register_template(self):
        reg = TemplateRegistry()
        t = WorkflowTemplate(
            template_id="custom_test",
            name="Custom Test",
            description="A test template",
            builder=lambda p: WorkflowDefinition(workflow_id="test", name="Test", nodes={}),
        )
        reg.register(t)
        assert reg.get("custom_test") is not None

    def test_register_duplicate_raises(self):
        reg = TemplateRegistry()
        t1 = WorkflowTemplate(
            template_id="dup",
            name="Dup",
            description="Dup",
            builder=lambda p: WorkflowDefinition(workflow_id="d", name="D", nodes={}),
        )
        t2 = WorkflowTemplate(
            template_id="dup",
            name="Dup2",
            description="Dup2",
            builder=lambda p: WorkflowDefinition(workflow_id="d2", name="D2", nodes={}),
        )
        reg.register(t1)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(t2)

    def test_get_template(self):
        reg = TemplateRegistry()
        assert reg.get("nonexistent") is None

    def test_list_templates(self):
        reg = TemplateRegistry()
        templates = reg.list()
        assert len(templates) > 0

    def test_list_by_tag(self):
        reg = TemplateRegistry()
        code_templates = reg.list_by_tag("code")
        assert len(code_templates) > 0
        for t in code_templates:
            assert "code" in t.tags

    def test_builtin_templates_exist(self):
        reg = TemplateRegistry()
        assert reg.get("analyze_implement_test_review") is not None
        assert reg.get("explore_plan_implement") is not None
        assert reg.get("parallel_review") is not None
        assert reg.get("retry_until_success") is not None
        assert reg.get("safe_deploy") is not None


class TestWorkflowTemplate:
    """Tests for WorkflowTemplate."""

    def test_build_with_params(self):
        reg = TemplateRegistry()
        tmpl = reg.get("analyze_implement_test_review")
        wf = tmpl.build(task_id="test_001")
        assert wf.workflow_id is not None
        assert len(wf.nodes) > 0
        assert wf.entry_node_id in wf.nodes

    def test_build_missing_required_raises(self):
        reg = TemplateRegistry()
        tmpl = reg.get("analyze_implement_test_review")
        with pytest.raises(ValueError, match="Required parameter"):
            tmpl.build()  # Missing task_id

    def test_build_with_default_params(self):
        reg = TemplateRegistry()
        tmpl = reg.get("analyze_implement_test_review")
        wf = tmpl.build(task_id="test_002")
        # Should use default complexity_threshold=0.7
        assert wf is not None

    def test_each_builtin_builds_valid_workflow(self):
        """Each built-in template should produce a valid workflow definition."""
        reg = TemplateRegistry()
        test_params = {
            "analyze_implement_test_review": {"task_id": "test"},
            "explore_plan_implement": {"codebase_path": "/test"},
            "parallel_review": {"artifact_id": "artifact1"},
            "retry_until_success": {"task_id": "task1"},
            "safe_deploy": {"deployment_target": "staging"},
        }
        for template_id, params in test_params.items():
            tmpl = reg.get(template_id)
            wf = tmpl.build(**params)
            assert isinstance(wf, WorkflowDefinition)
            assert wf.workflow_id
            assert wf.entry_node_id in wf.nodes if wf.entry_node_id else True

    def test_builder_none_raises(self):
        t = WorkflowTemplate(
            template_id="nobuilder",
            name="No Builder",
            description="No builder",
        )
        with pytest.raises(ValueError, match="no builder function"):
            t.build()


class TestTemplateModuleFunctions:
    """Tests for module-level template functions."""

    def test_get_template_registry(self):
        reg = get_template_registry()
        assert reg is not None
        assert len(reg.list()) > 0

    def test_get_template(self):
        tmpl = get_template("retry_until_success")
        assert tmpl is not None
        assert tmpl.template_id == "retry_until_success"

    def test_list_templates(self):
        templates = list_templates()
        assert len(templates) >= 5

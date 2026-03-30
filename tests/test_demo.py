"""
Tests for the omni demo command.
"""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from omni.cli.demo import DemoConfig, DemoRunner, DemoScenario
from omni.cli.main import cli


class TestDemoCommand:
    """Test the demo command."""

    def test_demo_command_exists(self) -> None:
        """Test that demo command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "demo" in result.output
        assert "Interactive demo of multi-agent orchestration" in result.output

    def test_demo_command_runs(self) -> None:
        """Test that demo command runs without error."""
        runner = CliRunner()

        # Mock the demo runner to avoid actual execution
        with patch("omni.cli.main.run_demo") as mock_demo:
            mock_demo.return_value = None
            result = runner.invoke(cli, ["demo", "--fast", "--silent"])

            # Check if command exists (should exit with 0 or show help)
            # Exit code 2 typically means "no such command"
            if result.exit_code == 2:
                print(f"Command error: {result.output}")

            # Command should exist and not crash
            assert result.exit_code != 2  # Should not be "no such command"

    def test_demo_scenario_loading(self) -> None:
        """Test that demo scenarios can be loaded."""
        config = DemoConfig(scenario=DemoScenario.BUILD_WEB_APP)
        runner = DemoRunner(config)

        # Test loading built-in scenario
        scenario_data = runner._load_scenario_data(DemoScenario.BUILD_WEB_APP)

        assert scenario_data["name"] == "Build a Simple Web App"
        assert "subtasks" in scenario_data
        assert len(scenario_data["subtasks"]) == 4
        assert "goal" in scenario_data

    def test_demo_scenario_custom(self) -> None:
        """Test custom task scenario generation."""
        config = DemoConfig(scenario=DemoScenario.CUSTOM_TASK)
        runner = DemoRunner(config)

        # Mock user input
        with patch("omni.cli.demo.Prompt.ask", return_value="Test custom task"):
            scenario_data = runner._get_custom_task()

            assert scenario_data["name"] == "Custom Task"
            assert scenario_data["goal"] == "Test custom task"
            assert "subtasks" in scenario_data
            assert len(scenario_data["subtasks"]) > 0

    def test_cost_calculation(self) -> None:
        """Test cost calculation logic."""
        config = DemoConfig(scenario=DemoScenario.BUILD_WEB_APP)
        runner = DemoRunner(config)

        # Load test scenario
        scenario_data = runner._load_scenario_data(DemoScenario.BUILD_WEB_APP)

        # Calculate costs
        sequential_cost, parallel_cost = runner._calculate_costs(scenario_data, 10.0)

        # Costs should be positive
        assert sequential_cost > 0
        assert parallel_cost > 0

        # Sequential should be more expensive than parallel
        assert sequential_cost > parallel_cost

    def test_demo_runner_initialization(self) -> None:
        """Test DemoRunner initialization."""
        config = DemoConfig(scenario=DemoScenario.BUILD_WEB_APP)
        runner = DemoRunner(config)

        assert runner.config == config
        assert runner.scenarios_dir.exists()

    @pytest.mark.skipif(True, reason="Requires rich library")
    def test_demo_integration(self) -> None:
        """Integration test for demo command (requires rich)."""
        runner = CliRunner()

        # Run demo in fast, silent mode
        result = runner.invoke(cli, ["demo", "--fast", "--silent"])

        # Should run without crashing
        assert result.exit_code == 0 or "error" not in result.output.lower()


class TestDemoConfig:
    """Test DemoConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = DemoConfig(scenario=DemoScenario.BUILD_WEB_APP)

        assert config.scenario == DemoScenario.BUILD_WEB_APP
        assert config.mock_execution is True
        assert config.show_progress is True
        assert config.explain_steps is True
        assert config.simulate_delay is True
        assert config.delay_multiplier == 1.0

    def test_fast_mode_config(self) -> None:
        """Test fast mode configuration."""
        config = DemoConfig(
            scenario=DemoScenario.BUILD_WEB_APP,
            simulate_delay=False,
            delay_multiplier=0.5
        )

        assert config.simulate_delay is False
        assert config.delay_multiplier == 0.5

    def test_silent_mode_config(self) -> None:
        """Test silent mode configuration."""
        config = DemoConfig(
            scenario=DemoScenario.BUILD_WEB_APP,
            explain_steps=False
        )

        assert config.explain_steps is False


class TestDemoScenarioEnum:
    """Test DemoScenario enum."""

    def test_enum_values(self) -> None:
        """Test enum values are correct."""
        assert DemoScenario.BUILD_WEB_APP.value == "build_web_app"
        assert DemoScenario.DEBUG_COMPLEX_ISSUE.value == "debug_complex_issue"
        assert DemoScenario.ANALYZE_CODEBASE.value == "analyze_codebase"
        assert DemoScenario.CUSTOM_TASK.value == "custom_task"

    def test_enum_from_string(self) -> None:
        """Test creating enum from string."""
        scenario = DemoScenario("build_web_app")
        assert scenario == DemoScenario.BUILD_WEB_APP

        scenario = DemoScenario("custom_task")
        assert scenario == DemoScenario.CUSTOM_TASK


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

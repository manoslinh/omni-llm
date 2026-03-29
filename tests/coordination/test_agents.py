"""Tests for agent definitions and registry."""

import pytest

from omni.coordination.agents import (
    DEFAULT_AGENTS,
    AgentCapability,
    AgentProfile,
    AgentRegistry,
    AgentTier,
)


class TestAgentProfile:
    """Test AgentProfile dataclass."""

    def test_agent_profile_creation(self):
        """Test basic AgentProfile creation."""
        agent = AgentProfile(
            agent_id="test-agent",
            tier=AgentTier.CODER,
            model_id="test/model",
            display_name="Test Agent",
            capabilities={AgentCapability.CODE_GENERATION},
            max_complexity=5.0,
            max_context_tokens=8000,
            cost_per_million_tokens=0.1,
            priority=5,
            description="Test agent",
        )
        assert agent.agent_id == "test-agent"
        assert agent.tier == AgentTier.CODER
        assert agent.model_id == "test/model"
        assert AgentCapability.CODE_GENERATION in agent.capabilities
        assert agent.max_complexity == 5.0
        assert agent.max_context_tokens == 8000
        assert agent.cost_per_million_tokens == 0.1
        assert agent.priority == 5

    def test_agent_profile_validation(self):
        """Test AgentProfile validation."""
        # Valid max_complexity
        agent = AgentProfile(
            agent_id="test",
            tier=AgentTier.INTERN,
            model_id="test",
            display_name="Test",
            capabilities=set(),
            max_complexity=10.0,
        )
        assert agent.max_complexity == 10.0

        # Invalid max_complexity
        with pytest.raises(ValueError, match="max_complexity must be 0-10"):
            AgentProfile(
                agent_id="test",
                tier=AgentTier.INTERN,
                model_id="test",
                display_name="Test",
                capabilities=set(),
                max_complexity=11.0,
            )

        # Invalid max_context_tokens
        with pytest.raises(ValueError, match="max_context_tokens must be non-negative"):
            AgentProfile(
                agent_id="test",
                tier=AgentTier.INTERN,
                model_id="test",
                display_name="Test",
                capabilities=set(),
                max_context_tokens=-1,
            )

    def test_can_handle(self):
        """Test capability checking."""
        agent = AgentProfile(
            agent_id="test",
            tier=AgentTier.CODER,
            model_id="test",
            display_name="Test",
            capabilities={AgentCapability.CODE_GENERATION, AgentCapability.TESTING},
        )
        assert agent.can_handle(AgentCapability.CODE_GENERATION)
        assert agent.can_handle(AgentCapability.TESTING)
        assert not agent.can_handle(AgentCapability.VISION)

    def test_can_handle_complexity(self):
        """Test complexity handling."""
        agent = AgentProfile(
            agent_id="test",
            tier=AgentTier.CODER,
            model_id="test",
            display_name="Test",
            capabilities=set(),
            max_complexity=5.0,
        )
        assert agent.can_handle_complexity(3.0)
        assert agent.can_handle_complexity(5.0)
        assert not agent.can_handle_complexity(5.1)


class TestAgentRegistry:
    """Test AgentRegistry operations."""

    def test_default_agents(self):
        """Test that default agents are loaded."""
        registry = AgentRegistry()
        assert len(registry.agents) == 5
        assert "intern" in registry.agents
        assert "coder" in registry.agents
        assert "reader" in registry.agents
        assert "visual" in registry.agents
        assert "thinker" in registry.agents

    def test_register_unregister(self):
        """Test agent registration and unregistration."""
        registry = AgentRegistry()
        initial_count = len(registry.agents)

        # Register new agent
        new_agent = AgentProfile(
            agent_id="custom",
            tier=AgentTier.CODER,
            model_id="custom/model",
            display_name="Custom",
            capabilities={AgentCapability.CODE_GENERATION},
        )
        registry.register(new_agent)
        assert len(registry.agents) == initial_count + 1
        assert "custom" in registry.agents

        # Cannot register duplicate
        with pytest.raises(ValueError, match="already registered"):
            registry.register(new_agent)

        # Unregister
        unregistered = registry.unregister("custom")
        assert unregistered.agent_id == "custom"
        assert len(registry.agents) == initial_count

        # Cannot unregister non-existent
        with pytest.raises(KeyError, match="not found"):
            registry.unregister("non-existent")

    def test_get_methods(self):
        """Test get methods."""
        registry = AgentRegistry()

        # Get by ID
        coder = registry.get("coder")
        assert coder.agent_id == "coder"
        assert coder.tier == AgentTier.CODER

        # Get non-existent
        with pytest.raises(KeyError, match="not found"):
            registry.get("non-existent")

        # Get by tier
        coders = registry.get_by_tier(AgentTier.CODER)
        assert len(coders) == 1
        assert coders[0].agent_id == "coder"

        # Get by capability
        code_gen_agents = registry.get_by_capability(AgentCapability.CODE_GENERATION)
        assert len(code_gen_agents) > 0
        assert all(AgentCapability.CODE_GENERATION in a.capabilities for a in code_gen_agents)

        # Get by capability with complexity filter
        low_complexity_agents = registry.get_by_capability(
            AgentCapability.FORMATTING, max_complexity=3.0
        )
        # Intern should be included (max_complexity=3.0, has formatting capability)
        intern_ids = [a.agent_id for a in low_complexity_agents]
        assert "intern" in intern_ids

    def test_get_escalation_target(self):
        """Test escalation chain."""
        registry = AgentRegistry()

        # Intern → Coder
        target = registry.get_escalation_target("intern")
        assert target is not None
        assert target.agent_id == "coder"

        # Coder → Reader
        target = registry.get_escalation_target("coder")
        assert target is not None
        assert target.agent_id == "reader"

        # Reader → Thinker
        target = registry.get_escalation_target("reader")
        assert target is not None
        assert target.agent_id == "thinker"

        # Thinker → None (already at top)
        target = registry.get_escalation_target("thinker")
        assert target is None

        # Visual → Thinker (specialist escalates to thinker)
        target = registry.get_escalation_target("visual")
        assert target is not None
        assert target.agent_id == "thinker"

        # Unknown → Thinker (fallback)
        target = registry.get_escalation_target("unknown")
        assert target is not None
        assert target.agent_id == "thinker"

    def test_summary(self):
        """Test registry summary."""
        registry = AgentRegistry()
        summary = registry.summary()

        assert "intern" in summary
        assert "coder" in summary
        assert "reader" in summary
        assert "visual" in summary
        assert "thinker" in summary

        coder_summary = summary["coder"]
        assert coder_summary["tier"] == "coder"
        assert "deepseek/deepseek-chat" in coder_summary["model"]
        assert "code_generation" in coder_summary["capabilities"]


class TestDefaultAgents:
    """Test default agent definitions."""

    def test_default_agents_exist(self):
        """Test that all required default agents exist."""
        assert "intern" in DEFAULT_AGENTS
        assert "coder" in DEFAULT_AGENTS
        assert "reader" in DEFAULT_AGENTS
        assert "visual" in DEFAULT_AGENTS
        assert "thinker" in DEFAULT_AGENTS

    def test_intern_agent(self):
        """Test Intern agent properties."""
        intern = DEFAULT_AGENTS["intern"]
        assert intern.tier == AgentTier.INTERN
        assert intern.model_id == "mimo/mimo-v2-flash"
        assert AgentCapability.FORMATTING in intern.capabilities
        assert AgentCapability.EXTRACTION in intern.capabilities
        assert AgentCapability.DOCUMENTATION in intern.capabilities
        assert intern.max_complexity == 3.0

    def test_coder_agent(self):
        """Test Coder agent properties."""
        coder = DEFAULT_AGENTS["coder"]
        assert coder.tier == AgentTier.CODER
        assert coder.model_id == "deepseek/deepseek-chat"
        assert AgentCapability.CODE_GENERATION in coder.capabilities
        assert AgentCapability.CODE_REVIEW in coder.capabilities
        assert AgentCapability.TESTING in coder.capabilities
        assert AgentCapability.DEBUGGING in coder.capabilities
        assert coder.max_complexity == 5.5

    def test_reader_agent(self):
        """Test Reader agent properties."""
        reader = DEFAULT_AGENTS["reader"]
        assert reader.tier == AgentTier.READER
        assert reader.model_id == "moonshot/kimi-k2.5"
        assert AgentCapability.LONG_CONTEXT in reader.capabilities
        assert AgentCapability.CODE_REVIEW in reader.capabilities
        assert AgentCapability.EXTRACTION in reader.capabilities
        assert reader.max_complexity == 7.5

    def test_visual_agent(self):
        """Test Visual agent properties."""
        visual = DEFAULT_AGENTS["visual"]
        assert visual.tier == AgentTier.VISUAL
        assert visual.model_id == "mimo/mimo-v2-omni"
        assert AgentCapability.VISION in visual.capabilities
        assert AgentCapability.IMAGE_ANALYSIS in visual.capabilities
        assert visual.max_complexity == 5.0

    def test_thinker_agent(self):
        """Test Thinker agent properties."""
        thinker = DEFAULT_AGENTS["thinker"]
        assert thinker.tier == AgentTier.THINKER
        assert thinker.model_id == "mimo/mimo-v2-pro"
        assert AgentCapability.ARCHITECTURE in thinker.capabilities
        assert AgentCapability.REASONING in thinker.capabilities
        assert thinker.max_complexity == 10.0

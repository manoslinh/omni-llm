"""
Test script for provider configuration system.
"""

import os
import sys

sys.path.insert(0, 'src')

from omni.providers.config import (
    ConfigLoader,
    ProviderConfig,
    get_default_providers_config,
)


def test_config_loading():
    """Test loading provider configuration."""
    # Set dummy environment variables for validation
    env_vars_to_set = [
        "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "COHERE_API_KEY", 
        "MISTRAL_API_KEY", "OPENAI_API_KEY", "TOGETHER_API_KEY",
        "FIREWORKS_API_KEY", "BEDROCK_AWS_ACCESS_KEY_ID",
        "BEDROCK_AWS_SECRET_ACCESS_KEY", "BEDROCK_AWS_REGION",
        "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
        "SAMBANOVA_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY",
        "OLLAMA_BASE_URL", "VERTEX_AI_PROJECT", "VERTEX_AI_LOCATION"
    ]
    
    original_env = {}
    for var in env_vars_to_set:
        if var in os.environ:
            original_env[var] = os.environ[var]
        os.environ[var] = "dummy-value-for-testing"
    
    try:
        # Load default config
        config = get_default_providers_config()

        # Check providers
        assert len(config.providers) > 0, "No providers loaded"

        # Check default provider
        default_provider = config.get_default_provider()
        assert default_provider is not None, "Default provider not found"
        assert default_provider.name == "litellm", f"Expected 'litellm', got '{default_provider.name}'"

        # Check default model
        default_model = config.get_default_model()
        assert default_model == "openai/gpt-4", f"Expected 'openai/gpt-4', got '{default_model}'"

        # Check model support
        assert default_provider.is_model_supported("openai/gpt-4"), "Model 'openai/gpt-4' not supported"

        # Check cost configuration
        gpt4_cost = config.get_model_cost("openai/gpt-4")
        assert gpt4_cost is not None, "Cost configuration for 'openai/gpt-4' not found"
        assert gpt4_cost.input_per_million == 30.00, f"Expected input cost 30.00, got {gpt4_cost.input_per_million}"
        assert gpt4_cost.output_per_million == 60.00, f"Expected output cost 60.00, got {gpt4_cost.output_per_million}"

        # Check validation (should pass with dummy env vars)
        errors = config.validate()
        assert not errors, f"Validation errors: {errors}"
    
    finally:
        # Restore original environment
        for var in env_vars_to_set:
            if var in original_env:
                os.environ[var] = original_env[var]
            else:
                del os.environ[var]


def test_environment_variable_substitution():
    """Test environment variable substitution in YAML."""
    # Set environment variable
    os.environ["TEST_API_KEY"] = "test-key-123"

    # Create a temporary YAML file with env var
    import tempfile
    import yaml

    yaml_content = """
    providers:
      - name: test-provider
        type: openai
        config:
          api_key: ${TEST_API_KEY}
        models:
          test-model:
            cost:
              input_per_million: 10.0
              output_per_million: 20.0
    """

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_file = f.name

    try:
        # Load config
        loader = ConfigLoader()
        config_dict = loader.load_yaml(temp_file)

        # Check that env var was substituted
        provider_config = config_dict["providers"][0]
        assert provider_config["config"]["api_key"] == "test-key-123", \
            f"Expected 'test-key-123', got '{provider_config['config'].get('api_key')}'"
    finally:
        # Clean up
        os.unlink(temp_file)
        del os.environ["TEST_API_KEY"]


def test_provider_config_class():
    """Test ProviderConfig class."""
    # Create a provider config
    config = ProviderConfig(
        name="test-provider",
        type="openai",
        description="Test provider",
        config={"api_key": "test-key"},
        models={
            "test-model": {
                "cost": {
                    "input_per_million": 10.0,
                    "output_per_million": 20.0,
                }
            }
        }
    )

    # Check attributes
    assert config.name == "test-provider"
    assert config.type == "openai"
    assert config.description == "Test provider"
    assert config.config["api_key"] == "test-key"
    assert len(config.models) == 1
    assert "test-model" in config.models
    assert config.models["test-model"]["cost"]["input_per_million"] == 10.0
    assert config.models["test-model"]["cost"]["output_per_million"] == 20.0

    # Check model support (ProviderConfig doesn't have is_model_supported method)
    # Check cost retrieval (ProviderConfig doesn't have get_model_cost method)
    # These methods are on ProvidersConfig, not ProviderConfig


def test_cost_estimation():
    """Test cost estimation."""
    config = get_default_providers_config()
    gpt4_cost = config.get_model_cost("openai/gpt-4")

    # Estimate cost for 1000 input tokens and 500 output tokens
    input_tokens = 1000
    output_tokens = 500
    estimated_cost = gpt4_cost.estimate_cost(input_tokens, output_tokens)

    # Expected cost: (1000/1M * 30) + (500/1M * 60) = 0.00003 + 0.00003 = 0.00006
    expected_cost = (1000 / 1_000_000 * 30.0) + (500 / 1_000_000 * 60.0)
    tolerance = 0.000001  # Allow for floating point errors

    assert abs(estimated_cost - expected_cost) < tolerance, \
        f"Expected cost ~{expected_cost:.6f}, got {estimated_cost:.6f}"

    # Test with zero tokens
    zero_cost = gpt4_cost.estimate_cost(0, 0)
    assert zero_cost == 0.0, f"Expected 0.0 for zero tokens, got {zero_cost}"
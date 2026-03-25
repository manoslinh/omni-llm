#!/usr/bin/env python3
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
    print("Testing configuration loading...")

    # Load default config
    config = get_default_providers_config()

    # Check providers
    assert len(config.providers) > 0, "No providers loaded"
    print(f"✓ Loaded {len(config.providers)} providers")

    # Check default provider
    default_provider = config.get_default_provider()
    assert default_provider is not None, "Default provider not found"
    assert default_provider.name == "litellm", f"Expected 'litellm', got '{default_provider.name}'"
    print(f"✓ Default provider: {default_provider.name}")

    # Check default model
    default_model = config.get_default_model()
    assert default_model == "openai/gpt-4", f"Expected 'openai/gpt-4', got '{default_model}'"
    print(f"✓ Default model: {default_model}")

    # Check model support
    assert default_provider.is_model_supported("openai/gpt-4"), "Model 'openai/gpt-4' not supported"
    print("✓ Model 'openai/gpt-4' is supported")

    # Check cost configuration
    gpt4_cost = config.get_model_cost("openai/gpt-4")
    assert gpt4_cost is not None, "Cost configuration for 'openai/gpt-4' not found"
    assert gpt4_cost.input_per_million == 30.00, f"Expected input cost 30.00, got {gpt4_cost.input_per_million}"
    assert gpt4_cost.output_per_million == 60.00, f"Expected output cost 60.00, got {gpt4_cost.output_per_million}"
    print(f"✓ Cost configuration for 'openai/gpt-4': ${gpt4_cost.input_per_million}/M input, ${gpt4_cost.output_per_million}/M output")

    # Check validation
    errors = config.validate()
    if errors:
        print(f"✗ Validation errors: {errors}")
        return False
    else:
        print("✓ Configuration validation passed")

    return True


def test_environment_variable_substitution():
    """Test environment variable substitution in YAML."""
    print("\nTesting environment variable substitution...")

    # Set a test environment variable
    os.environ["TEST_API_KEY"] = "test-key-123"

    # Create a test YAML content
    test_yaml = """
test_key: "${TEST_API_KEY}"
default_key: "${UNSET_VAR:-default_value}"
"""

    # Test substitution
    substituted = ConfigLoader._substitute_env_vars(test_yaml)

    # Check if substitution worked
    assert "test-key-123" in substituted, "Environment variable not substituted"
    print("✓ Environment variable substitution works")

    # Clean up
    del os.environ["TEST_API_KEY"]

    return True


def test_provider_config_class():
    """Test ProviderConfig class."""
    print("\nTesting ProviderConfig class...")

    # Create a provider config
    provider = ProviderConfig(
        name="test-provider",
        type="litellm",
        description="Test provider",
        enabled=True,
        config={"timeout": 30},
        models={"test-model": {"max_tokens": 1000}}
    )

    # Test properties
    assert provider.name == "test-provider"
    assert provider.type == "litellm"
    assert provider.is_model_supported("test-model")
    assert not provider.is_model_supported("non-existent-model")

    # Test model config
    model_config = provider.get_model_config("test-model")
    assert model_config is not None
    assert model_config["max_tokens"] == 1000

    print("✓ ProviderConfig class works correctly")
    return True


def test_cost_estimation():
    """Test cost estimation."""
    print("\nTesting cost estimation...")

    config = get_default_providers_config()
    gpt4_cost = config.get_model_cost("openai/gpt-4")

    # Estimate cost for 1000 input tokens and 500 output tokens
    input_tokens = 1000
    output_tokens = 500
    estimated_cost = gpt4_cost.estimate_cost(input_tokens, output_tokens)

    # Expected cost: (1000/1M * 30) + (500/1M * 60) = 0.00003 + 0.00003 = 0.00006
    expected_cost = (input_tokens / 1_000_000) * 30.00 + (output_tokens / 1_000_000) * 60.00
    assert abs(estimated_cost - expected_cost) < 0.000001, f"Cost estimation mismatch: {estimated_cost} vs {expected_cost}"

    print(f"✓ Cost estimation: ${estimated_cost:.6f} for {input_tokens} input + {output_tokens} output tokens")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Provider Configuration System Tests")
    print("=" * 60)

    all_passed = True

    tests = [
        test_config_loading,
        test_environment_variable_substitution,
        test_provider_config_class,
        test_cost_estimation,
    ]

    for test in tests:
        try:
            if not test():
                all_passed = False
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

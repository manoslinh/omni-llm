"""
Provider Configuration System for Omni-LLM.

Handles loading, validation, and management of provider configurations.
Supports environment variable substitution and YAML-based configuration.
"""

import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import yaml


@dataclass
class ProviderConfig:
    """Configuration for a single provider."""
    
    name: str
    type: str
    description: str = ""
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    models: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.name:
            raise ValueError("Provider name cannot be empty")
        if not self.type:
            raise ValueError("Provider type cannot be empty")
    
    def get_model_config(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific model."""
        return self.models.get(model_id)
    
    def is_model_supported(self, model_id: str) -> bool:
        """Check if a model is supported by this provider."""
        return model_id in self.models
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProviderConfig':
        """Create ProviderConfig from dictionary."""
        return cls(**data)


@dataclass
class APIKeyConfig:
    """Configuration for API key management."""
    
    name: str
    env_var: str
    description: str = ""
    required: bool = True
    default: Optional[str] = None
    
    def get_value(self) -> Optional[str]:
        """Get API key value from environment or default."""
        value = os.getenv(self.env_var)
        if value is None and self.default is not None:
            value = self.default
        return value
    
    def is_set(self) -> bool:
        """Check if API key is set."""
        return self.get_value() is not None


@dataclass
class ModelCostConfig:
    """Configuration for model costs."""
    
    model_id: str
    input_per_million: float
    output_per_million: float
    currency: str = "USD"
    
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for given token counts."""
        input_cost = (input_tokens / 1_000_000) * self.input_per_million
        output_cost = (output_tokens / 1_000_000) * self.output_per_million
        return input_cost + output_cost


@dataclass
class BudgetConfig:
    """Configuration for budget and rate limiting."""
    
    daily_limit: float = 10.0
    per_session_limit: float = 2.0
    warning_threshold: float = 0.8
    hard_limit: bool = True
    
    def should_warn(self, spent: float) -> bool:
        """Check if warning should be issued."""
        return spent >= self.daily_limit * self.warning_threshold
    
    def should_stop(self, spent: float) -> bool:
        """Check if spending should be stopped."""
        return self.hard_limit and spent >= self.daily_limit


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    
    enabled: bool = True
    requests_per_minute: int = 60
    tokens_per_minute: int = 150000
    burst_capacity: int = 10


@dataclass
class ProviderConfiguration:
    """Main configuration container for all providers."""
    
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    defaults: Dict[str, Any] = field(default_factory=dict)
    api_keys: Dict[str, str] = field(default_factory=dict)
    provider_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cost_config: Dict[str, ModelCostConfig] = field(default_factory=dict)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    rate_limiting: RateLimitConfig = field(default_factory=RateLimitConfig)
    
    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """Get provider configuration by name."""
        return self.providers.get(name)
    
    def get_default_provider(self) -> Optional[ProviderConfig]:
        """Get the default provider configuration."""
        default_name = self.defaults.get("provider")
        if default_name:
            return self.providers.get(default_name)
        return None
    
    def get_default_model(self) -> str:
        """Get the default model."""
        return self.defaults.get("model", "gpt-4")
    
    def get_model_cost(self, model_id: str) -> Optional[ModelCostConfig]:
        """Get cost configuration for a model."""
        return self.cost_config.get(model_id)
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        # Check default provider exists
        default_provider = self.defaults.get("provider")
        if default_provider and default_provider not in self.providers:
            errors.append(f"Default provider '{default_provider}' not found in providers")
        
        # Check default model exists
        default_model = self.defaults.get("model")
        if default_model:
            # Check if model is supported by any provider
            model_found = False
            for provider in self.providers.values():
                if provider.is_model_supported(default_model):
                    model_found = True
                    break
            if not model_found:
                errors.append(f"Default model '{default_model}' not supported by any provider")
        
        # Check API keys are set (if required)
        # Note: We don't require API keys to be set for all providers
        # Some providers may work without API keys (e.g., local Ollama)
        pass
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "providers": {name: config.to_dict() for name, config in self.providers.items()},
            "defaults": self.defaults,
            "api_keys": self.api_keys,
            "provider_configs": self.provider_configs,
            "cost_config": {k: asdict(v) for k, v in self.cost_config.items()},
            "budget": asdict(self.budget),
            "rate_limiting": asdict(self.rate_limiting),
        }


class ConfigLoader:
    """Utility class for loading provider configurations from YAML files."""
    
    @staticmethod
    def load_yaml(file_path: Union[str, Path]) -> Dict[str, Any]:
        """Load YAML file with environment variable substitution."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Substitute environment variables
        content = ConfigLoader._substitute_env_vars(content)
        
        # Parse YAML
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {file_path}: {e}")
    
    @staticmethod
    def _substitute_env_vars(content: str) -> str:
        """Substitute environment variables in YAML content."""
        # Pattern to match ${VAR_NAME} or $VAR_NAME
        pattern = r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)'
        
        def replace_match(match):
            # Try both patterns
            var_name = match.group(1) or match.group(2)
            value = os.getenv(var_name, match.group(0))  # Keep original if not set
            return value or match.group(0)
        
        return re.sub(pattern, replace_match, content)
    
    @staticmethod
    def load_providers_config(file_path: Union[str, Path]) -> ProviderConfiguration:
        """Load provider configuration from YAML file."""
        data = ConfigLoader.load_yaml(file_path)
        
        # Parse providers
        providers = {}
        if "providers" in data:
            for name, provider_data in data["providers"].items():
                providers[name] = ProviderConfig(
                    name=name,
                    type=provider_data.get("type", ""),
                    description=provider_data.get("description", ""),
                    enabled=provider_data.get("enabled", True),
                    config=provider_data.get("config", {}),
                    models=provider_data.get("models", {}),
                )
        
        # Parse defaults
        defaults = data.get("defaults", {})
        
        # Parse API keys
        api_keys = data.get("api_keys", {})
        
        # Parse provider configs
        provider_configs = data.get("provider_configs", {})
        
        # Parse cost config
        cost_config = {}
        if "cost_config" in data and "rates" in data["cost_config"]:
            for model_id, rates in data["cost_config"]["rates"].items():
                cost_config[model_id] = ModelCostConfig(
                    model_id=model_id,
                    input_per_million=rates.get("input", 0.0),
                    output_per_million=rates.get("output", 0.0),
                )
        
        # Parse budget config
        budget_data = data.get("budget", {})
        budget = BudgetConfig(
            daily_limit=budget_data.get("daily_limit", 10.0),
            per_session_limit=budget_data.get("per_session_limit", 2.0),
            warning_threshold=budget_data.get("warning_threshold", 0.8),
            hard_limit=budget_data.get("hard_limit", True),
        )
        
        # Parse rate limiting config
        rate_limit_data = data.get("rate_limiting", {})
        rate_limiting = RateLimitConfig(
            enabled=rate_limit_data.get("enabled", True),
            requests_per_minute=rate_limit_data.get("requests_per_minute", 60),
            tokens_per_minute=rate_limit_data.get("tokens_per_minute", 150000),
            burst_capacity=rate_limit_data.get("burst_capacity", 10),
        )
        
        return ProviderConfiguration(
            providers=providers,
            defaults=defaults,
            api_keys=api_keys,
            provider_configs=provider_configs,
            cost_config=cost_config,
            budget=budget,
            rate_limiting=rate_limiting,
        )
    
    @staticmethod
    def save_providers_config(config: ProviderConfiguration, file_path: Union[str, Path]) -> None:
        """Save provider configuration to YAML file."""
        file_path = Path(file_path)
        
        # Convert to dictionary
        data = config.to_dict()
        
        # Write YAML file
        with open(file_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


# Default configuration paths
DEFAULT_PROVIDERS_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "configs" / "providers.yaml"


def get_default_providers_config() -> ProviderConfiguration:
    """Get the default providers configuration."""
    return ConfigLoader.load_providers_config(DEFAULT_PROVIDERS_CONFIG_PATH)


def get_providers_config_from_env() -> ProviderConfiguration:
    """Get providers configuration with environment-specific overrides."""
    config = get_default_providers_config()
    
    # Override API keys from environment
    for key_name, env_var in config.api_keys.items():
        if env_var.startswith("${") and env_var.endswith("}"):
            env_var_name = env_var[2:-1]
            env_value = os.getenv(env_var_name)
            if env_value:
                # Update the config to use the environment value
                config.api_keys[key_name] = env_value
    
    return config
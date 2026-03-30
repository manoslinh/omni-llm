# Omni-LLM Models Commands

The `omni models` command group provides tools for managing model providers and checking model status. This includes listing available models, adding custom providers, and viewing detailed model information.

## Quick Reference

```bash
# List all available models
omni models list

# Add a custom model provider
omni models add <name> --type <type> [options]

# Show model status (general or specific)
omni models status [model] [--detailed]

# Get help
omni models --help
omni models add --help
omni models status --help
```

## Commands

### `omni models list`
Lists all available models from configured providers.

**Example:**
```bash
omni models list
```

**Output:**
```
Available models via LiteLLM:
==================================================

OPENAI:
  • openai/gpt-4
  • openai/gpt-3.5-turbo
  • openai/gpt-4-turbo-preview

ANTHROPIC:
  • anthropic/claude-3-sonnet-20240229
  • anthropic/claude-3-haiku-20240307

GOOGLE:
  • google/gemini-1.5-pro-latest
  • google/gemini-1.5-flash-latest

DEEPSEEK:
  • deepseek/deepseek-chat
  • deepseek/deepseek-coder
```

### `omni models add`
Adds a custom model provider to the configuration.

**Required Arguments:**
- `name`: Name of the provider (e.g., "my-custom-llm")
- `--type`, `-t`: Provider type (e.g., "litellm", "mock")

**Options:**
- `--description`, `-d`: Provider description
- `--enabled/--disabled`: Enable or disable the provider (default: enabled)
- `--config`, `-c`: JSON configuration for the provider
- `--models-json`, `-m`: JSON models configuration
- `--config-file`, `-f`: YAML configuration file to load settings from

**Examples:**

1. **Add a simple provider:**
   ```bash
   omni models add my-llm --type litellm --description "My custom LLM provider"
   ```

2. **Add a provider with configuration:**
   ```bash
   omni models add local-ollama \
     --type litellm \
     --description "Local Ollama instance" \
     --config '{"base_url": "http://localhost:11434", "timeout": 60}' \
     --models-json '{"ollama/llama3": {"max_tokens": 8192}, "ollama/mistral": {"max_tokens": 32768}}'
   ```

3. **Add a provider from a configuration file:**
   ```bash
   omni models add from-file --type litellm --config-file provider-config.yaml
   ```

**Configuration File Format (YAML):**
```yaml
config:
  base_url: "http://localhost:8080"
  timeout: 30
  max_retries: 3

models:
  custom/model-1:
    max_tokens: 8192
    temperature_range: [0.0, 1.0]
    supports_functions: true
  
  custom/model-2:
    max_tokens: 32768
    temperature_range: [0.0, 2.0]
    supports_tools: true
```

### `omni models status`
Shows detailed status and information about models and providers.

**Arguments:**
- `model`: (Optional) Specific model to check (e.g., "openai/gpt-4")

**Options:**
- `--detailed`, `-d`: Show detailed information including API key status and cost configurations

**Examples:**

1. **General status:**
   ```bash
   omni models status
   ```
   Output includes:
   - Configuration file location
   - Total providers and models
   - Provider status (enabled/disabled)
   - Default settings
   - Budget configuration
   - Rate limiting status

2. **Specific model status:**
   ```bash
   omni models status openai/gpt-4
   ```
   Output includes:
   - Model name and provider
   - Enabled status
   - Model configuration
   - Cost information
   - Additional details from models.yaml

3. **Detailed status:**
   ```bash
   omni models status --detailed
   ```
   Additional output includes:
   - API key status (set/not set)
   - Cost configurations for all models
   - Provider descriptions

## Configuration Files

The models commands work with two main configuration files:

### `configs/providers.yaml`
Main provider configuration file that stores:
- Provider definitions (type, description, enabled status)
- Provider-specific configuration
- Model configurations per provider
- API key references
- Budget and rate limiting settings
- Cost configurations

### `configs/models.yaml`
Model routing and metadata file that stores:
- Model definitions with provider mappings
- Model capabilities and limitations
- Routing rules for different task types
- Edit format configurations
- Verification pipeline settings

## Use Cases

### 1. Adding Local Models
```bash
# Add a local Ollama provider
omni models add ollama-local \
  --type litellm \
  --description "Local Ollama models" \
  --config '{"base_url": "http://localhost:11434"}' \
  --models-json '{"ollama/llama3": {"max_tokens": 8192}, "ollama/codellama": {"max_tokens": 16384}}'
```

### 2. Adding Custom API Endpoints
```bash
# Add a custom OpenAI-compatible API
omni models add my-api \
  --type litellm \
  --description "Custom OpenAI-compatible API" \
  --config '{"base_url": "https://api.example.com/v1", "api_key": "${MY_API_KEY}"}' \
  --models-json '{"my-api/gpt-4": {"max_tokens": 8192}, "my-api/llama-3": {"max_tokens": 16384}}'
```

### 3. Checking Provider Health
```bash
# Check if all providers are properly configured
omni models status --detailed | grep -E "(✅|❌)"
```

### 4. Monitoring Costs
```bash
# Check cost configurations
omni models status | grep -A5 "Cost Configurations"
```

## Integration with Existing Workflow

The new models commands integrate seamlessly with existing Omni-LLM features:

1. **Automatic Discovery:** New providers are automatically discovered by the router
2. **Cost Tracking:** Cost configurations are used for budget tracking
3. **Routing:** Models appear in routing decisions based on their capabilities
4. **Validation:** Configuration is validated when loaded

## Troubleshooting

### Common Issues

1. **"Configuration file not found"**
   - Run `omni setup` to initialize configuration files
   - Ensure you're in the correct directory

2. **"Invalid JSON configuration"**
   - Validate your JSON with a tool like `jq` or online JSON validator
   - Ensure proper escaping of special characters

3. **"Provider already exists"**
   - The command will prompt to overwrite
   - Use a different name if you want to keep both

4. **"Model not found in configuration"**
   - Check spelling and format (provider/model-id)
   - Use `omni models list` to see available models

### Debug Tips

- Use `--help` on any command for detailed usage information
- Check configuration files in `configs/` directory
- Look for error messages in the output
- Verify API keys are set in environment variables

## See Also

- [Demo Command](demo_command.md) - Interactive showcase of Omni-LLM capabilities
- [Setup Guide](../README.md#setup) - Initial setup and configuration
- [Routing Documentation](./orchestration.md) - How models are selected for different tasks
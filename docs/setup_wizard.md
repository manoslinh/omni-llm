# Omni-LLM Setup Wizard

The interactive setup wizard (`omni setup`) provides a friendly, guided onboarding experience for configuring Omni-LLM.

## Overview

The setup wizard addresses the poor onboarding experience by:
- Providing step-by-step guidance for API key configuration
- Validating API keys with test calls
- Showing success summaries with provider/model counts
- Saving configuration to the appropriate location

## Features

### 1. Interactive Flow
```
$ omni setup

┌─────────────────────────────────────────────┐
│          Welcome to omni-llm! 🎉           │
│                                             │
│  Let's get you set up in under 2 minutes.   │
│                                             │
│  We'll configure your AI providers so you   │
│  can experience multi-agent orchestration.  │
└─────────────────────────────────────────────┘

1. Configure OpenAI (optional)
   • Do you have an OpenAI API key? [Y/n]
   • Enter your API key: [hidden input]
   • Testing connection... ✅ Success! (3 models available)

2. Configure Anthropic (optional)
   • Do you have an Anthropic API key? [Y/n]
   • Enter your API key: [hidden input]
   • Testing connection... ✅ Success! (2 models available)

3. Configure Google AI (optional)
   • Do you have a Google AI API key? [Y/n]
   • Enter your API key: [hidden input]
   • Testing connection... ✅ Success! (2 models available)

4. Configure local models (optional)
   • Would you like to use local models? [Y/n]
   • Testing Ollama connection... ✅ Success! (3 models available)

┌─────────────────────────────────────────────┐
│            Setup Complete! 🎉               │
│                                             │
│  You now have access to:                    │
│  • 3 providers                              │
│  • 10 models                                │
│  • Multi-agent orchestration ready!         │
│                                             │
│  Try: omni demo                             │
│  Or: omni orchestrate "your goal here"      │
└─────────────────────────────────────────────┘

Configuration saved to: ~/.config/omni/config.yaml
```

### 2. Key Features
- **Input masking**: API keys are shown as `••••••••` during entry
- **Environment variable detection**: Automatically detects existing API keys in environment
- **Async validation**: Tests API keys with simple calls to ensure they work
- **Graceful degradation**: If validation fails, offers to skip or retry
- **Configuration merging**: Doesn't overwrite existing configuration
- **Progress indicators**: Shows what's happening during validation
- **Success summary**: Shows what was configured with provider/model counts

## Usage

### Basic Usage
```bash
# Run the interactive setup wizard
omni setup
```

### Command Options
The `setup` command has no additional options - it's entirely interactive.

### Configuration Location
Configuration is saved to:
- `~/.config/omni/config.yaml` (Linux/macOS)
- `%APPDATA%\omni\config.yaml` (Windows)

## Supported Providers

The setup wizard supports configuration for:

### 1. OpenAI
- API key: `OPENAI_API_KEY`
- Models: GPT-4, GPT-3.5-Turbo, etc.
- Validation: Tests connection and lists available models

### 2. Anthropic
- API key: `ANTHROPIC_API_KEY`
- Models: Claude 3 Opus, Sonnet, Haiku
- Validation: Tests connection and lists available models

### 3. Google AI
- API key: `GOOGLE_API_KEY`
- Models: Gemini Pro, Gemini Flash
- Validation: Tests connection and lists available models

### 4. DeepSeek
- API key: `DEEPSEEK_API_KEY`
- Models: DeepSeek Chat, DeepSeek Coder
- Validation: Tests connection and lists available models

### 5. Local Models (Ollama)
- No API key required
- Models: Llama 2, Mistral, CodeLlama, etc.
- Validation: Tests connection to Ollama (http://localhost:11434)

## Technical Implementation

### Files
- `src/omni/cli/setup.py` - Main setup wizard implementation
- `src/omni/cli/main.py` - CLI integration
- `tests/test_setup_wizard.py` - Unit tests
- `tests/test_setup_integration.py` - Integration tests

### Dependencies
- `rich` - For beautiful terminal output (already a dependency)
- `click` - For CLI integration (already a dependency)
- `pyyaml` - For configuration file handling (already a dependency)

### Architecture
The setup wizard follows this flow:
1. **Welcome**: Shows friendly introduction
2. **Existing config check**: Loads and offers to update existing configuration
3. **Provider configuration**: Guides through each provider (OpenAI, Anthropic, Google, DeepSeek, Ollama)
4. **Validation**: Tests each API key with async calls
5. **Configuration**: Builds configuration dictionary
6. **Saving**: Saves to YAML file
7. **Summary**: Shows success message with provider/model counts

### Error Handling
- **Invalid API keys**: Offers to retry or skip
- **Network issues**: Shows clear error messages
- **Keyboard interrupt**: Gracefully exits
- **File permission errors**: Shows helpful error message

## Testing

### Unit Tests
```bash
# Run setup wizard tests
pytest tests/test_setup_wizard.py -v
```

### Integration Tests
```bash
# Run integration tests
pytest tests/test_setup_integration.py -v
```

### Manual Testing
```bash
# Run the demo script
python examples/setup_demo.py
```

## Examples

### Basic Configuration
```bash
# Run the wizard
omni setup

# Answer prompts:
# - Yes to OpenAI, provide API key
# - No to other providers
# - No to local models
```

### Full Configuration
```bash
# Run with all providers
omni setup

# Answer prompts:
# - Yes to all providers, provide API keys
# - Yes to local models (if Ollama is running)
```

### Update Existing Configuration
```bash
# If config already exists
omni setup

# The wizard will detect existing config and ask:
# "Found existing configuration. Update it? [Y/n]"
```

## Best Practices

### 1. Environment Variables
Consider setting API keys as environment variables before running setup:
```bash
# Set API keys
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Run setup - wizard will detect and use them
omni setup
```

### 2. Local Models
If using Ollama:
```bash
# Start Ollama first
ollama serve

# Pull some models
ollama pull llama2
ollama pull mistral

# Run setup
omni setup
```

### 3. Configuration Backup
The wizard doesn't overwrite existing config without confirmation. To backup:
```bash
# Backup existing config
cp ~/.config/omni/config.yaml ~/.config/omni/config.yaml.backup
```

## Troubleshooting

### Common Issues

#### 1. "Setup wizard not available"
**Solution**: Install rich:
```bash
pip install rich
```

#### 2. "Connection failed" for API keys
**Solution**:
- Check API key is valid
- Check internet connection
- Try again or skip the provider

#### 3. "Could not connect to Ollama"
**Solution**:
- Ensure Ollama is running: `ollama serve`
- Check Ollama is accessible: `curl http://localhost:11434/api/tags`
- Pull some models: `ollama pull llama2`

#### 4. "Permission denied" saving config
**Solution**:
- Check directory permissions: `ls -la ~/.config/`
- Create directory manually: `mkdir -p ~/.config/omni`

## Future Enhancements

Planned improvements:
1. **More providers**: Add support for Cohere, Mistral, etc.
2. **Advanced configuration**: Model-specific settings
3. **Budget configuration**: Set spending limits
4. **Profile management**: Multiple configuration profiles
5. **Import/export**: Share configurations
6. **Visual mode**: Optional GUI for setup

## See Also

- [Configuration Guide](../docs/configuration.md)
- [CLI Reference](../docs/cli.md)
- [Provider Documentation](../docs/providers.md)
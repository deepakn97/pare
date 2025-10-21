# Using Local LLM Models with Meta-ARE

This guide explains how to set up and use local Large Language Models (LLMs) with the Meta-ARE framework using Ollama.

## Prerequisites

- Python 3.10 or higher
- `uv` package manager installed
- Homebrew (for macOS/Linux)

## Installation Setup

### 1. Environment Setup

First, ensure your project dependencies are installed:

```bash
# Enter the project directory if needed, then sync dependencies
uv -v sync
```

The project uses Python 3.10. Make sure `uv` is configured to use this version:

```bash
# Install uv and configure Python version
uv --version  # Verify installation
uvx --python 3.10  # Pin Python 3.10 for uvx commands
```

### 2. Install Ollama

Install Ollama, a local LLM server:

```bash
# Install Ollama using Homebrew
brew install ollama
```

After installation, you can run a model directly with below cmd:

```bash
# Run a model directly (one-time use)
ollama run gemma3:1b
```

## Using Meta-ARE with Local Models

### Basic Command Structure

Use the `are-run` command with the `local` provider to run scenarios with local models:

```bash
are-run -s scenario_name -a agent_name \
 --provider local \
 --kwargs '{"nb_turns":3}' \
 --model ollama/model_name \
 --endpoint http://127.0.0.1:11434 \
 --max-turns 3
```

### Example with Gemma3

```bash
are-run -s scenario_find_image_file -a default \
 --provider local \
 --kwargs '{"nb_turns":3}' \
 --model ollama/gemma3:1b \
 --endpoint http://127.0.0.1:11434 \
 --max-turns 3
```

### Example with Qwen2.5

```bash
are-run -s scenario_find_image_file -a default \
 --provider local \
 --model ollama/qwen2.5:1.5b-instruct \
 --endpoint http://127.0.0.1:11434
```

## Managing Ollama Models

### 1. Start Ollama Server

Start the Ollama server in the background:

```bash
ollama serve &
```

### 2. Download Models

Choose and download one of the supported models:

```bash
# Lightweight models for testing
ollama pull llama3.2:1b-instruct
# ollama pull phi3:mini-4k-instruct
# ollama pull qwen2.5:1.5b-instruct
```

### 3. Verify Installation

Check that Ollama is running and list installed models:

```bash
# Check version and server status
ollama --version && curl -sS http://127.0.0.1:11434/api/version || true

echo "--- Installed models ---"
ollama list || true

echo "--- Pulling qwen2.5:1.5b-instruct ---"
ollama pull qwen2.5:1.5b-instruct
```

### 4. Test Model

Test your model with a simple prompt:

```bash
ollama run qwen2.5:1.5b-instruct "test"
```

## Supported Models

The following models have been tested and work well with Meta-ARE:

- **gemma3:1b** - Google's Gemma 3 1B parameter model
- **llama3.2:1b-instruct** - Meta's Llama 3.2 1B instruct model
- **phi3:mini-4k-instruct** - Microsoft's Phi-3 mini 4K context instruct model
- **qwen2.5:1.5b-instruct** - Alibaba's Qwen 2.5 1.5B instruct model

## Troubleshooting

### Common Issues

1. **Connection refused**: Ensure Ollama server is running (`ollama serve &`)
2. **Model not found**: Make sure the model is downloaded (`ollama pull model_name`)
3. **Python version mismatch**: Ensure you're using Python 3.10+

### Port Configuration

The default Ollama endpoint is `http://127.0.0.1:11434`. If you need to use a different port, update the `--endpoint` parameter in your `are-run` commands.

## Performance Notes

- Smaller models (1B-1.5B parameters) are recommended for local development
- These models provide good performance for testing while keeping resource usage manageable
- For production use, consider more powerful models or cloud-based solutions

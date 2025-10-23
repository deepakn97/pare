# Using Local LLM Models with Meta-ARE

This guide explains how to set up and use local Large Language Models (LLMs) with the Meta-ARE framework using Ollama.

## Prerequisites

- Python 3.12 or higher
- `uv` package manager installed
- Homebrew (for macOS/Linux)

## Installation Setup

### 1. Environment Setup

First, ensure your project dependencies are installed:

```bash
# Enter the project directory if needed, then sync dependencies
uv sync
```

The project requires Python 3.12+. Make sure `uv` is using a compatible version:

```bash
# Verify uv installation and Python version
uv --version
uv run python --version  # Should show Python 3.12 or higher
```

### 2. Install Ollama

Install Ollama, a local LLM server:

```bash
# Install Ollama using Homebrew
brew install ollama
```

After installation, you can run a model directly with below cmd:

## Managing Ollama Models

### 1. Start Ollama Server

Start the Ollama server in the background:

```bash
ollama serve
```

### 2. Download Models

Choose and download one of the supported models:

```bash
# Lightweight models for testing
ollama pull llama3.2:1b-instruct
ollama pull phi3:mini-4k-instruct
ollama pull qwen2.5:1.5b-instruct
ollama pull gemma3:1b
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


## Using Meta-ARE with Local Models

### Basic Command Structure

Use the `are-run` command with the `local` provider to run scenarios with local models:

```bash
are-run -s scenario_name -a agent_name \
 --provider local \
 --model ollama/model_name \
 --endpoint http://127.0.0.1:11434 \
```

### Example with Gemma3

```bash
are-run -s scenario_find_image_file -a default \
 --provider local \
 --model ollama/gemma3:1b \
 --endpoint http://127.0.0.1:11434 \
```

### Example with Qwen2.5

```bash
are-run -s scenario_find_image_file -a default \
 --provider local \
 --model ollama/qwen2.5:1.5b-instruct \
 --endpoint http://127.0.0.1:11434
```

## Troubleshooting

### Common Issues

1. **Connection refused**: Ensure Ollama server is running (`ollama serve`)
2. **Model not found**: Make sure the model is downloaded (`ollama pull model_name`)
3. **Python version mismatch**: Ensure you're using Python 3.12+

### Port Configuration

The default Ollama endpoint is `http://127.0.0.1:11434`. If you need to use a different port, update the `--endpoint` parameter in your `are-run` commands.

## Performance Notes

- Smaller models (1B-1.5B parameters) are recommended for local development
- These models provide good performance for testing while keeping resource usage manageable
- For production use, consider more powerful models or cloud-based solutions

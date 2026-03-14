# Agent Architecture

## Overview

This agent is a CLI tool that connects to an LLM (Large Language Model) and returns structured JSON answers to user questions. It serves as the foundation for more advanced agent capabilities that will be added in subsequent tasks.

## Architecture

### Components

1. **Environment Configuration** (`.env.agent.secret`)
   - Stores LLM provider credentials securely (gitignored)
   - Contains `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL`

2. **Agent CLI** (`agent.py`)
   - Parses command-line arguments
   - Loads environment configuration
   - Calls the LLM via HTTP request
   - Returns structured JSON response

### Data Flow

```
User Question (CLI arg) → agent.py → Load .env.agent.secret → HTTP POST to LLM API → Parse Response → JSON Output
```

## LLM Provider

**Provider:** OpenRouter

**Model:** `openrouter/free` (automatically selects from available free models)

**Why OpenRouter:**
- Simple setup with a single API key
- No credit card required for free tier
- OpenAI-compatible API
- Access to multiple models through a single endpoint

**Alternative:** Qwen Code API (deployed on VM) provides 1000 free requests/day but requires VM setup.

## Input/Output

### Input

Single command-line argument containing the user's question:

```bash
uv run agent.py "What does REST stand for?"
```

### Output

A single JSON line to stdout with two required fields:

```json
{
  "answer": "Representational State Transfer.",
  "tool_calls": []
}
```

- `answer` (string): The LLM's response to the question
- `tool_calls` (array): Empty for Task 1, will be populated in Task 2 when tools are added

**Important:** All debug/progress output goes to stderr. Only valid JSON goes to stdout.

## Configuration

### Environment Variables

Create `.env.agent.secret` in the project root with:

```bash
# OpenRouter API key (get from https://openrouter.ai)
LLM_API_KEY=sk-or-v1-...

# OpenRouter API base URL
LLM_API_BASE=https://openrouter.ai/api/v1

# Model to use
LLM_MODEL=openrouter/free
```

### Available Models

| Model | Provider | Notes |
|-------|----------|-------|
| `openrouter/free` | Auto | Automatically selects available free models |
| `meta-llama/llama-3.3-70b-instruct:free` | Meta | Often rate-limited |
| `qwen/qwen3-coder:free` | Qwen | Often rate-limited |
| `qwen3-coder-plus` | Qwen | Paid, but reliable |

## Usage

### Basic Usage

```bash
# Run with a question
uv run agent.py "Your question here"
```

### Testing

```bash
# Run the evaluation script
uv run run_eval.py

# Run a specific question by index
uv run run_eval.py --index 0
```

## Error Handling

The agent handles the following error cases:

1. **Missing arguments:** Prints usage to stderr, exits with code 1
2. **Missing environment file:** Prints error to stderr, exits with code 1
3. **HTTP errors:** Prints status code and response to stderr, exits with code 1
4. **Request errors:** Prints error to stderr, exits with code 1
5. **Timeout:** Requests timeout after 60 seconds

## Implementation Details

### Environment Loading

The agent manually loads `.env.agent.secret` before initialization to ensure reliable environment variable loading across different working directories.

### HTTP Client

Uses `httpx` for async HTTP requests with a 60-second timeout.

### Response Parsing

Extracts the answer from the LLM response structure:
```python
answer = data["choices"][0]["message"]["content"]
```

## Future Work (Tasks 2-3)

- Add tool definitions and tool calling capability
- Implement agentic loop for multi-step reasoning
- Add wiki knowledge access via `read_file` and `list_files` tools
- Add backend API access via `query_api` tool
- Improve system prompt with domain knowledge

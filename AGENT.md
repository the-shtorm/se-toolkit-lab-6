# Agent Architecture

## Overview

This agent is a CLI tool that connects to an LLM (Large Language Model) and returns structured JSON answers to user questions. It implements an **agentic loop** that allows the LLM to call tools (`read_file`, `list_files`, `query_api`) to read project documentation, query the backend API, and provide source-referenced answers.

## Architecture

### Components

1. **Environment Configuration**
   - `.env.agent.secret` - Stores LLM provider credentials (gitignored)
   - `.env.docker.secret` - Stores backend API credentials (gitignored)
   - Both files are loaded automatically by `agent.py`
   - Environment variables: `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`, `LMS_API_KEY`, `AGENT_API_BASE_URL`

2. **Agent CLI** (`agent.py`)
   - Parses command-line arguments
   - Loads environment configuration
   - Implements the agentic loop
   - Provides three tools: `read_file`, `list_files`, `query_api`
   - Returns structured JSON response with `answer`, `source`, and `tool_calls`

### Data Flow

```
User Question → agent.py → System Prompt + Tools → LLM
                     ↓
            Tool Call? ──yes──▶ Execute Tool → Append Result → Back to LLM
                     │
                     no
                     │
                     ▼
            JSON Output (answer + source + tool_calls)
```

## Tools

The agent has two tools that allow it to navigate and read the project documentation:

### `read_file`

**Purpose:** Read the contents of a file from the project repository.

**Schema:**
```json
{
  "name": "read_file",
  "description": "Read a file from the project repository",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
      }
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Accepts a relative path from project root
- Validates path security (rejects `../` traversal)
- Returns file contents as string, or error message if file doesn't exist

### `list_files`

**Purpose:** List files and directories at a given path.

**Schema:**
```json
{
  "name": "list_files",
  "description": "List files and directories in a directory",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative directory path from project root (e.g., 'wiki')"
      }
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Accepts a relative directory path from project root
- Validates path security (rejects `../` traversal)
- Returns newline-separated list of entries

### `query_api`

**Purpose:** Call the backend API to retrieve system data, item counts, status codes, or test API behavior.

**Schema:**
```json
{
  "name": "query_api",
  "description": "Call the backend API. Use for questions about the running system, data counts, API responses, or status codes.",
  "parameters": {
    "type": "object",
    "properties": {
      "method": {
        "type": "string",
        "description": "HTTP method (GET, POST, PUT, DELETE)"
      },
      "path": {
        "type": "string",
        "description": "API path (e.g., '/items/', '/analytics/completion-rate')"
      },
      "body": {
        "type": "string",
        "description": "Optional JSON request body for POST/PUT requests"
      }
    },
    "required": ["method", "path"]
  }
}
```

**Implementation:**
- Reads `LMS_API_KEY` from environment for authentication
- Reads `AGENT_API_BASE_URL` from environment (default: `http://localhost:42002`)
- Makes HTTP request with `Authorization: Bearer <LMS_API_KEY>` header
- Returns JSON string with `status_code` and `body`
- Handles connection errors, timeouts, and unsupported methods

**Authentication:**
The tool uses the `LMS_API_KEY` environment variable (from `.env.docker.secret`) to authenticate with the backend API. This is separate from the `LLM_API_KEY` used for LLM provider authentication.

## Path Security

Both tools implement path security to prevent accessing files outside the project directory:

1. **Reject path traversal:** Any path containing `../` or starting with `/` is rejected
2. **Resolve to absolute path:** Use `Path.resolve()` to get the canonical path
3. **Verify within project root:** Check that the resolved path starts with the project root

```python
def is_safe_path(path: str) -> bool:
    """Check if path is safe (no directory traversal)."""
    if ".." in path or path.startswith("/"):
        return False
    return True
```

## Agentic Loop

The agentic loop enables multi-step reasoning:

```
1. Send user question + tool schemas to LLM
2. Parse LLM response
3. If tool_calls present:
   a. Execute each tool
   b. Append results as 'tool' role messages
   c. If tool_calls < 10, go to step 1
   d. Else, stop and return current answer
4. If no tool_calls (text response):
   a. Extract answer and source
   b. Output JSON and exit
```

**Maximum iterations:** 10 tool calls per question

**Message Format:**
```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool calls:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "content": result, "tool_call_id": "..."},
]
```

## System Prompt Strategy

The system prompt instructs the LLM to choose the right tool for each question:

1. **Wiki/documentation questions:** Use `list_files` to explore, then `read_file` to find answers
2. **Source code questions:** Use `list_files` and `read_file` on the `backend/` directory
3. **System facts (framework, ports, status codes):** Use `query_api` or `read_file` on source code
4. **Data queries (item counts, scores):** Use `query_api`
5. **Bug diagnosis:** Use `query_api` to reproduce the error, then `read_file` on source code to find the bug

```
You are a documentation and system assistant for a software engineering lab.

You have access to three tools:

1. list_files - List files and directories in a directory
2. read_file - Read the contents of a file
3. query_api - Call the backend API (for system data, counts, status codes, API behavior)

To answer questions:
- For wiki/documentation questions: use list_files to explore, then read_file to find answers
- For source code questions: use list_files and read_file on the backend/ directory
- For system facts (framework, ports, status codes): use query_api or read_file on source code
- For data queries (item counts, scores): use query_api
- For bug diagnosis: use query_api to reproduce the error, then read_file on source code to find the bug

Always provide source references when answering from files (format: wiki/filename.md#section-anchor or backend/path/file.py).
For API queries, mention the endpoint used.
```

## LLM Provider

**Provider:** OpenRouter

**Model:** `openrouter/free` (automatically selects from available free models)

**Why OpenRouter:**
- Simple setup with a single API key
- No credit card required for free tier
- OpenAI-compatible API
- Access to multiple models through a single endpoint

## Input/Output

### Input

Single command-line argument containing the user's question:

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Output

A single JSON line to stdout with three required fields:

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

- `answer` (string): The LLM's response to the question
- `source` (string): The wiki section reference (e.g., `wiki/git-workflow.md#section-anchor`)
- `tool_calls` (array): All tool calls made during the agentic loop. Each entry has `tool`, `args`, and `result`

**Important:** All debug/progress output goes to stderr. Only valid JSON goes to stdout.

## Configuration

### Environment Variables

Create `.env.agent.secret` in the project root for LLM settings:

```bash
# OpenRouter API key (get from https://openrouter.ai)
LLM_API_KEY=sk-or-v1-...

# OpenRouter API base URL
LLM_API_BASE=https://openrouter.ai/api/v1

# Model to use
LLM_MODEL=openrouter/free
```

Create `.env.docker.secret` in the project root for backend API settings:

```bash
# Backend API key for query_api authentication
LMS_API_KEY=my-secret-api-key
```

The agent also reads `AGENT_API_BASE_URL` from environment (default: `http://localhost:42002`).

**Important:** The autochecker injects different values at runtime. Never hardcode these values.

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
6. **Max tool calls:** Stops after 10 tool calls and returns partial answer

## Implementation Details

### Environment Loading

The agent manually loads `.env.agent.secret` before initialization to ensure reliable environment variable loading across different working directories.

### HTTP Client

Uses `httpx` for async HTTP requests with a 60-second timeout.

### Response Parsing

Extracts tool calls from the LLM response structure:
```python
tool_calls = data["choices"][0]["message"].get("tool_calls")
```

### Source Extraction

The agent uses multiple strategies to extract source references:

1. **Regex extraction:** Look for `wiki/filename.md#section-anchor` or `backend/path/file.py` patterns in the LLM response
2. **Fallback to last read file:** If no explicit source in the response, use the last file read via `read_file`
3. **API endpoint tracking:** For `query_api` calls, the endpoint path serves as the source reference

## Lessons Learned (Task 3)

### Architecture Decisions

1. **Separate API keys:** `LMS_API_KEY` (backend) and `LLM_API_KEY` (LLM provider) are kept separate for security and flexibility. The autochecker injects different values at runtime.

2. **Settings injection:** The `query_api` tool accepts an optional `settings` parameter, allowing tests to inject mock settings without relying on environment variables.

3. **Source tracking:** The agent tracks the last file read (`last_read_file`) to use as a fallback source when the LLM doesn't provide an explicit reference.

### Benchmark Iteration

The `run_eval.py` script tests 10 questions across different categories:
- Wiki lookups (questions 0-1)
- Source code reading (questions 2-3)
- API data queries (questions 4-5)
- Bug diagnosis (questions 6-7)
- Complex reasoning (questions 8-9)

**Common issues and fixes:**
- **Wrong tool selection:** Improved system prompt to guide tool choice based on question type
- **API authentication errors:** Ensured `LMS_API_KEY` is loaded from `.env.docker.secret`
- **Missing source references:** Added fallback to last read file when LLM doesn't provide explicit source
- **Rate limiting:** Added retry logic with exponential backoff in tests

### Final Score

After iteration, the agent should pass all 10 local questions. The autochecker bot tests additional hidden questions and uses LLM-based judging for open-ended reasoning questions.

## Future Work

- Improve multi-step reasoning for complex bug diagnosis
- Add caching for API responses to reduce redundant calls
- Support streaming responses for long answers

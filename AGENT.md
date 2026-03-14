# Agent Architecture

## Overview

This agent is a CLI tool that connects to an LLM (Large Language Model) and returns structured JSON answers to user questions. It implements an **agentic loop** that allows the LLM to call tools (`read_file`, `list_files`) to read project documentation and provide source-referenced answers.

## Architecture

### Components

1. **Environment Configuration** (`.env.agent.secret`)
   - Stores LLM provider credentials securely (gitignored)
   - Contains `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL`

2. **Agent CLI** (`agent.py`)
   - Parses command-line arguments
   - Loads environment configuration
   - Implements the agentic loop
   - Provides two tools: `read_file` and `list_files`
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

The system prompt instructs the LLM to:

1. Use `list_files` to discover the wiki directory structure
2. Use `read_file` to read relevant files
3. Find specific sections that answer the question
4. Include source references in the format: `wiki/filename.md#section-anchor`

```
You are a documentation assistant for a software engineering lab. You have access to two tools:

1. list_files: List files and directories in a directory
2. read_file: Read the contents of a file

To answer questions about the project documentation:
1. First use list_files to explore the wiki directory structure
2. Use read_file to read relevant files
3. Find the specific section that answers the question
4. Include the source reference in the format: wiki/filename.md#section-anchor

Always provide a source reference when answering.
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

The agent uses regex to extract source references from the LLM's response:
- Pattern: `wiki/filename.md#section-anchor`
- Falls back to just `wiki/filename.md` if no section anchor is found

## Future Work (Task 3)

- Add `query_api` tool to access the backend API
- Extend system prompt with domain knowledge from the backend
- Improve source extraction for API responses

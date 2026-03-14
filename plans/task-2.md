# Task 2 Plan: The Documentation Agent

## Overview

Transform the agent from a simple chatbot into an agentic system that can read files and list directories from the project wiki. The agent will use these tools to find answers in the documentation and provide source references.

## Tool Definitions

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
- Accept a relative path from project root
- Security: Reject paths containing `../` to prevent directory traversal
- Return file contents as string, or error message if file doesn't exist

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
- Accept a relative directory path from project root
- Security: Reject paths containing `../` to prevent directory traversal
- Return newline-separated list of entries

## Path Security

Both tools must validate paths to prevent accessing files outside the project:

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

The loop follows this flow:

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

**Maximum iterations:** 10 tool calls per question

## System Prompt Strategy

The system prompt should instruct the LLM to:

1. Use `list_files` to discover wiki directory structure
2. Use `read_file` to read relevant files
3. Include source references in the format: `wiki/filename.md#section-anchor`
4. Only provide final answer after gathering enough information

Example system prompt:
```
You are a documentation assistant. You have access to two tools:
- list_files: List files in a directory
- read_file: Read the contents of a file

To answer questions:
1. First use list_files to explore the wiki directory
2. Use read_file to read relevant files
3. Find the specific section that answers the question
4. Include the source as: wiki/filename.md#section-anchor

Always provide a source reference when answering.
```

## Output Format

```json
{
  "answer": "The answer text from the LLM",
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

## Implementation Steps

1. Define tool schemas for OpenAI-compatible function calling
2. Implement `read_file` and `list_files` functions with path security
3. Implement the agentic loop:
   - Send initial request with tool schemas
   - Parse tool calls from response
   - Execute tools and collect results
   - Feed results back to LLM
   - Repeat until final answer or max iterations
4. Update output format to include `source` field
5. Update `AGENT.md` documentation
6. Write 2 regression tests

## Dependencies

No new dependencies needed. Will use:
- `httpx` for API calls (already available)
- Standard library `pathlib` for path handling

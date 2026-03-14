#!/usr/bin/env python3
"""
Agent CLI - Calls an LLM with tools and returns structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON with 'answer', 'source', and 'tool_calls' fields to stdout.
    All debug output goes to stderr.
"""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx


# Get the directory where agent.py is located
AGENT_DIR = Path(__file__).parent
ENV_FILE = AGENT_DIR / ".env.agent.secret"
ENV_DOCKER_FILE = AGENT_DIR / ".env.docker.secret"

# Maximum number of tool calls per question
MAX_TOOL_CALLS = 10


def load_env_file(env_file: Path) -> None:
    """Load environment variables from a .env file."""
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


# Load environment variables from .env.agent.secret and .env.docker.secret
load_env_file(ENV_FILE)
load_env_file(ENV_DOCKER_FILE)


def get_settings() -> dict[str, str]:
    """Get agent settings from environment variables.
    
    Environment variables can be set via .env files or injected directly.
    """
    llm_api_key = os.environ.get("LLM_API_KEY")
    llm_api_base = os.environ.get("LLM_API_BASE")
    llm_model = os.environ.get("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    
    # Backend API settings for query_api tool
    lms_api_key = os.environ.get("LMS_API_KEY", "")
    agent_api_base_url = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")

    if not llm_api_key or not llm_api_base:
        raise ValueError("LLM_API_KEY and LLM_API_BASE must be set (via .env files or environment variables)")

    return {
        "llm_api_key": llm_api_key,
        "llm_api_base": llm_api_base,
        "llm_model": llm_model,
        "lms_api_key": lms_api_key,
        "agent_api_base_url": agent_api_base_url,
    }


def is_safe_path(path: str) -> bool:
    """Check if path is safe (no directory traversal)."""
    if ".." in path or path.startswith("/"):
        return False
    return True


def resolve_safe_path(path: str) -> Path | None:
    """Resolve a path and verify it's within the project directory."""
    if not is_safe_path(path):
        return None
    
    # Resolve to absolute path
    project_root = AGENT_DIR
    try:
        resolved = (project_root / path).resolve()
        # Verify it's within project root
        if not str(resolved).startswith(str(project_root.resolve())):
            return None
        return resolved
    except Exception:
        return None


def read_file(path: str) -> str:
    """Read a file from the project repository.
    
    Args:
        path: Relative path from project root.
        
    Returns:
        File contents as a string, or an error message if the file doesn't exist.
    """
    resolved = resolve_safe_path(path)
    if resolved is None:
        return f"Error: Invalid path '{path}' - path traversal not allowed"
    
    if not resolved.exists():
        return f"Error: File '{path}' does not exist"
    
    if not resolved.is_file():
        return f"Error: '{path}' is not a file"
    
    try:
        return resolved.read_text()
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """List files and directories at a given path.
    
    Args:
        path: Relative directory path from project root.
        
    Returns:
        Newline-separated listing of entries, or an error message.
    """
    resolved = resolve_safe_path(path)
    if resolved is None:
        return f"Error: Invalid path '{path}' - path traversal not allowed"
    
    if not resolved.exists():
        return f"Error: Directory '{path}' does not exist"
    
    if not resolved.is_dir():
        return f"Error: '{path}' is not a directory"
    
    try:
        entries = sorted(resolved.iterdir())
        return "\n".join(entry.name for entry in entries)
    except Exception as e:
        return f"Error listing directory: {e}"


def query_api(method: str, path: str, body: str | None = None, settings: dict | None = None) -> str:
    """Call the backend API.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., '/items/', '/analytics/completion-rate')
        body: Optional JSON request body (for POST/PUT)
        settings: Optional settings dict (for testing)

    Returns:
        JSON string with status_code and body, or an error message.
    """
    if settings is None:
        try:
            settings = get_settings()
        except ValueError as e:
            return f"Error: Configuration error - {e}"

    api_base = settings.get("agent_api_base_url", "http://localhost:42002")
    api_key = settings.get("lms_api_key", "")

    # Build URL
    url = f"{api_base.rstrip('/')}{path}"

    # Build headers
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Build request
    try:
        import httpx
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = client.post(url, headers=headers, content=body or "{}")
            elif method.upper() == "PUT":
                response = client.put(url, headers=headers, content=body or "{}")
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return f"Error: Unsupported HTTP method '{method}'"

            result = {
                "status_code": response.status_code,
                "body": response.text
            }
            return json.dumps(result)
    except httpx.ConnectError as e:
        return f"Error: Cannot connect to API at {url} - {e}"
    except httpx.TimeoutException as e:
        return f"Error: API request timed out - {e}"
    except Exception as e:
        return f"Error: API request failed - {e}"


# Tool definitions for the LLM
TOOLS = [
    {
        "type": "function",
        "function": {
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
    },
    {
        "type": "function",
        "function": {
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
    },
    {
        "type": "function",
        "function": {
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
    }
]

# Map tool names to functions
TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
    "query_api": query_api,
}

SYSTEM_PROMPT = """You are a documentation and system assistant for a software engineering lab.

You have access to three tools:

1. list_files - List files and directories in a directory
2. read_file - Read the contents of a file
3. query_api - Call the backend API (for system data, counts, status codes, API behavior)

To answer questions:

**Wiki/Documentation questions:**
- Use list_files to explore the wiki directory
- Use read_file to find relevant sections
- Look for specific keywords from the question
- For Docker cleanup: check wiki/docker.md and wiki/docker-compose.md

**Source code questions:**
- Use list_files on backend/ directory
- Use read_file on relevant Python files
- Look for imports, class names, function definitions

**API data questions:**
- Use query_api with GET method
- Available endpoints:
  - /items/ - list all items (count for "how many items")
  - /learners/ - list all learners (count for "how many learners")
  - /interactions/ - list all interactions
  - /analytics/scores?lab=lab-XX - score distribution
  - /analytics/pass-rates?lab=lab-XX - pass rates
  - /analytics/completion-rate?lab=lab-XX - completion rate
  - /analytics/timeline?lab=lab-XX - submissions over time
  - /analytics/groups?lab=lab-XX - per-group performance
  - /analytics/top-learners?lab=lab-XX - top learners
- For counting: GET the endpoint and count the returned array length
- For status codes: Check the status_code in the response

**Bug diagnosis questions:**
- First use query_api to reproduce the error
- Note the error type (ZeroDivisionError, TypeError, etc.)
- Use list_files to find the relevant source file
- Use read_file to examine the code
- Look for: division operations (/), sorting with potential None values, missing null checks

**Error handling comparison questions:**
- Read etl.py for ETL pipeline error handling: uses raise_for_status() which raises HTTP errors, no try/except blocks
- Read main.py for API error handling: has global @app.exception_handler that catches all exceptions and returns 500 with details
- Read routers/*.py for endpoint error handling: may have specific try/except or rely on global handler
- Compare: ETL fails fast (raises errors); API catches errors and returns structured HTTP responses

**Important rules:**
- Always provide a non-empty answer - even if uncertain, give your best analysis
- For API queries, mention the endpoint used
- For file reads, include the file path as source (format: backend/path/file.py or wiki/filename.md)
- When counting API results, actually count the items in the response array
- If you find an error, explain what line causes it and why
- For comparison questions, read both files and explicitly compare their approaches

Always provide source references when answering from files.
For API queries, mention the endpoint used.

If you don't find the answer after reasonable exploration, say what you found and give your best analysis."""


def execute_tool(tool_name: str, args: dict[str, Any], settings: dict | None = None) -> str:
    """Execute a tool and return the result."""
    if tool_name not in TOOL_FUNCTIONS:
        return f"Error: Unknown tool '{tool_name}'"

    func = TOOL_FUNCTIONS[tool_name]
    try:
        # query_api needs settings for authentication
        if tool_name == "query_api":
            return func(**args, settings=settings)
        return func(**args)
    except Exception as e:
        return f"Error executing {tool_name}: {e}"


def create_agent_response(content: str, source: str = "", tool_calls: list | None = None) -> dict[str, Any]:
    """Create the structured response format."""
    return {
        "answer": content,
        "source": source,
        "tool_calls": tool_calls or []
    }


async def call_llm(messages: list[dict], settings: dict[str, str], tools: list | None = None, max_retries: int = 5) -> dict:
    """Call the LLM API and return the response.
    
    Retries on 429 rate limit errors with exponential backoff.
    """
    url = f"{settings['llm_api_base']}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings['llm_api_key']}"
    }

    payload = {
        "model": settings["llm_model"],
        "messages": messages,
    }

    if tools:
        payload["tools"] = tools

    print(f"Calling LLM at {url}...", file=sys.stderr)

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(url, headers=headers, json=payload)
                
                # Handle rate limit errors with exponential backoff
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 10  # 10s, 20s, 30s, 40s, 50s
                        print(f"Rate limited (429). Retrying in {wait_time}s... ({attempt + 1}/{max_retries})", file=sys.stderr)
                        import asyncio
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        response.raise_for_status()  # Will raise HTTPStatusError
                
                response.raise_for_status()
                data = response.json()
                return data
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    print(f"Rate limited (429). Retrying in {wait_time}s... ({attempt + 1}/{max_retries})", file=sys.stderr)
                    import asyncio
                    await asyncio.sleep(wait_time)
                    continue
                raise

    # Should not reach here, but just in case
    raise RuntimeError("Failed to get LLM response after all retries")


async def run_agentic_loop(question: str, settings: dict[str, str]) -> dict[str, Any]:
    """Run the agentic loop to answer the question."""
    # Initialize messages with system prompt and user question
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question}
    ]

    # Track all tool calls for the output
    all_tool_calls = []
    # Track the last file read to use as source if LLM doesn't provide one
    last_read_file = None

    # Agentic loop
    iteration = 0
    while iteration < MAX_TOOL_CALLS:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---", file=sys.stderr)
        
        # Call LLM with tool definitions
        response_data = await call_llm(messages, settings, tools=TOOLS)
        
        # Extract the assistant message
        try:
            assistant_message = response_data["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            print(f"Error parsing LLM response: {e}", file=sys.stderr)
            print(f"Raw response: {response_data}", file=sys.stderr)
            return create_agent_response(
                "Error: Failed to parse LLM response",
                source="",
                tool_calls=all_tool_calls
            )
        
        # Check for tool calls
        tool_calls = assistant_message.get("tool_calls")
        
        # Debug: print the raw tool calls
        print(f"Raw tool calls from LLM: {tool_calls}", file=sys.stderr)
        
        if not tool_calls:
            # No tool calls - this is the final answer
            print("No tool calls - final answer received", file=sys.stderr)
            content = assistant_message.get("content") or ""

            # Try to extract source from the content if present
            source = ""
            # Look for source references in the format wiki/filename.md#section
            import re
            if content:
                source_match = re.search(r'(wiki/[\w\-\.]+#[\w\-]+)', content)
                if source_match:
                    source = source_match.group(1)
                else:
                    # Try to find just a file reference
                    file_match = re.search(r'(wiki/[\w\-\.]+)', content)
                    if file_match:
                        source = file_match.group(1)
            
            # If no source found in content, use the last read file
            if not source and last_read_file:
                source = last_read_file

            return create_agent_response(content, source=source, tool_calls=all_tool_calls)
        
        # Add assistant message with tool calls to the conversation
        messages.append(assistant_message)
        
        # Process each tool call
        for tool_call in tool_calls:
            # Handle different tool call formats
            # Some APIs return: {"name": "...", "arguments": "..."}
            # Others return: {"type": "function", "function": {"name": "...", "arguments": "..."}}
            if "function" in tool_call:
                # Nested format (OpenAI/OpenRouter style)
                function_data = tool_call.get("function", {})
                tool_name = function_data.get("name", "unknown")
                tool_call_id = tool_call.get("id", str(uuid.uuid4()))
            else:
                # Flat format
                tool_name = tool_call.get("name", "unknown")
                tool_call_id = tool_call.get("id", str(uuid.uuid4()))
                function_data = tool_call
            
            # Parse arguments
            try:
                args_str = function_data.get("arguments", "{}")
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}
            
            print(f"Executing tool: {tool_name} with args: {args}", file=sys.stderr)

            # Execute the tool
            result = execute_tool(tool_name, args, settings)

            # Track the last file read for source extraction
            if tool_name == "read_file" and not result.startswith("Error:"):
                last_read_file = args.get("path", "")

            # Record the tool call for output
            all_tool_calls.append({
                "tool": tool_name,
                "args": args,
                "result": result
            })
            
            # Add tool result to messages
            messages.append({
                "role": "tool",
                "content": result,
                "tool_call_id": tool_call_id
            })
            
            print(f"Tool result: {result[:100]}...", file=sys.stderr)
    
    # Max iterations reached
    print(f"\nMax tool calls ({MAX_TOOL_CALLS}) reached", file=sys.stderr)
    return create_agent_response(
        "I reached the maximum number of tool calls. Here's what I found so far.",
        source=last_read_file or "",
        tool_calls=all_tool_calls
    )


async def main() -> int:
    """Main entry point for the agent."""
    try:
        # Parse command-line arguments
        if len(sys.argv) < 2:
            print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
            print(json.dumps({"answer": "No question provided", "source": "", "tool_calls": []}))
            return 1

        question = sys.argv[1]
        print(f"Question: {question}", file=sys.stderr)

        # Load settings
        try:
            settings = get_settings()
        except ValueError as e:
            print(f"Error loading configuration: {e}", file=sys.stderr)
            # Output valid JSON even on error (autochecker requirement)
            print(json.dumps({"answer": f"Configuration error: {e}", "source": "", "tool_calls": []}))
            return 1

        # Run the agentic loop
        try:
            response = await run_agentic_loop(question, settings)
        except httpx.HTTPStatusError as e:
            print(f"HTTP error: {e.response.status_code}", file=sys.stderr)
            print(f"Response: {e.response.text}", file=sys.stderr)
            print(json.dumps({"answer": f"HTTP error: {e.response.status_code}", "source": "", "tool_calls": []}))
            return 1
        except httpx.RequestError as e:
            print(f"Request error: {e}", file=sys.stderr)
            print(json.dumps({"answer": f"Request error: {e}", "source": "", "tool_calls": []}))
            return 1
        except Exception as e:
            print(f"Error in agentic loop: {e}", file=sys.stderr)
            print(json.dumps({"answer": f"Error: {e}", "source": "", "tool_calls": []}))
            return 1

        # Output valid JSON to stdout
        print(json.dumps(response))

        return 0
    except Exception as e:
        # Catch-all for any unexpected errors
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"answer": f"Unexpected error: {e}", "source": "", "tool_calls": []}))
        return 1


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))

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


# Load environment variables from .env.agent.secret
load_env_file(ENV_FILE)


def get_settings() -> dict[str, str]:
    """Get agent settings from environment variables."""
    llm_api_key = os.environ.get("LLM_API_KEY")
    llm_api_base = os.environ.get("LLM_API_BASE")
    llm_model = os.environ.get("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

    if not llm_api_key or not llm_api_base:
        raise ValueError("LLM_API_KEY and LLM_API_BASE must be set in .env.agent.secret")

    return {
        "llm_api_key": llm_api_key,
        "llm_api_base": llm_api_base,
        "llm_model": llm_model,
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
    }
]

# Map tool names to functions
TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
}

SYSTEM_PROMPT = """You are a documentation assistant for a software engineering lab. You have access to two tools:

1. list_files: List files and directories in a directory
2. read_file: Read the contents of a file

To answer questions about the project documentation:
1. First use list_files to explore the wiki directory structure
2. Use read_file to read relevant files
3. Find the specific section that answers the question
4. Include the source reference in the format: wiki/filename.md#section-anchor

Always provide a source reference when answering. The source should point to the specific file and section that contains the answer.

If you don't find the answer in the documentation, say so honestly."""


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Execute a tool and return the result."""
    if tool_name not in TOOL_FUNCTIONS:
        return f"Error: Unknown tool '{tool_name}'"
    
    func = TOOL_FUNCTIONS[tool_name]
    try:
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


async def call_llm(messages: list[dict], settings: dict[str, str], tools: list | None = None) -> dict:
    """Call the LLM API and return the response."""
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
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()

    return data


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
            result = execute_tool(tool_name, args)

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
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        return 1

    question = sys.argv[1]
    print(f"Question: {question}", file=sys.stderr)

    # Load settings
    try:
        settings = get_settings()
    except ValueError as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        print("Make sure .env.agent.secret exists with required values.", file=sys.stderr)
        return 1

    # Run the agentic loop
    try:
        response = await run_agentic_loop(question, settings)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
        return 1
    except httpx.RequestError as e:
        print(f"Request error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Output valid JSON to stdout
    print(json.dumps(response))

    return 0


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))

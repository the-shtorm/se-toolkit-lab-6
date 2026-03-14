#!/usr/bin/env python3
"""
Agent CLI - Calls an LLM and returns structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON with 'answer' and 'tool_calls' fields to stdout.
    All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


# Get the directory where agent.py is located
AGENT_DIR = Path(__file__).parent
ENV_FILE = AGENT_DIR / ".env.agent.secret"


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


def create_agent_response(content: str) -> dict[str, Any]:
    """Create the structured response format."""
    return {
        "answer": content,
        "tool_calls": []
    }


async def call_llm(question: str, settings: dict[str, str]) -> str:
    """Call the LLM API and return the answer."""
    url = f"{settings['llm_api_base']}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings['llm_api_key']}"
    }

    payload = {
        "model": settings["llm_model"],
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ]
    }

    print(f"Calling LLM at {url}...", file=sys.stderr)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()

    # Extract the answer from the response
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        print(f"Error parsing LLM response: {e}", file=sys.stderr)
        print(f"Raw response: {data}", file=sys.stderr)
        raise

    return answer


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

    # Call the LLM
    try:
        answer = await call_llm(question, settings)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
        return 1
    except httpx.RequestError as e:
        print(f"Request error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error calling LLM: {e}", file=sys.stderr)
        return 1

    # Create and output the response
    response = create_agent_response(answer)

    # Output valid JSON to stdout
    print(json.dumps(response))

    return 0


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))

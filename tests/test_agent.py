"""Regression tests for agent.py.

These tests run agent.py as a subprocess and verify the JSON output structure.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

# Project root is the parent of the tests directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_PATH = PROJECT_ROOT / "agent.py"


def run_agent(question: str, timeout: int = 180, max_retries: int = 3) -> dict:
    """Run the agent and return the parsed JSON response.

    Retries if the agent returns empty tool_calls or rate limit error (may happen due to LLM rate limiting).
    """
    for attempt in range(max_retries + 1):
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), question],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Check for rate limit error - retry with longer delay
        if result.returncode != 0 and "429" in result.stderr:
            if attempt < max_retries:
                time.sleep(5)  # Wait longer before retry for rate limit
                continue
            raise AssertionError(f"Agent hit rate limit after {max_retries + 1} attempts: {result.stderr[:200]}")

        # Check exit code
        if result.returncode != 0:
            raise AssertionError(f"Agent exited with code {result.returncode}: {result.stderr}")

        # Parse JSON
        try:
            data = json.loads(result.stdout.strip())
        except json.JSONDecodeError as e:
            raise AssertionError(f"Agent output is not valid JSON: {result.stdout[:200]}") from e

        # Check required fields exist
        assert "answer" in data, "Missing 'answer' field in output"
        assert "tool_calls" in data, "Missing 'tool_calls' field in output"

        # If tool_calls is empty, retry (LLM may have answered from cached knowledge)
        if len(data["tool_calls"]) == 0 and attempt < max_retries:
            time.sleep(2)  # Wait before retry
            continue

        return data

    return data


def test_agent_returns_valid_json_with_required_fields():
    """Test that agent.py returns valid JSON with 'answer' and 'tool_calls' fields."""
    # Run the agent with a simple question
    data = run_agent("What is 2 + 2?", timeout=60)

    # Check field types
    assert isinstance(data["answer"], str), "'answer' should be a string"
    assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"

    # Check answer is not empty
    assert len(data["answer"]) > 0, "'answer' should not be empty"


def test_agent_uses_read_file_for_wiki_question():
    """Test that agent uses read_file tool when asked about wiki documentation."""
    # Run the agent with a question that requires reading wiki files
    data = run_agent("How do you resolve a merge conflict?")

    # Check required fields
    assert "source" in data, "Missing 'source' field in output"

    # Check that read_file was used
    tool_names = [call.get("tool") for call in data["tool_calls"]]
    assert "read_file" in tool_names, "Expected read_file to be called for wiki question"

    # Check that source references wiki documentation (git.md or git-workflow.md)
    source = data.get("source", "")
    assert "wiki/git" in source and ".md" in source, \
        f"Expected source to reference wiki git documentation, got: {source}"


def test_agent_uses_list_files_for_directory_question():
    """Test that agent uses list_files tool when asked about directory contents."""
    # Run the agent with a question that requires listing files
    data = run_agent("What files are in the wiki?")

    # Check that list_files was used
    tool_names = [call.get("tool") for call in data["tool_calls"]]
    assert "list_files" in tool_names, "Expected list_files to be called for directory question"


def test_agent_uses_read_file_for_source_code_question():
    """Test that agent uses read_file tool when asked about backend source code."""
    # Run the agent with a question that requires reading backend source code
    data = run_agent("What Python web framework does the backend use?")

    # Check that read_file was used
    tool_names = [call.get("tool") for call in data["tool_calls"]]
    assert "read_file" in tool_names, "Expected read_file to be called for source code question"

    # Check that source references backend code
    source = data.get("source", "")
    assert "backend" in source.lower() or ".py" in source, \
        f"Expected source to reference backend Python file, got: {source}"


def test_agent_uses_query_api_for_data_question():
    """Test that agent uses query_api tool when asked about database data."""
    # Run the agent with a question that requires querying the API
    data = run_agent("How many items are currently stored in the database?")

    # Check that query_api was used
    tool_names = [call.get("tool") for call in data["tool_calls"]]
    assert "query_api" in tool_names, "Expected query_api to be called for data question"

    # Check that answer contains a number
    import re
    answer = data.get("answer", "")
    numbers = re.findall(r'\d+', answer)
    assert len(numbers) > 0, f"Expected answer to contain a number, got: {answer}"


if __name__ == "__main__":
    # Allow running tests directly
    test_agent_returns_valid_json_with_required_fields()
    test_agent_uses_read_file_for_wiki_question()
    test_agent_uses_list_files_for_directory_question()
    test_agent_uses_read_file_for_source_code_question()
    test_agent_uses_query_api_for_data_question()
    print("All tests passed!")

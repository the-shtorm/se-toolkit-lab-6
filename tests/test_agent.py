"""Regression tests for agent.py.

These tests run agent.py as a subprocess and verify the JSON output structure.
"""

import json
import subprocess
import sys
from pathlib import Path

# Project root is the parent of the tests directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_PATH = PROJECT_ROOT / "agent.py"


def test_agent_returns_valid_json_with_required_fields():
    """Test that agent.py returns valid JSON with 'answer' and 'tool_calls' fields."""
    # Run the agent with a simple question
    result = subprocess.run(
        [sys.executable, str(AGENT_PATH), "What is 2 + 2?"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    
    # Check exit code
    assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"
    
    # Check stdout is not empty
    assert result.stdout.strip(), "Agent produced no output"
    
    # Parse JSON
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {result.stdout[:200]}") from e
    
    # Check required fields
    assert "answer" in data, "Missing 'answer' field in output"
    assert "tool_calls" in data, "Missing 'tool_calls' field in output"
    
    # Check field types
    assert isinstance(data["answer"], str), "'answer' should be a string"
    assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"
    
    # Check answer is not empty
    assert len(data["answer"]) > 0, "'answer' should not be empty"


if __name__ == "__main__":
    # Allow running tests directly
    test_agent_returns_valid_json_with_required_fields()
    print("All tests passed!")

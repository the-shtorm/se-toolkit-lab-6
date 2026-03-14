# Task 1 Plan: Call an LLM from Code

## LLM Provider and Model

**Provider:** Qwen Code API (deployed on VM)

**Model:** `qwen3-coder-plus`

**Why this choice:**
- 1000 free requests per day (sufficient for development and testing)
- Available in Russia
- No credit card required
- OpenAI-compatible API (easy to integrate)
- Strong tool-calling capabilities (needed for future tasks)

## Architecture

### Components

1. **Environment Configuration** (`.env.agent.secret`)
   - `LLM_API_KEY`: API key for authentication
   - `LLM_API_BASE`: Base URL for the API endpoint
   - `LLM_MODEL`: Model name to use

2. **Agent CLI** (`agent.py`)
   - Parse command-line argument (the question)
   - Load environment configuration
   - Call the LLM via HTTP request
   - Parse the response
   - Output structured JSON

### Data Flow

```
Command line argument → agent.py → Load .env.agent.secret → HTTP POST to LLM API → Parse response → JSON output to stdout
```

### Input/Output

**Input:**
- Single command-line argument: the user's question
- Example: `uv run agent.py "What does REST stand for?"`

**Output:**
- Single JSON line to stdout:
  ```json
  {"answer": "Representational State Transfer.", "tool_calls": []}
  ```
- All debug/progress output goes to stderr

### Error Handling

1. **Missing arguments:** Print usage to stderr, exit with code 1
2. **Missing environment file:** Print error to stderr, exit with code 1
3. **API request failure:** Print error to stderr, exit with code 1
4. **Invalid API response:** Print error to stderr, exit with code 1
5. **Timeout (>60s):** Let the request timeout naturally, handle gracefully

### Implementation Steps

1. Create `.env.agent.secret` from `.env.agent.example`
2. Implement `agent.py`:
   - Use `sys.argv` for CLI argument parsing
   - Use `pydantic-settings` for environment loading
   - Use `httpx` for async HTTP requests
   - Use `json` for output formatting
3. Test with sample questions
4. Create regression test

### Dependencies

Already available in `pyproject.toml`:
- `httpx` - for HTTP requests
- `pydantic-settings` - for environment configuration
- `pydantic` - for data validation

No additional dependencies needed.

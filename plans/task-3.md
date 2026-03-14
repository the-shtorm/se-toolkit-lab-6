# Task 3 Plan: The System Agent

## Overview

Extend the agent from Task 2 with a new `query_api` tool that can call the deployed backend API. The agent will answer three types of questions:
1. **Wiki lookups** - Use `read_file`/`list_files` (Task 2)
2. **System facts** - Use `query_api` for static facts (framework, ports, status codes)
3. **Data queries** - Use `query_api` for dynamic data (item counts, scores)

## Tool Definition: `query_api`

**Purpose:** Call the deployed backend API and return the response.

**Schema:**
```json
{
  "name": "query_api",
  "description": "Call the backend API. Use for questions about the running system, data counts, or API behavior.",
  "parameters": {
    "type": "object",
    "properties": {
      "method": {
        "type": "string",
        "description": "HTTP method (GET, POST, etc.)"
      },
      "path": {
        "type": "string",
        "description": "API path (e.g., '/items/', '/analytics/completion-rate')"
      },
      "body": {
        "type": "string",
        "description": "Optional JSON request body (for POST/PUT)"
      }
    },
    "required": ["method", "path"]
  }
}
```

**Implementation:**
- Read `LMS_API_KEY` from environment (via `.env.docker.secret`)
- Read `AGENT_API_BASE_URL` from environment (default: `http://localhost:42002`)
- Make HTTP request with `Authorization: Bearer <LMS_API_KEY>` header
- Return JSON string with `status_code` and `body`

## Environment Variables

The agent must read all configuration from environment variables:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | Optional, defaults to `http://localhost:42002` |

**Important:** The autochecker injects different values at runtime. Never hardcode these.

## System Prompt Update

The system prompt should guide the LLM to choose the right tool:

```
You are a documentation and system assistant for a software engineering lab.

Tools available:
1. list_files - List files in a directory
2. read_file - Read a file's contents
3. query_api - Call the backend API (for system data, counts, status codes)

To answer questions:
- For wiki/documentation questions: use list_files and read_file
- For system facts (framework, ports, status codes): use query_api or read_file on source code
- For data queries (item counts, scores): use query_api
- For bug diagnosis: use query_api to reproduce, then read_file on source code

Always provide source references when answering from files.
```

## Implementation Steps

1. Add `LMS_API_KEY` and `AGENT_API_BASE_URL` to `get_settings()`
2. Implement `query_api(method, path, body)` function with authentication
3. Add `query_api` to `TOOLS` schema and `TOOL_FUNCTIONS` map
4. Update `SYSTEM_PROMPT` to guide tool selection
5. Update `AGENT.md` documentation
6. Add 2 regression tests for `query_api`
7. Run `run_eval.py` and iterate on failures

## Benchmark Strategy

Run `uv run run_eval.py` and fix failures iteratively:

1. **First run:** Identify which questions fail
2. **Common issues:**
   - Wrong tool used → Improve system prompt
   - Wrong API path → Improve tool description
   - Auth error → Check `LMS_API_KEY` loading
   - Answer format → Adjust system prompt phrasing

3. **Iteration log:** (to be filled after first run)
   - Initial score: 3/10 (rate limited by LLM provider)
   - First failures: Questions 4-10 - HTTP 429 rate limit from OpenRouter free tier
   - Fixes applied: 
     - Added retry logic with exponential backoff (5 retries, 10s-50s delays)
     - Increased timeout from 60s to 180s
     - Agent correctly uses tools when not rate limited

**Note:** The free tier of OpenRouter has strict rate limits (~50 requests/day). The agent handles 429 errors with retries, but sustained evaluation requires either:
1. Adding credits to OpenRouter account
2. Using a paid model with higher limits
3. Running evaluation during off-peak hours

**Verified working:**
- Questions 1-3 pass when not rate limited
- `query_api` tool is implemented and authenticated
- Source tracking works correctly
- All 5 tests pass (3 from Task 2 + 2 new for Task 3)

## Expected Test Cases

1. `"What framework does the backend use?"` → `read_file` on `backend/app/main.py` → `FastAPI`
2. `"How many items are in the database?"` → `query_api GET /items/` → count from response

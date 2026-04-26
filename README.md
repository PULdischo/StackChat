<picture>
  <source media="(prefers-color-scheme: dark)" srcset="logo-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="logo-light.png">
  <img width="100" src="logo-light.png" alt="StackChat Logo">
</picture>


# StackChat

A [FastMCP](https://github.com/jlowin/fastmcp) server that exposes the [Princeton University Library catalog](https://catalog.princeton.edu) as typed MCP tools. LLM agents can search, filter, and retrieve bibliographic records from over 12 million holdings without writing raw HTTP requests.

## Features

- **14 typed tools** covering keyword, title, author, subject, publisher, series, call-number, and ISBN/ISSN lookup, plus facet listing, subject/name/call-number browse
- **Smart filtering** — narrow by format, language, location, year range, or online-only access
- **ISBN/ISSN normalization** — validates check digits, strips hyphens, reports canonical form
- **Transparent caching** — TTL cache avoids redundant catalog requests
- **Automatic retry** — exponential back-off on 429 / 5xx responses
- **Configuration via env vars** — no code changes needed for alternate deployments

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/apjanco/StackChat.git
cd StackChat
uv sync
```

## Running the server

```bash
# stdio transport (default — use with Claude Desktop / any MCP host)
uv run stackchat

# Or directly:
uv run python -m stackchat.server
```

### Claude Desktop config (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "stackchat": {
      "command": "uv",
      "args": ["--directory", "/path/to/StackChat", "run", "stackchat"]
    }
  }
}
```

## Configuration

All settings have production-safe defaults. Override with environment variables or a `.env` file at the project root.

| Variable | Default | Description |
|---|---|---|
| `STACKCHAT_CATALOG_URL` | `https://catalog.princeton.edu` | Base URL of the Blacklight instance |
| `STACKCHAT_USER_AGENT` | `stackchat/0.1 (+…)` | `User-Agent` header; include a contact URL |
| `STACKCHAT_HTTP_TIMEOUT` | `15` | Request timeout in seconds |
| `STACKCHAT_CACHE_MAX_SIZE` | `512` | Maximum cached responses in memory |
| `STACKCHAT_CACHE_TTL` | `300` | Cache time-to-live in seconds |
| `STACKCHAT_RETRY_ATTEMPTS` | `3` | Max retries on 429 / 5xx errors |

Example `.env`:

```dotenv
STACKCHAT_CATALOG_URL=https://catalog.princeton.edu
STACKCHAT_HTTP_TIMEOUT=20
STACKCHAT_CACHE_TTL=600
```

## Available tools

### Search tools

| Tool | Searches by | Notes |
|---|---|---|
| `search_keyword` | All fields | Boolean operators (`AND`, `OR`, `NOT` — uppercase), wildcards (`algor*`), phrase search (`"French revolution"`) |
| `search_title` | Title words | Words in any order; for prefix lookup use `search_title_starts_with` |
| `search_title_starts_with` | Title prefix | Respects MARC non-filing characters (skips "The", "A", etc.) |
| `search_author` | Author / creator | Flexible name order |
| `search_subject` | LCSH subject headings | Partial phrases work |
| `search_publisher` | Publisher name | |
| `search_series` | Series title | |
| `search_call_number` | LC call number prefix | Browses the classified shelf; use `browse_call_numbers` for authority browse |

All search tools accept these optional refinement parameters:

| Parameter | Type | Description |
|---|---|---|
| `format` | `str \| list[str]` | E.g. `"Book"`, `["Book", "Journal"]` |
| `language` | `str \| list[str]` | E.g. `"French"` |
| `location` | `str \| list[str]` | Library location code |
| `online_only` | `bool` | Restrict to online-accessible items |
| `year_range` | `(int\|None, int\|None)` | Publication year range, e.g. `(1990, 2010)` |
| `sort` | `str` | `relevance` (default), `newest`, `oldest`, `title_asc`, `title_desc`, `author_asc` |
| `per_page` | `int` | Results per page, 1–100 (default 10) |
| `page` | `int` | 1-indexed page number |

### Record lookup

| Tool | Description |
|---|---|
| `get_record` | Fetch a single bibliographic record by catalog ID |
| `find_by_isbn` | Validate an ISBN-10 or ISBN-13, then find matching records |
| `find_by_issn` | Validate an ISSN, then find matching serial records |

### Facet and browse tools

| Tool | Description |
|---|---|
| `list_facets` | List available values (with hit counts) for a specific facet field |
| `browse_names` | Alphabetic browse of the name authority index |
| `browse_subjects` | Alphabetic browse of the subject authority index |
| `browse_call_numbers` | Alphabetic browse of the LC call number index |

## Project layout

```
src/stackchat/
├── __init__.py       Version and package metadata
├── client.py         Shared httpx client, caching, retry
├── fields.py         Field names, facets, sort tokens, browse indexes
├── models.py         Pydantic v2 request/response schemas
├── normalize.py      Blacklight JSON → clean typed models
├── server.py         FastMCP entrypoint; 14 @mcp.tool definitions
├── settings.py       Pydantic-settings configuration (env vars)
└── validate.py       ISBN-10/13 and ISSN check-digit validation

tests/
├── conftest.py       Fixtures from captured API responses
├── test_unit.py      ISBN/ISSN validation, normalize helpers
├── test_params.py    _build_params() combinations
└── test_fixtures.py  End-to-end normalization against real API data

evals/
├── prompts.yaml      20 LLM-style eval cases
└── run_eval.py       In-process FastMCP.Client smoke-test runner
```

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests with coverage
uv run pytest tests/ -v

# Run structural evals (no live network needed)
uv run python evals/run_eval.py

# Lint
uv run ruff check src/

# Auto-fix lint issues
uv run ruff check src/ --fix
```

## License

MIT


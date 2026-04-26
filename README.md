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
| `STACKCHAT_TRANSPORT` | `stdio` | `stdio` for local use; `streamable-http` for Cloud Run / remote |
| `PORT` | `8080` | Port to bind (Cloud Run injects this automatically) |

Example `.env`:

```dotenv
STACKCHAT_CATALOG_URL=https://catalog.princeton.edu
STACKCHAT_HTTP_TIMEOUT=20
STACKCHAT_CACHE_TTL=600
```

## Cloud Run deployment

### 1. Build and push the container image

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-east1
export IMAGE=gcr.io/$PROJECT_ID/stackchat

docker build -t $IMAGE .
docker push $IMAGE
```

Or use Cloud Build to build remotely:

```bash
gcloud builds submit --tag $IMAGE
```

### 2. Deploy to Cloud Run (public)

```bash
gcloud run deploy stackchat \
  --image $IMAGE \
  --region $REGION \
  --port 8080 \
  --allow-unauthenticated \
  --set-env-vars STACKCHAT_TRANSPORT=streamable-http
```

After deployment, Cloud Run prints the service URL:

```
Service URL: https://stackchat-<hash>-<region-abbr>.a.run.app
```

### 3. Map a custom domain (optional but recommended)

Cloud Run supports custom domains so users get a stable, readable URL.

```bash
gcloud run domain-mappings create \
  --service stackchat \
  --domain mcp.example.com \
  --region $REGION
```

Then add the DNS records shown in the output (a CNAME or A record pointing to `ghs.googlehosted.com`). Once DNS propagates, the service is live at `https://mcp.example.com`.

### 4. Configure your MCP client

Use the HTTPS URL directly — no local proxy or extra tooling required:

```json
{
  "mcpServers": {
    "stackchat": {
      "url": "https://mcp.example.com/mcp"
    }
  }
}
```

If you are using the auto-generated Cloud Run URL instead of a custom domain:

```json
{
  "mcpServers": {
    "stackchat": {
      "url": "https://stackchat-<hash>-<region-abbr>.a.run.app/mcp"
    }
  }
}
```

Retrieve the URL at any time with:

```bash
gcloud run services describe stackchat --region $REGION \
  --format='value(status.url)'
```

> **Private deployment:** If you want to restrict access to authenticated users only, replace `--allow-unauthenticated` with `--no-allow-unauthenticated` and use `gcloud run services proxy` or OIDC tokens. See the [Cloud Run authentication docs](https://docs.cloud.google.com/run/docs/host-mcp-servers#authenticate-mcp-clients-for-ai-agents).

### Environment variables on Cloud Run

Pass additional config at deploy time with `--set-env-vars`:

```bash
gcloud run deploy stackchat \
  --image $IMAGE \
  --region $REGION \
  --port 8080 \
  --no-allow-unauthenticated \
  --set-env-vars STACKCHAT_TRANSPORT=streamable-http,STACKCHAT_CACHE_TTL=600
```

For secrets (e.g. a future API key), use `--set-secrets` to pull from Secret Manager rather than plain env vars.

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


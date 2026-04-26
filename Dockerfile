# syntax=docker/dockerfile:1
# ── StackChat — MCP server for the Princeton University Library catalog ────────
#
# Build:  docker build -t stackchat .
# Run:    docker run -e PORT=8080 -e STACKCHAT_TRANSPORT=streamable-http -p 8080:8080 stackchat
# Deploy: see README.md § "Cloud Run deployment"

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Cloud Run requires the process to handle SIGTERM gracefully.
# Python 3.12's asyncio event loop does this by default.

WORKDIR /app

# ── Install dependencies (cached layer) ──────────────────────────────────────
# Copy only the files that define the dependency set first so Docker can cache
# this layer and skip re-installing on code-only changes.
COPY pyproject.toml uv.lock ./

# Install production deps only; --frozen ensures the lockfile is respected.
RUN uv sync --no-dev --frozen --no-install-project

# ── Copy application source ───────────────────────────────────────────────────
COPY src/ ./src/

# Install the project itself (already has deps from above).
RUN uv sync --no-dev --frozen

# ── Runtime configuration ─────────────────────────────────────────────────────
# Cloud Run injects PORT; STACKCHAT_TRANSPORT switches from stdio to HTTP.
ENV STACKCHAT_TRANSPORT=streamable-http

# Cloud Run routes external HTTPS to whatever port the container listens on.
# We default to 8080 here; Cloud Run will override PORT at runtime.
EXPOSE 8080

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD ["uv", "run", "stackchat"]

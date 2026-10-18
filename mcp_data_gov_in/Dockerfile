FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Create app user
RUN useradd --create-home --shell /bin/bash app
USER app
WORKDIR /app

# Copy uv files first for better layer caching
COPY --chown=app:app pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Streamable HTTP runtime defaults
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000
ENV FASTMCP_STREAMABLE_HTTP_PATH=/mcp
EXPOSE 8000

# Copy application code
COPY --chown=app:app . .

CMD ["uv", "run", "mcp_server.py"]

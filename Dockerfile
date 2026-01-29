# syntax=docker/dockerfile:1
# Dockerfile for Streamlit freight dashboard (merge app)
# Build: docker build -t merge-dashboard .
# Run:   docker run -p 8501:8501 merge-dashboard

FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies from lock file
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application and data files
COPY app.py ./
COPY merge/ ./merge/
COPY ["BASE_VALORES.xlsx", "CALCULO FRETE PESO.xlsx", "COTAÇÃO_LOTAÇÃO.xlsm", "./"]

EXPOSE 8501

# Streamlit listens on 0.0.0.0 so the host can reach it
CMD ["uv", "run", "streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]

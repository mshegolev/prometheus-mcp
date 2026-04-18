FROM python:3.12-slim

WORKDIR /app

# Install the package from PyPI
RUN pip install --no-cache-dir prometheus-mcp

ENTRYPOINT ["prometheus-mcp"]

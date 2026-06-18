FROM python:3.12-slim

LABEL version="0.3.0"
LABEL maintainer="Mikhail Shchegolev"

WORKDIR /app

# Install the package from PyPI
RUN pip install --no-cache-dir prometheus-mcp

ENTRYPOINT ["prometheus-mcp"]

#!/usr/bin/env python3
"""
Script to validate the OpenAPI specification for prometheus-mcp.
"""

import yaml
from pathlib import Path


def validate_openapi_spec():
    """Validate the OpenAPI specification file."""
    spec_path = Path("specs/openapi.yaml")

    if not spec_path.exists():
        print(f"Error: Specification file not found at {spec_path}")
        return False

    try:
        with open(spec_path, "r") as f:
            spec = yaml.safe_load(f)

        # Basic validation
        required_keys = ["openapi", "info", "paths"]
        for key in required_keys:
            if key not in spec:
                print(f"Error: Missing required key '{key}' in specification")
                return False

        print(f"✓ OpenAPI version: {spec['openapi']}")
        print(f"✓ Title: {spec['info']['title']}")
        print(f"✓ Version: {spec['info']['version']}")
        print(f"✓ Paths: {len(spec['paths'])} endpoints defined")

        # Check for tools
        tools = [path for path in spec["paths"].keys() if path.startswith("/tools/")]
        print(f"✓ Tools: {len(tools)} MCP tools documented")

        return True

    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML in specification file: {e}")
        return False
    except Exception as e:
        print(f"Error: Failed to validate specification: {e}")
        return False


if __name__ == "__main__":
    print("Validating OpenAPI specification...")
    if validate_openapi_spec():
        print("\n✅ Specification validation passed!")
    else:
        print("\n❌ Specification validation failed!")
        exit(1)

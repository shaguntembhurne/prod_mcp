"""
Security utilities for MCP server input validation and sanitization.
"""

import re
import html
from typing import Any, Dict, List


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """Sanitize a string input by removing potentially harmful content."""
    if not isinstance(value, str):
        raise ValueError("Value must be a string")

    # Limit length
    if len(value) > max_length:
        raise ValueError(f"String too long. Maximum {max_length} characters allowed.")

    # HTML escape
    value = html.escape(value)

    # Remove null bytes and other control characters
    value = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", value)

    return value.strip()


def validate_resource_id(resource_id: str) -> str:
    """Validate and sanitize a resource ID."""
    if not resource_id:
        raise ValueError("Resource ID cannot be empty")

    resource_id = sanitize_string(resource_id, max_length=100)

    # Basic format validation - alphanumeric, hyphens, underscores
    if not re.match(r"^[a-zA-Z0-9_-]+$", resource_id):
        raise ValueError(
            "Resource ID contains invalid characters. Only alphanumeric, hyphens, and underscores allowed."
        )

    return resource_id


def validate_query_list(queries: List[str], max_queries: int = 5, max_query_length: int = 200) -> List[str]:
    """Validate and sanitize a list of search queries."""
    if not isinstance(queries, list):
        raise ValueError("Queries must be a list")

    if len(queries) == 0:
        raise ValueError("At least one query is required")

    if len(queries) > max_queries:
        raise ValueError(f"Too many queries. Maximum {max_queries} allowed.")

    sanitized_queries = []
    for i, query in enumerate(queries):
        if not isinstance(query, str):
            raise ValueError(f"Query {i+1} must be a string")

        sanitized_query = sanitize_string(query, max_length=max_query_length)

        if not sanitized_query:
            raise ValueError(f"Query {i+1} cannot be empty after sanitization")

        sanitized_queries.append(sanitized_query)

    return sanitized_queries


def validate_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and sanitize column filters."""
    if not isinstance(filters, dict):
        raise ValueError("Filters must be a dictionary")

    sanitized_filters = {}
    for key, value in filters.items():
        # Sanitize filter keys
        sanitized_key = sanitize_string(str(key), max_length=100)
        if not sanitized_key:
            continue

        # Sanitize filter values
        if isinstance(value, str):
            sanitized_value = sanitize_string(value, max_length=500)
        else:
            sanitized_value = str(value)[:500]  # Convert to string and limit length

        if sanitized_value:
            sanitized_filters[sanitized_key] = sanitized_value

    return sanitized_filters


def log_security_event(event_type: str, details: Dict[str, Any], severity: str = "INFO"):
    """Log security-related events for monitoring."""
    # In a production environment, you might want to send this to a proper logging system
    import sys
    import json
    from datetime import datetime

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "severity": severity,
        "details": details,
    }

    print(f"SECURITY_EVENT: {json.dumps(log_entry)}", file=sys.stderr)

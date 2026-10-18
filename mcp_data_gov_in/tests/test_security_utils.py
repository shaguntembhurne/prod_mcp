"""
Tests for security utilities.
"""

import pytest
from security_utils import sanitize_string, validate_resource_id, validate_query_list, validate_filters


def test_sanitize_string():
    """Test string sanitization."""
    # Normal string should pass through
    assert sanitize_string("hello world") == "hello world"

    # HTML should be escaped
    assert sanitize_string("<script>alert('xss')</script>") == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"

    # Control characters should be removed
    assert sanitize_string("hello\x00world\x1f") == "helloworld"

    # Whitespace should be trimmed
    assert sanitize_string("  hello  ") == "hello"

    # Length limit should be enforced
    with pytest.raises(ValueError, match="String too long"):
        sanitize_string("x" * 1001)


def test_validate_resource_id():
    """Test resource ID validation."""
    # Valid resource IDs
    assert validate_resource_id("abc123") == "abc123"
    assert validate_resource_id("my-resource_id") == "my-resource_id"

    # Invalid characters
    with pytest.raises(ValueError, match="invalid characters"):
        validate_resource_id("resource@id")

    # Empty resource ID
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_resource_id("")

    # Too long
    with pytest.raises(ValueError, match="String too long"):
        validate_resource_id("x" * 101)


def test_validate_query_list():
    """Test query list validation."""
    # Valid queries
    result = validate_query_list(["query1", "query2"])
    assert result == ["query1", "query2"]

    # Empty list
    with pytest.raises(ValueError, match="At least one query"):
        validate_query_list([])

    # Too many queries
    with pytest.raises(ValueError, match="Too many queries"):
        validate_query_list(["q1", "q2", "q3", "q4", "q5", "q6"])

    # Non-string query
    with pytest.raises(ValueError, match="must be a string"):
        validate_query_list(["query1", 123])  # type: ignore

    # Empty query after sanitization
    with pytest.raises(ValueError, match="cannot be empty after sanitization"):
        validate_query_list(["query1", ""])


def test_validate_filters():
    """Test filter validation."""
    # Valid filters
    filters = {"state": "California", "year": "2023"}
    result = validate_filters(filters)
    assert result == {"state": "California", "year": "2023"}

    # Non-string values should be converted
    filters = {"count": 123, "active": True}
    result = validate_filters(filters)
    assert result == {"count": "123", "active": "True"}

    # HTML should be escaped
    filters = {"name": "<script>alert('xss')</script>"}
    result = validate_filters(filters)
    assert "&lt;script&gt;" in result["name"]

    # Non-dict input
    with pytest.raises(ValueError, match="must be a dictionary"):
        validate_filters("not a dict")  # type: ignore


if __name__ == "__main__":
    pytest.main([__file__])

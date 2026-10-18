"""
Tests for the rate limiter middleware.
"""

import asyncio
import time
from unittest.mock import Mock

import pytest

from rate_limiter import SimpleRateLimiter


class MockContext:
    def __init__(self, method: str):
        self.method = method
        self.message = Mock()
        self.message.id = "test-id"


@pytest.mark.asyncio
async def test_rate_limiter_allows_normal_requests():
    """Test that normal requests are allowed through."""
    limiter = SimpleRateLimiter(requests_per_minute=60, burst_limit=5)
    context = MockContext("tools/call")

    async def mock_call_next(ctx):
        return {"result": "success"}

    # First few requests should be allowed
    for i in range(3):
        result = await limiter.on_message(context, mock_call_next)
        assert result == {"result": "success"}


@pytest.mark.asyncio
async def test_rate_limiter_blocks_burst():
    """Test that burst limit is enforced."""
    limiter = SimpleRateLimiter(requests_per_minute=60, burst_limit=2)
    context = MockContext("tools/call")

    async def mock_call_next(ctx):
        return {"result": "success"}

    # First two requests should be allowed
    for i in range(2):
        result = await limiter.on_message(context, mock_call_next)
        assert result == {"result": "success"}

    # Third request should be blocked
    result = await limiter.on_message(context, mock_call_next)
    assert result["error"]["message"] == "Rate limit exceeded. Please slow down your requests."


@pytest.mark.asyncio
async def test_rate_limiter_ignores_non_tool_calls():
    """Test that non-tool-call messages are not rate limited."""
    limiter = SimpleRateLimiter(requests_per_minute=1, burst_limit=1)
    context = MockContext("resources/list")

    async def mock_call_next(ctx):
        return {"result": "success"}

    # Multiple non-tool calls should be allowed
    for i in range(5):
        result = await limiter.on_message(context, mock_call_next)
        assert result == {"result": "success"}


@pytest.mark.asyncio
async def test_rate_limiter_cleanup():
    """Test that old requests are cleaned up."""
    limiter = SimpleRateLimiter(requests_per_minute=60, burst_limit=10)
    limiter.window_size = 0.1  # 100ms window for testing

    context = MockContext("tools/call")

    async def mock_call_next(ctx):
        return {"result": "success"}

    # Make some requests
    for i in range(3):
        await limiter.on_message(context, mock_call_next)

    # Wait for window to expire
    await asyncio.sleep(0.15)

    # Should be able to make more requests
    result = await limiter.on_message(context, mock_call_next)
    assert result == {"result": "success"}


if __name__ == "__main__":
    pytest.main([__file__])

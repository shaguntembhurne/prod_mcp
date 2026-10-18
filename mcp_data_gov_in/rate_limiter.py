"""
Simple rate limiting middleware for MCP server.
"""

import time
from typing import Dict, Any
from collections import defaultdict, deque
from fastmcp.server.middleware import Middleware, MiddlewareContext


class SimpleRateLimiter(Middleware):
    """Simple in-memory rate limiter based on client identification."""

    def __init__(self, requests_per_minute: int = 60, burst_limit: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.window_size = 60  # 1 minute window

        # Store request timestamps per client
        self.request_history: Dict[str, deque] = defaultdict(lambda: deque())

    def _get_client_id(self, context: MiddlewareContext) -> str:
        """Get a simple client identifier. In production, this could be more sophisticated."""
        # For stdio transport, we use a fixed identifier since it's single-user
        # For HTTP transport, you could use IP address or authentication info
        return "local_client"

    def _cleanup_old_requests(self, client_id: str, current_time: float):
        """Remove requests older than the window size."""
        history = self.request_history[client_id]
        while history and history[0] < current_time - self.window_size:
            history.popleft()

    def _is_rate_limited(self, client_id: str) -> bool:
        """Check if the client should be rate limited."""
        current_time = time.time()
        self._cleanup_old_requests(client_id, current_time)

        history = self.request_history[client_id]

        # Check burst limit (requests in last few seconds)
        recent_requests = sum(1 for timestamp in history if timestamp > current_time - 5)
        if recent_requests >= self.burst_limit:
            return True

        # Check rate limit (requests per minute)
        if len(history) >= self.requests_per_minute:
            return True

        return False

    def _record_request(self, client_id: str):
        """Record a new request timestamp."""
        current_time = time.time()
        self.request_history[client_id].append(current_time)

    async def on_message(self, context: MiddlewareContext, call_next):
        """Check rate limits before processing the message."""
        client_id = self._get_client_id(context)

        # Only rate limit tool calls, not other protocol messages
        if context.method == "tools/call":
            if self._is_rate_limited(client_id):
                # Return a proper JSON-RPC error
                return {
                    "jsonrpc": "2.0",
                    "id": getattr(context.message, "id", None),
                    "error": {
                        "code": -32603,  # Internal error
                        "message": "Rate limit exceeded. Please slow down your requests.",
                        "data": {"retry_after": 60, "limit": self.requests_per_minute, "window": "1 minute"},
                    },
                }

            self._record_request(client_id)

        return await call_next(context)

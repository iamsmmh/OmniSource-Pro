"""
Rate limiter for API connectors.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from omnisource.config.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for API requests.

    Tracks remaining requests and wait times for rate-limited APIs.
    """

    def __init__(
        self,
        max_requests: int = 5000,
        period: timedelta = timedelta(hours=1),
    ):
        """
        Initialize the rate limiter.

        Args:
            max_requests: Maximum requests per period
            period: Time period for rate limit
        """
        self.max_requests = max_requests
        self.period = period
        self.remaining = max_requests
        self.reset_at: datetime | None = None
        self._lock = asyncio.Lock()
        self._last_request: datetime | None = None

    async def wait_for_token(self) -> None:
        """
        Wait for a token to be available.

        If rate limited, waits until the reset time.
        If no tokens remaining, waits until reset.
        """
        async with self._lock:
            now = datetime.now(UTC)

            # Check if we need to reset
            if self.reset_at and now >= self.reset_at:
                self.remaining = self.max_requests
                self.reset_at = now + self.period
                self._last_request = now
                return

            # If no reset time, initialize it
            if self.reset_at is None:
                self.reset_at = now + self.period

            # Check if we have remaining requests
            if self.remaining > 0:
                self.remaining -= 1
                self._last_request = now
                return

            # Calculate wait time
            if self.reset_at:
                wait_time = (self.reset_at - now).total_seconds()
                if wait_time > 0:
                    logger.debug(f"Rate limited. Waiting {wait_time:.1f}s for reset")
                    await asyncio.sleep(wait_time)
                    resumed_at = datetime.now(UTC)
                    self.remaining = self.max_requests - 1
                    self.reset_at = resumed_at + self.period
                    self._last_request = resumed_at

    def update_remaining(self, remaining: int) -> None:
        """Update remaining requests from API response."""
        self.remaining = remaining

    def update_reset(self, reset_time: datetime) -> None:
        """Update reset time from API response."""
        self.reset_at = reset_time

    @property
    def is_rate_limited(self) -> bool:
        """Check if currently rate limited."""
        if self.remaining <= 0:
            return True
        if self.reset_at and datetime.now(UTC) >= self.reset_at:
            return False
        return self.remaining <= 0

    @property
    def time_until_reset(self) -> float | None:
        """Get seconds until rate limit reset."""
        if self.reset_at:
            delta = self.reset_at - datetime.now(UTC)
            return max(0, delta.total_seconds())
        return None

    @property
    def requests_remaining(self) -> int:
        """Get remaining requests."""
        return self.remaining

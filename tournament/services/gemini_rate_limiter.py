"""
Gemini API Rate Limiter
=======================
Enforces a strict sliding-window rate limit on all Gemini API calls
across threads to at most 5 calls per minute (or custom configured threshold).
Includes HTTP 429 quota backoff handling.
"""

import logging
import threading
import time
from collections import deque
from typing import Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class GeminiRateLimiter:
    """
    Thread-safe sliding-window rate limiter for Google Gemini API calls.
    Guarantees no more than MAX_CALLS_PER_MINUTE within any 60-second window.
    """

    _lock = threading.Lock()
    _timestamps: deque = deque()
    _penalty_until: float = 0.0

    @classmethod
    def get_max_calls_per_minute(cls) -> int:
        """Returns maximum permitted calls per minute (default: 5)."""
        return int(getattr(settings, "GEMINI_MAX_CALLS_PER_MINUTE", 5))

    @classmethod
    def get_window_seconds(cls) -> float:
        """Returns the sliding window duration in seconds (default: 60.0)."""
        return float(getattr(settings, "GEMINI_RATE_LIMIT_WINDOW_SECONDS", 60.0))

    @classmethod
    def acquire(cls, timeout: float = 120.0) -> bool:
        """
        Blocks until an API call slot is available within the 5 calls/minute rate limit.
        Returns True when the slot is acquired, or False if timeout expires.
        """
        start_wait = time.time()
        max_calls = cls.get_max_calls_per_minute()
        window_seconds = cls.get_window_seconds()

        while True:
            penalty_sleep = 0.0
            sleep_duration = 0.0
            with cls._lock:
                now = time.time()

                # 1. Check if we are in a 429 penalty cooldown
                if cls._penalty_until > now:
                    penalty_sleep = cls._penalty_until - now + 0.1
                    if (time.time() - start_wait) + penalty_sleep > timeout:
                        logger.warning("GeminiRateLimiter: Timeout while waiting for 429 penalty backoff to clear.")
                        return False
                    logger.info("GeminiRateLimiter: In 429 penalty backoff. Waiting %.1fs...", penalty_sleep)
                else:
                    # 2. Evict timestamps older than sliding window
                    while cls._timestamps and cls._timestamps[0] <= now - window_seconds:
                        cls._timestamps.popleft()

                    # 3. Check if under rate limit
                    if len(cls._timestamps) < max_calls:
                        cls._timestamps.append(now)
                        logger.debug("GeminiRateLimiter: Slot acquired (%d/%d calls in last %.0fs)", len(cls._timestamps), max_calls, window_seconds)
                        return True

                    # 4. Rate limit reached: compute wait time until oldest timestamp expires
                    oldest_timestamp = cls._timestamps[0]
                    sleep_duration = (oldest_timestamp + window_seconds) - now + 0.05

            if penalty_sleep > 0:
                time.sleep(penalty_sleep)
                continue

            # Outside lock: sleep until window rolls over
            if (time.time() - start_wait) + sleep_duration > timeout:
                logger.warning("GeminiRateLimiter: Timeout (%.1fs) waiting for Gemini rate limit slot.", timeout)
                return False

            logger.info("GeminiRateLimiter: Rate limit reached (%d calls/min). Throttling call for %.1fs...", max_calls, sleep_duration)
            time.sleep(sleep_duration)

    @classmethod
    def record_429(cls, backoff_seconds: float = 60.0):
        """
        Registers an HTTP 429 Too Many Requests response from Gemini,
        imposing a temporary penalty backoff across all threads.
        """
        with cls._lock:
            cls._penalty_until = time.time() + backoff_seconds
            logger.warning(
                "GeminiRateLimiter: Recorded HTTP 429 (Quota/Rate Limit Exceeded). Enforcing %.0fs cooldown on Gemini API.",
                backoff_seconds
            )

    @classmethod
    def reset(cls):
        """Resets the rate limiter state (used in testing)."""
        with cls._lock:
            cls._timestamps.clear()
            cls._penalty_until = 0.0

    @classmethod
    def get_status(cls) -> dict:
        """Returns current rate limiter statistics."""
        with cls._lock:
            now = time.time()
            window_seconds = cls.get_window_seconds()
            active_calls = sum(1 for t in cls._timestamps if t > now - window_seconds)
            return {
                "active_calls_in_window": active_calls,
                "max_calls_per_minute": cls.get_max_calls_per_minute(),
                "in_penalty_cooldown": cls._penalty_until > now,
                "penalty_remaining_seconds": max(0.0, cls._penalty_until - now),
            }

"""
Gemini API Rate Limiter
=======================
Enforces a strict sliding-window rate limit on all Gemini API calls
across threads to at most 5 calls per minute (or custom configured threshold).
Includes HTTP 429 quota backoff handling.
"""

import fcntl
import json
import logging
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from django.conf import settings

logger = logging.getLogger(__name__)


class GeminiRateLimiter:
    """
    Thread-safe and cross-process sliding-window rate limiter for Google Gemini API calls.
    Guarantees no more than MAX_CALLS_PER_MINUTE within any 60-second window across
    web workers and background cron processes.
    """

    _lock = threading.Lock()
    _state_file = os.path.join(tempfile.gettempdir(), "prediction_engine_gemini_ratelimit.json")

    @classmethod
    @contextmanager
    def _locked_state(cls, write: bool = False):
        """Acquires thread + fcntl file lock and yields mutable {'timestamps': list, 'penalty_until': float}."""
        with cls._lock:
            os.makedirs(os.path.dirname(cls._state_file), exist_ok=True)
            with open(cls._state_file, "a+", encoding="utf-8") as fh:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                try:
                    fh.seek(0)
                    raw = fh.read().strip()
                    try:
                        state = json.loads(raw) if raw else {}
                    except json.JSONDecodeError:
                        state = {}
                    if not isinstance(state, dict):
                        state = {}
                    state.setdefault("timestamps", [])
                    state.setdefault("penalty_until", 0.0)
                    yield state
                    if write:
                        fh.seek(0)
                        fh.truncate()
                        json.dump(state, fh)
                        fh.flush()
                finally:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    @classmethod
    def get_max_calls_per_minute(cls) -> int:
        """Returns maximum permitted calls per minute (default: 14)."""
        return int(getattr(settings, "GEMINI_MAX_CALLS_PER_MINUTE", 14))

    @classmethod
    def get_window_seconds(cls) -> float:
        """Returns the sliding window duration in seconds (default: 60.0)."""
        return float(getattr(settings, "GEMINI_RATE_LIMIT_WINDOW_SECONDS", 60.0))

    @classmethod
    def is_in_penalty(cls) -> bool:
        """Returns True if the rate limiter is currently in an active 429 penalty cooldown."""
        with cls._locked_state(write=False) as state:
            return time.time() < float(state["penalty_until"])

    @classmethod
    def acquire(cls, timeout: float = 8.0) -> bool:
        """
        Blocks until an API call slot is available within the rate limit.
        Returns True when the slot is acquired, or False if timeout expires.
        """
        start_wait = time.time()
        max_calls = cls.get_max_calls_per_minute()
        window_seconds = cls.get_window_seconds()

        while True:
            penalty_sleep = 0.0
            sleep_duration = 0.0
            with cls._locked_state(write=True) as state:
                now = time.time()
                penalty_until = float(state["penalty_until"])

                # 1. Check if we are in a 429 penalty cooldown
                if penalty_until > now:
                    penalty_sleep = penalty_until - now + 0.1
                    if (time.time() - start_wait) + penalty_sleep > timeout:
                        logger.warning("GeminiRateLimiter: Timeout while waiting for 429 penalty backoff to clear.")
                        return False
                    logger.info("GeminiRateLimiter: In 429 penalty backoff. Waiting %.1fs...", penalty_sleep)
                else:
                    # 2. Evict timestamps older than sliding window
                    timestamps = [t for t in state["timestamps"] if t > now - window_seconds]
                    state["timestamps"] = timestamps

                    # 3. Check if under rate limit
                    if len(timestamps) < max_calls:
                        timestamps.append(now)
                        logger.debug("GeminiRateLimiter: Slot acquired (%d/%d calls in last %.0fs)", len(timestamps), max_calls, window_seconds)
                        return True

                    # 4. Rate limit reached: compute wait time until oldest timestamp expires
                    oldest_timestamp = timestamps[0]
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
        imposing a temporary penalty backoff across all processes.
        """
        with cls._locked_state(write=True) as state:
            state["penalty_until"] = time.time() + backoff_seconds
            logger.warning(
                "GeminiRateLimiter: Recorded HTTP 429 (Quota/Rate Limit Exceeded). Enforcing %.0fs cooldown on Gemini API.",
                backoff_seconds
            )

    @classmethod
    def reset(cls):
        """Resets the rate limiter state (used in testing)."""
        with cls._locked_state(write=True) as state:
            state["timestamps"] = []
            state["penalty_until"] = 0.0

    @classmethod
    def get_status(cls) -> dict:
        """Returns current rate limiter statistics."""
        with cls._locked_state(write=False) as state:
            now = time.time()
            window_seconds = cls.get_window_seconds()
            active_calls = sum(1 for t in state["timestamps"] if t > now - window_seconds)
            penalty_until = float(state["penalty_until"])
            return {
                "active_calls_in_window": active_calls,
                "max_calls_per_minute": cls.get_max_calls_per_minute(),
                "in_penalty_cooldown": penalty_until > now,
                "penalty_remaining_seconds": max(0.0, penalty_until - now),
            }

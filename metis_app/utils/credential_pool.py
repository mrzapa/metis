"""metis_app.utils.credential_pool — Thread-safe API key pool with least-used rotation.

Ported from Hermes Agent v0.7.0 credential_pool pattern.
"""
from __future__ import annotations

import threading
from typing import Sequence


class CredentialPool:
    """Manages a pool of API keys for a single provider.

    Strategy: least-used — always return the key with the lowest success_count.
    On auth failure, remove the key from the active pool.
    Thread-safe via a single Lock.
    """

    def __init__(self, keys: Sequence[str]) -> None:
        self._lock = threading.Lock()
        # {key: use_count}
        self._pool: dict[str, int] = {k: 0 for k in keys if k}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_key(self) -> str:
        """Return the least-used active key.

        Raises
        ------
        RuntimeError
            If the pool is empty or all keys have been failed out.
        """
        with self._lock:
            if not self._pool:
                raise RuntimeError(
                    "No credential pool keys available. "
                    "Add more keys to 'credential_pool' in settings."
                )
            return min(self._pool, key=self._pool.__getitem__)

    def report_success(self, key: str) -> None:
        """Increment use counter for *key*."""
        with self._lock:
            if key in self._pool:
                self._pool[key] += 1

    def report_failure(self, key: str) -> None:
        """Remove *key* from the active pool (auth/rate-limit failure)."""
        with self._lock:
            self._pool.pop(key, None)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def active_count(self) -> int:
        """Number of keys still in the active pool."""
        with self._lock:
            return len(self._pool)

"""Tests for metis_app.utils.credential_pool.CredentialPool."""
from __future__ import annotations
import pytest
from metis_app.utils.credential_pool import CredentialPool


def test_get_key_returns_first_when_all_equal():
    pool = CredentialPool(["key-a", "key-b", "key-c"])
    assert pool.get_key() == "key-a"


def test_report_success_increments_use_count():
    pool = CredentialPool(["key-a", "key-b"])
    pool.report_success("key-a")
    pool.report_success("key-a")
    # key-b has lower count — should be preferred now
    assert pool.get_key() == "key-b"


def test_report_failure_removes_key():
    pool = CredentialPool(["key-a", "key-b"])
    pool.report_failure("key-a")
    assert pool.get_key() == "key-b"


def test_report_failure_all_keys_raises():
    pool = CredentialPool(["key-a"])
    pool.report_failure("key-a")
    with pytest.raises(RuntimeError, match="No credential pool keys"):
        pool.get_key()


def test_empty_pool_raises():
    pool = CredentialPool([])
    with pytest.raises(RuntimeError, match="No credential pool keys"):
        pool.get_key()


def test_thread_safety(monkeypatch):
    """get_key() + report_success() from multiple threads should not corrupt state."""
    import threading
    pool = CredentialPool(["k1", "k2", "k3"])
    results = []
    errors = []

    def _worker():
        try:
            key = pool.get_key()
            pool.report_success(key)
            results.append(key)
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=_worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(results) == 20

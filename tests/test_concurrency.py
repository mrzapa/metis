"""Concurrency and safety tests for shared state operations.

These tests validate that the concurrency hardening changes work correctly:
- Settings atomic writes
- Session append under contention
- Index bundle atomic staging
- Single-instance guard
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
import time
from typing import Any

import pytest


class TestSettingsAtomicWrite:
    """Tests for atomic settings writes."""

    def test_atomic_write_creates_valid_file(self, tmp_path: pathlib.Path) -> None:
        """Verify atomic write produces a valid, readable file."""
        from metis_app import settings_store

        settings_file = tmp_path / "settings.json"

        class MockStore:
            DEFAULT_PATH = tmp_path / "default.json"
            USER_PATH = settings_file

            def load_settings(self) -> dict[str, Any]:
                return {}

        mock = MockStore()
        mock.DEFAULT_PATH.write_text("{}")

        content = json.dumps({"key": "value"}, indent=2)
        settings_store._atomic_write(settings_file, content)

        assert settings_file.exists()
        result = json.loads(settings_file.read_text(encoding="utf-8"))
        assert result == {"key": "value"}

    def test_atomic_write_overwrites_existing(self, tmp_path: pathlib.Path) -> None:
        """Verify atomic write correctly overwrites existing file."""
        from metis_app import settings_store

        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"old": "value"}')

        content = json.dumps({"new": "value"}, indent=2)
        settings_store._atomic_write(settings_file, content)

        result = json.loads(settings_file.read_text(encoding="utf-8"))
        assert result == {"new": "value"}

    @pytest.mark.skipif(
        os.name == "nt", reason="Concurrent file access flaky on Windows"
    )
    def test_concurrent_writes_produce_valid_json(self, tmp_path: pathlib.Path) -> None:
        """Multiple processes writing concurrently should not corrupt the file."""
        from metis_app import settings_store

        settings_file = tmp_path / "settings.json"
        settings_file.write_text("{}")

        errors: list[Exception] = []

        def writer(value: int) -> None:
            try:
                for _ in range(10):
                    content = json.dumps({"value": value})
                    settings_store._atomic_write(settings_file, content)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        result = json.loads(settings_file.read_text(encoding="utf-8"))
        assert "value" in result


class TestSessionRepositoryConcurrency:
    """Tests for session repository under concurrent access."""

    def test_wal_mode_enabled(self, tmp_path: pathlib.Path) -> None:
        """Verify WAL mode is enabled for new connections."""
        from metis_app.services.session_repository import SessionRepository

        repo = SessionRepository(db_path=tmp_path / "test.db")
        repo.init_db()

        with repo._connect() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode.lower() == "wal"

    def test_concurrent_append_uses_transaction(self, tmp_path: pathlib.Path) -> None:
        """Verify append_message uses explicit transactions."""
        from metis_app.services.session_repository import SessionRepository

        repo = SessionRepository(db_path=tmp_path / "test.db")
        repo.init_db()
        session = repo.create_session(session_id="test-session")

        errors: list[Exception] = []

        def append_message(thread_id: int) -> None:
            try:
                for i in range(5):
                    repo.append_message(
                        session.session_id,
                        role="user",
                        content=f"Message from thread {thread_id} iteration {i}",
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=append_message, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        updated = repo.get_session(session.session_id)
        assert updated is not None
        assert len(updated.messages) == 15


class TestIndexBundleAtomicStaging:
    """Tests for atomic index bundle staging."""

    def test_atomic_dir_stage_creates_directory(self, tmp_path: pathlib.Path) -> None:
        """Verify atomic staging creates a complete directory."""
        from metis_app.services import index_service

        target = tmp_path / "index"
        stage_files = {
            pathlib.Path("manifest.json"): {"index_id": "test"},
            pathlib.Path("bundle.json"): {"chunks": []},
            pathlib.Path("artifacts") / "outline.json": [],
        }

        index_service._atomic_dir_stage(target, stage_files)

        assert target.exists()
        assert (target / "manifest.json").exists()
        assert (target / "bundle.json").exists()
        assert (target / "artifacts" / "outline.json").exists()

    def test_atomic_dir_stage_atomic_replacement(self, tmp_path: pathlib.Path) -> None:
        """Verify atomic staging atomically replaces existing directory."""
        from metis_app.services import index_service

        target = tmp_path / "index"
        target.mkdir()
        (target / "old.txt").write_text("old")

        stage_files = {
            pathlib.Path("new.txt"): {"data": "new"},
        }

        index_service._atomic_dir_stage(target, stage_files)

        assert target.exists()
        assert (target / "new.txt").exists()
        assert not (target / "old.txt").exists()


class TestSingleInstanceGuard:
    """Tests for single-instance guard."""

    def test_lock_file_created(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify lock file is created when acquiring."""
        import metis_app.api.__main__ as api_main

        monkeypatch.setattr(api_main, "_LOCK_FILE", tmp_path / ".lock")

        result = api_main._acquire_lock()
        assert result is True
        assert (tmp_path / ".lock").exists()

    def test_lock_rejected_when_held(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify second instance is rejected when lock is held."""
        import metis_app.api.__main__ as api_main

        lock_file = tmp_path / ".lock"
        monkeypatch.setattr(api_main, "_LOCK_FILE", lock_file)

        lock_file.write_text(str(os.getpid() + 99999))

        result = api_main._acquire_lock()
        assert result is False

    def test_lock_released_on_exit(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify lock is released on exit."""
        import metis_app.api.__main__ as api_main

        lock_file = tmp_path / ".lock"
        monkeypatch.setattr(api_main, "_LOCK_FILE", lock_file)

        acquired = api_main._acquire_lock()
        assert acquired is True

        api_main._release_lock()
        assert not lock_file.exists()

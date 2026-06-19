from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta


def test_phase37_log_metadata_serializes_datetime_values(monkeypatch):
    from app.plugins.tigrao_fsm import storage

    captured = {}

    class FakeResult:
        lastrowid = 123

    class FakeConn:
        def execute(self, stmt, params=None):
            if params and "metadata_json" in params:
                captured["metadata_json"] = params["metadata_json"]
            return FakeResult()

    class FakeBegin:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    monkeypatch.setattr(storage, "ensure_tables", lambda: None)
    monkeypatch.setattr(storage, "engine", FakeEngine())

    when = datetime(2026, 6, 19, 9, 15, 0, tzinfo=timezone.utc)
    row_id = storage.log_event(
        action="test_datetime_metadata",
        result="ok",
        detection="direta",
        surface="teste",
        metadata={"expire_date": when, "duration": timedelta(minutes=30)},
    )

    assert row_id == 123
    data = json.loads(captured["metadata_json"])
    assert data["expire_date"] == "2026-06-19T09:15:00+00:00"
    assert data["duration"] == 1800

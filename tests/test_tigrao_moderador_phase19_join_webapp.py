from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient


def test_phase19_join_request_static_assets_exist() -> None:
    assert Path("app/static/join-request.html").exists()
    assert Path("app/static/join-request.css").exists()
    assert Path("app/static/join-request.js").exists()
    html = Path("app/static/join-request.html").read_text(encoding="utf-8")
    js = Path("app/static/join-request.js").read_text(encoding="utf-8")
    assert "groupSelect" in html
    assert "/telegram/join-request/groups" in js
    assert "selected_chat_id" in js
    assert "result: \"queue\"" in js


def test_phase19_webapp_url_defaults_to_join_request() -> None:
    source = Path("app/config/settings.py").read_text(encoding="utf-8")
    assert "return f\"{BASE_URL}/join-request\"" in source
    assert "TIGRAO_JOIN_REQUEST_WEBAPP_URL = _resolve_join_request_webapp_url()" in source


def test_phase19_runtime_stores_query_id_and_stops_after_webapp() -> None:
    runtime = Path("app/plugins/tigrao_fsm/runtime/join_request_runtime.py").read_text(encoding="utf-8")
    assert "query_id=str(getattr(join_request, \"query_id\"" in runtime
    assert "if await _send_join_request_webapp_if_available(bot, join_request, request):\n        return True" in runtime


def test_phase19_groups_endpoint_lists_known_groups_with_secret(monkeypatch) -> None:
    from app import main

    monkeypatch.setattr(main, "WEBHOOK_SECRET", "secret")
    monkeypatch.setattr(main, "list_groups", lambda limit=100: [
        {"chat_id": -1001, "title": "Grupo A", "username": "grupo_a", "chat_type": "supergroup", "last_seen": "2026-06-18T00:00:00Z"},
        {"chat_id": -1002, "title": "Grupo B", "username": None, "chat_type": "supergroup", "last_seen": "2026-06-18T00:00:00Z"},
    ])
    client = TestClient(main.app)

    response = client.post("/telegram/join-request/groups", json={"secret": "secret"})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert [group["title"] for group in data["groups"]] == ["Grupo A", "Grupo B"]
    assert data["groups"][0]["public_link"] == "https://t.me/grupo_a"


def test_phase19_join_request_query_blocks_group_mismatch(monkeypatch) -> None:
    from app import main

    calls: list[dict] = []
    monkeypatch.setattr(main, "WEBHOOK_SECRET", "secret")
    monkeypatch.setattr(main, "bot", SimpleNamespace(token="123:TOKEN"))
    monkeypatch.setattr(main, "answer_chat_join_request_query_compat", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        main.tigrao_storage,
        "find_pending_join_request_by_query_id",
        lambda query_id: SimpleNamespace(
            chat_id=-1001,
            chat_title="Grupo A",
            user_id=777,
            username="usuario",
            full_name="Usuário",
        ),
    )
    monkeypatch.setattr(main.tigrao_storage, "log_event", lambda **kwargs: None)
    client = TestClient(main.app)

    response = client.post("/telegram/join-request-query", json={
        "secret": "secret",
        "query_id": "query-1",
        "result": "queue",
        "selected_chat_id": -1002,
    })

    assert response.status_code == 409
    assert calls == []

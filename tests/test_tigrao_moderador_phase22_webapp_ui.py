from __future__ import annotations

from pathlib import Path
from fastapi.testclient import TestClient


def test_phase22_join_webapp_uses_bot_profile_icon_and_custom_group_buttons() -> None:
    html = Path("app/static/join-request.html").read_text(encoding="utf-8")
    js = Path("app/static/join-request.js").read_text(encoding="utf-8")
    css = Path("app/static/join-request.css").read_text(encoding="utf-8")

    assert 'src="/telegram/bot-icon"' in html
    assert 'id="botIcon"' in html
    assert 'id="groupList"' in html
    assert 'role="radiogroup"' in html
    assert "group-option" in js
    assert 'setAttribute("role", "radio")' in js
    assert "setSelectedGroup" in js
    assert "selected_chat_id: selectedGroupId()" in js
    assert "choice-dot" in html
    assert 'input[type="checkbox"]' in css
    assert "opacity: 0" in css
    assert "appearance: none" in css


def test_phase22_bot_icon_endpoint_returns_fallback_without_token(monkeypatch) -> None:
    from app import main

    monkeypatch.setattr(main, "TELEGRAM_BOT_TOKEN", "")
    client = TestClient(main.app)

    response = client.get("/telegram/bot-icon")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert b">R<" in response.content


def test_phase22_bot_icon_helper_uses_public_telegram_profile_photo_api() -> None:
    source = Path("app/bot/bot_profile_icon.py").read_text(encoding="utf-8")

    assert "getMe" in source
    assert "getUserProfilePhotos" in source
    assert "getFile" in source
    assert "https://api.telegram.org/file/bot" in source
    assert "CACHE_MAX_AGE_SECONDS" in source

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_phase16_answer_join_request_query_falls_back_to_raw_bot_api(monkeypatch) -> None:
    from app.bot import api_compat

    calls: list[tuple[str, str, dict]] = []

    def fake_post(token: str, method_name: str, payload: dict, *, timeout: float = 10.0):
        calls.append((token, method_name, payload))
        return True

    monkeypatch.setattr(api_compat, "_post_json_sync", fake_post)
    bot = SimpleNamespace(token="123:TOKEN")

    result = await api_compat.answer_chat_join_request_query_compat(
        bot,
        chat_join_request_query_id="query-123",
        result="queue",
    )

    assert result is True
    assert calls == [("123:TOKEN", "answerChatJoinRequestQuery", {"chat_join_request_query_id": "query-123", "result": "queue"})]


@pytest.mark.asyncio
async def test_phase16_send_join_request_webapp_falls_back_to_raw_bot_api(monkeypatch) -> None:
    from app.bot import api_compat

    calls: list[tuple[str, str, dict]] = []

    def fake_post(token: str, method_name: str, payload: dict, *, timeout: float = 10.0):
        calls.append((token, method_name, payload))
        return True

    monkeypatch.setattr(api_compat, "_post_json_sync", fake_post)
    bot = SimpleNamespace(token="123:TOKEN")

    result = await api_compat.send_chat_join_request_web_app_compat(
        bot,
        chat_join_request_query_id="query-abc",
        web_app_url="https://example.com/join",
    )

    assert result is True
    assert calls == [("123:TOKEN", "sendChatJoinRequestWebApp", {"chat_join_request_query_id": "query-abc", "web_app_url": "https://example.com/join"})]


@pytest.mark.asyncio
async def test_phase16_compat_prefers_aiogram_method_when_present() -> None:
    from app.bot import api_compat

    class BotWithNativeMethod:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def answer_chat_join_request_query(self, **kwargs):
            self.calls.append(kwargs)
            return "native"

    bot = BotWithNativeMethod()
    result = await api_compat.answer_chat_join_request_query_compat(bot, chat_join_request_query_id="q", result="approve")

    assert result == "native"
    assert bot.calls == [{"chat_join_request_query_id": "q", "result": "approve"}]


def test_phase16_main_join_request_endpoint_is_wired_to_compat() -> None:
    from pathlib import Path

    source = Path("app/main.py").read_text(encoding="utf-8")
    assert '@app.post("/telegram/join-request-query")' in source
    assert "answer_chat_join_request_query_compat" in source
    assert "await answer_chat_join_request_query_compat(bot, chat_join_request_query_id=query_id, result=result)" in source


def test_phase16_static_no_direct_missing_aiogram_join_request_calls() -> None:
    from pathlib import Path

    runtime = Path("app/plugins/tigrao_fsm/runtime/join_request_runtime.py").read_text(encoding="utf-8")
    main_source = Path("app/main.py").read_text(encoding="utf-8")

    assert "bot.send_chat_join_request_web_app" not in runtime
    assert "bot.answer_chat_join_request_query" not in main_source
    assert "send_chat_join_request_web_app_compat" in runtime
    assert "answer_chat_join_request_query_compat" in main_source


def test_phase16_reactions_menu_is_not_dead_text() -> None:
    from pathlib import Path

    source = Path("app/plugins/tigrao_fsm/routers/panel.py").read_text(encoding="utf-8")
    assert "Reações ainda não implementadas" not in source
    assert "make_callback(session.session_id, \"react1\")" in source
    assert "make_callback(session.session_id, \"reactall\")" in source

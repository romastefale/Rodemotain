from __future__ import annotations


def test_x9_inline_is_subscribed_in_allowed_updates() -> None:
    from app.config.settings import ALLOWED_UPDATES

    assert "inline_query" in ALLOWED_UPDATES
    assert "callback_query" in ALLOWED_UPDATES


def test_x9_query_parser_accepts_empty_user_and_chat() -> None:
    from app.plugins.tigrao_fsm.routers.inline_x9 import parse_x9_query

    assert parse_x9_query("...").target_user_id is None
    one = parse_x9_query("+ 123456789")
    assert one.target_user_id == 123456789
    assert one.chat_id is None
    two = parse_x9_query("+ 123456789 + -1009876543210")
    assert two.target_user_id == 123456789
    assert two.chat_id == -1009876543210


def test_x9_callback_data_stays_under_telegram_limit() -> None:
    from app.plugins.tigrao_fsm.routers.inline_x9 import _callback_data, parse_x9_callback

    data = _callback_data("ask", "muteforever", 1234567890, -1009876543210)
    assert len(data.encode("utf-8")) <= 64
    assert parse_x9_callback(data) == ("ask", "muteforever", 1234567890, -1009876543210)


def test_x9_inline_results_hide_functions_from_unauthorized_users() -> None:
    from app.plugins.tigrao_fsm.routers.inline_x9 import build_x9_inline_results

    results = build_x9_inline_results("123", authorized=False)
    assert len(results) == 1
    result = results[0]
    title = result["title"] if isinstance(result, dict) else result.title
    assert "Acesso negado" in title


def test_x9_inline_result_builds_target_menu_for_authorized_user() -> None:
    from app.plugins.tigrao_fsm.routers.inline_x9 import build_x9_inline_results

    results = build_x9_inline_results("123 -100456", authorized=True)
    assert len(results) == 1
    result = results[0]
    text = result["text"] if isinstance(result, dict) else result.input_message_content.message_text
    assert "Alvo: 123" in text
    assert "Grupo: -100456" in text

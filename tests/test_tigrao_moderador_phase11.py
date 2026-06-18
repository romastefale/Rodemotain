from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "app/plugins/tigrao_fsm/routers/panel.py"


def _source() -> str:
    return PANEL.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    tree = ast.parse(_source())
    lines = _source().splitlines()
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"function not found: {name}")


def test_phase11_advanced_text_only_prepares_confirmation() -> None:
    body = _function_source("_handle_advanced_text")
    assert 'pending_advanced_action' in body
    assert 'confirm_cancel_keyboard' in body
    # A resposta textual do operador não deve executar efeitos reais diretamente.
    forbidden_direct_calls = [
        'ban_user_custom(',
        'mute_user_custom(',
        'purge_messages(',
        'set_group_lockdown(',
        'set_group_title(',
        'set_group_description(',
        'delete_message_reaction(',
        'delete_all_message_reactions(',
        'pin_message(',
        'unpin_message(',
        'unpin_all_messages(',
    ]
    for call in forbidden_direct_calls:
        assert call not in body


def test_phase11_confirm_executes_advanced_actions_after_button_only() -> None:
    body = _function_source("_confirm_pending_action")
    execute_body = _function_source("_execute_pending_advanced_action")
    assert 'pending_advanced_action' in body
    assert '_execute_pending_advanced_action' in body
    assert 'ban_user_custom(' in execute_body
    assert 'purge_messages(' in execute_body
    assert 'set_group_lockdown(' in execute_body
    assert 'delete_all_message_reactions(' in execute_body


def test_phase11_no_text_destructive_group_actions_require_confirmation() -> None:
    body = _function_source("_prepare_advanced_confirmation")
    assert '{"lock", "unlock", "unpinall"}' in body
    assert 'pending_advanced_action' in body
    assert 'confirm_cancel_keyboard' in body
    assert 'set_group_lockdown(' not in body
    assert 'unpin_all_messages(' not in body


def test_phase11_navigation_back_handler_clears_pending_actions() -> None:
    body = _function_source("_go_back")
    assert 'pending_destructive_action' in body
    assert 'pending_advanced_action' in body
    assert 'nav_back' in body
    assert '_show_actions(callback, session)' in body


def test_phase11_join_pending_is_view_only_not_accept_wait_state() -> None:
    body = _function_source("_join_pending")
    assert 'Aceitar ID pendente' in body
    assert 'session.waiting_for = None' in body
    assert 'session.waiting_for = "join_pending_id"' not in body


def test_phase11_safe_edit_has_fallback_for_stale_or_deleted_panel_message() -> None:
    body = _function_source("_safe_edit")
    assert 'try:' in body
    assert 'edit_text' in body
    assert 'TIGRAO_SAFE_EDIT_FAILED' in body
    assert 'callback.answer()' in body


def test_phase11_purge_accepts_spaced_ranges_for_usability() -> None:
    from app.plugins.tigrao_fsm.parsers import parse_message_ids

    parsed = parse_message_ids("10 - 12, 20")
    assert parsed.error is None
    assert parsed.message_ids == [10, 11, 12, 20]

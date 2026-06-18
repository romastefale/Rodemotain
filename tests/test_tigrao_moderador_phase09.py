from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_allowed_updates_cover_moderation_surfaces() -> None:
    from app.config.settings import ALLOWED_UPDATES

    required = {
        "message",
        "edited_message",
        "callback_query",
        "chat_join_request",
        "chat_member",
        "message_reaction",
        "message_reaction_count",
        "chat_boost",
        "removed_chat_boost",
    }
    assert required.issubset(set(ALLOWED_UPDATES))


def test_permissions_model_reflects_bot_api_101_admin_flags() -> None:
    from app.plugins.tigrao_fsm.permissions import permissions_from_chat_member

    member = SimpleNamespace(
        status="administrator",
        is_anonymous=True,
        can_manage_chat=True,
        can_delete_messages=True,
        can_manage_video_chats=True,
        can_restrict_members=True,
        can_promote_members=True,
        can_change_info=True,
        can_invite_users=True,
        can_post_stories=True,
        can_edit_stories=True,
        can_delete_stories=True,
        can_post_messages=True,
        can_edit_messages=True,
        can_pin_messages=True,
        can_manage_topics=True,
        can_manage_direct_messages=True,
        can_manage_tags=True,
    )
    perms = permissions_from_chat_member(member)
    assert perms.is_admin is True
    assert perms.can_promote_members is True
    assert perms.can_manage_direct_messages is True
    assert perms.can_manage_video_chats is True
    assert perms.can_post_stories is True
    assert perms.can_edit_messages is True


def test_parse_duration_accepts_composite_and_absolute_forms() -> None:
    from app.plugins.tigrao_fsm.parsers import parse_ddx_filter_input, parse_duration

    assert parse_duration("1h30m").duration == timedelta(hours=1, minutes=30)
    assert parse_duration("2d 4h").duration == timedelta(days=2, hours=4)
    assert parse_duration("1 semana").duration == timedelta(days=7)

    parsed = parse_ddx_filter_input("spam | 1h30m")
    assert parsed.filter_text == "spam"
    assert parsed.duration == timedelta(hours=1, minutes=30)

    absolute = parse_duration("até 2099-01-01T00:00:00Z")
    assert absolute.error is None
    assert absolute.until is not None
    assert absolute.duration is not None and absolute.duration.total_seconds() > 0


@pytest.mark.asyncio
async def test_unban_is_safe_only_if_banned() -> None:
    from app.plugins.tigrao_fsm.destructive_actions import DestructiveActionRequest, execute_destructive_action
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions

    class FakeBot:
        def __init__(self) -> None:
            self.kwargs = None

        async def unban_chat_member(self, **kwargs):
            self.kwargs = kwargs

    bot = FakeBot()
    request = DestructiveActionRequest(
        action="unban",
        chat_id=-1001,
        chat_title="Grupo",
        actor_user_id=111,
        target_user_id=222,
        confirmed=True,
    )
    result = await execute_destructive_action(
        bot,
        request,
        permissions=TigraoBotPermissions(is_admin=True, can_restrict_members=True),
        bot_user_id=999,
    )
    assert result.ok is True
    assert bot.kwargs["only_if_banned"] is True


def test_join_request_keyboard_exposes_accept_and_decline_without_duplicate_usage_button() -> None:
    from app.plugins.tigrao_fsm.keyboards import join_requests_keyboard, logs_keyboard

    join_rows = join_requests_keyboard("abc123")
    join_texts = [row[0].text for row in join_rows]
    assert "Aceitar ID pendente" in join_texts
    assert "Recusar ID pendente" in join_texts

    log_rows = logs_keyboard("abc123")
    log_texts = [row[0].text for row in log_rows]
    assert log_texts.count("Uso") == 1


def test_panel_wires_decline_join_request_and_ux_examples_static() -> None:
    panel = read("app/plugins/tigrao_fsm/routers/panel.py")
    assert "decline_pending_join_request" in panel
    assert "join_decline_id" in panel
    assert "1h30m" in panel
    assert "até 2026-07-01T12:00:00Z" in panel

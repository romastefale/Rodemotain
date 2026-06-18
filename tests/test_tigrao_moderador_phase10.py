from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_phase10_keyboard_exposes_new_bot_api_power_actions() -> None:
    from app.plugins.tigrao_fsm.keyboards import destructive_actions_keyboard

    labels = [row[0].text for row in destructive_actions_keyboard("abc123")]
    assert "Banir com tempo livre" in labels
    assert "Mutar com tempo livre" in labels
    assert "Purge 1–100 mensagens" in labels
    assert "Fechar grupo / lockdown" in labels
    assert "Limpar todos os fixados" in labels
    assert "Auditar admins/bots" in labels
    assert "Remover reação de mensagem" in labels


def test_phase10_parsers_accept_custom_moderation_inputs() -> None:
    from app.plugins.tigrao_fsm.parsers import parse_message_ids, parse_reaction_target, parse_timed_user_action

    timed = parse_timed_user_action("123456 | 1h30m")
    assert timed.user_id == 123456
    assert timed.duration == timedelta(hours=1, minutes=30)

    ids = parse_message_ids("10-12, 20")
    assert ids.message_ids == [10, 11, 12, 20]
    assert ids.error is None

    reaction = parse_reaction_target("https://t.me/c/1234567890/55 | 777", selected_chat_id=-1001234567890, require_message=True)
    assert reaction.message_id == 55
    assert reaction.user_id == 777

    actor = parse_reaction_target("chat:-100987", require_message=False)
    assert actor.actor_chat_id == -100987


@pytest.mark.asyncio
async def test_purge_uses_delete_messages_batch_when_available() -> None:
    from app.plugins.tigrao_fsm.advanced_actions import purge_messages
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions

    class FakeBot:
        def __init__(self) -> None:
            self.batch = None

        async def delete_messages(self, **kwargs):
            self.batch = kwargs

    bot = FakeBot()
    result = await purge_messages(
        bot,
        chat_id=-1001,
        chat_title="Grupo",
        actor_user_id=111,
        message_ids=[1, 2, 2, 3],
        permissions=TigraoBotPermissions(is_admin=True, can_delete_messages=True),
    )
    assert result.ok is True
    assert bot.batch == {"chat_id": -1001, "message_ids": [1, 2, 3]}


@pytest.mark.asyncio
async def test_lockdown_uses_set_chat_permissions() -> None:
    from app.plugins.tigrao_fsm.advanced_actions import set_group_lockdown
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions

    class FakeBot:
        def __init__(self) -> None:
            self.kwargs = None

        async def set_chat_permissions(self, **kwargs):
            self.kwargs = kwargs

    bot = FakeBot()
    result = await set_group_lockdown(
        bot,
        chat_id=-1001,
        chat_title="Grupo",
        actor_user_id=111,
        permissions=TigraoBotPermissions(is_admin=True, can_restrict_members=True),
        locked=True,
    )
    assert result.ok is True
    assert bot.kwargs["chat_id"] == -1001
    assert bot.kwargs["use_independent_chat_permissions"] is True


@pytest.mark.asyncio
async def test_reaction_removal_methods_are_wired() -> None:
    from app.plugins.tigrao_fsm.advanced_actions import delete_all_message_reactions, delete_message_reaction
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions

    class FakeBot:
        def __init__(self) -> None:
            self.one = None
            self.all = None

        async def delete_message_reaction(self, **kwargs):
            self.one = kwargs

        async def delete_all_message_reactions(self, **kwargs):
            self.all = kwargs

    bot = FakeBot()
    perms = TigraoBotPermissions(is_admin=True, can_delete_messages=True)
    one = await delete_message_reaction(bot, chat_id=-1001, chat_title="Grupo", actor_user_id=111, message_id=9, user_id=222, actor_chat_id=None, permissions=perms)
    all_result = await delete_all_message_reactions(bot, chat_id=-1001, chat_title="Grupo", actor_user_id=111, user_id=222, actor_chat_id=None, permissions=perms)
    assert one.ok is True
    assert all_result.ok is True
    assert bot.one == {"chat_id": -1001, "message_id": 9, "user_id": 222}
    assert bot.all == {"chat_id": -1001, "user_id": 222}


def test_panel_wires_phase10_callbacks_static() -> None:
    panel = read("app/plugins/tigrao_fsm/routers/panel.py")
    assert "parse_timed_user_action" in panel
    assert "purge_messages" in panel
    assert "set_group_lockdown" in panel
    assert "format_admin_audit" in panel
    assert "delete_all_message_reactions" in panel

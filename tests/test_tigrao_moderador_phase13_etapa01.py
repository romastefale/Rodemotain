from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_etapa01_admin_and_link_parsers() -> None:
    from app.plugins.tigrao_fsm.parsers import (
        parse_admin_role_action,
        parse_admin_title_action,
        parse_invite_create_action,
        parse_invite_edit_action,
        parse_invite_link_ref,
        parse_sender_chat_action,
    )

    promote = parse_admin_role_action("123 | total")
    assert promote.user_id == 123
    assert promote.role == "full"

    custom = parse_admin_role_action("123 | delete, restrict, invite")
    assert custom.role == "custom"
    assert custom.custom_flags and custom.custom_flags["can_delete_messages"] is True
    assert custom.custom_flags["can_restrict_members"] is True
    assert custom.custom_flags["can_invite_users"] is True

    title = parse_admin_title_action("123 | Fiscal")
    assert title.user_id == 123
    assert title.title == "Fiscal"

    sender = parse_sender_chat_action("-100777")
    assert sender.sender_chat_id == -100777

    created = parse_invite_create_action("Entrada | 7d | 50 | não")
    assert created.name == "Entrada"
    assert created.member_limit == 50
    assert created.creates_join_request is False

    request_link = parse_invite_create_action("Entrada | 2h | 999 | sim")
    assert request_link.member_limit is None
    assert request_link.creates_join_request is True

    edited = parse_invite_edit_action("https://t.me/+abcdef | Entrada | 1h | 10 | não")
    assert edited.invite_link == "https://t.me/+abcdef"
    assert edited.create and edited.create.member_limit == 10

    ref = parse_invite_link_ref("https://t.me/+abcdef")
    assert ref.invite_link == "https://t.me/+abcdef"


def test_etapa01_callbacks_registered() -> None:
    from app.plugins.tigrao_fsm.keyboards import CALLBACK_ACTIONS

    for action in (
        "promote",
        "demote",
        "admintitle",
        "bansender",
        "unbansender",
        "linkexport",
        "linkcreate",
        "linkedit",
        "linkrevoke",
    ):
        assert action in CALLBACK_ACTIONS


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def promote_chat_member(self, **kwargs):
        self.calls.append(("promote_chat_member", kwargs))
        return True

    async def set_chat_administrator_custom_title(self, **kwargs):
        self.calls.append(("set_chat_administrator_custom_title", kwargs))
        return True

    async def ban_chat_sender_chat(self, **kwargs):
        self.calls.append(("ban_chat_sender_chat", kwargs))
        return True

    async def unban_chat_sender_chat(self, **kwargs):
        self.calls.append(("unban_chat_sender_chat", kwargs))
        return True

    async def export_chat_invite_link(self, **kwargs):
        self.calls.append(("export_chat_invite_link", kwargs))
        return "https://t.me/+primary"

    async def create_chat_invite_link(self, **kwargs):
        self.calls.append(("create_chat_invite_link", kwargs))
        return SimpleNamespace(invite_link="https://t.me/+created")

    async def edit_chat_invite_link(self, **kwargs):
        self.calls.append(("edit_chat_invite_link", kwargs))
        return SimpleNamespace(invite_link="https://t.me/+edited")

    async def revoke_chat_invite_link(self, **kwargs):
        self.calls.append(("revoke_chat_invite_link", kwargs))
        return SimpleNamespace(invite_link=kwargs["invite_link"])


@pytest.mark.asyncio
async def test_etapa01_advanced_actions_call_real_bot_methods() -> None:
    from app.plugins.tigrao_fsm.advanced_actions import (
        ban_sender_chat,
        create_invite_link_full,
        demote_user_admin,
        edit_invite_link_full,
        export_primary_invite_link,
        promote_user_admin,
        revoke_invite_link_full,
        set_admin_custom_title,
        unban_sender_chat,
    )
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions

    bot = FakeBot()
    perms = TigraoBotPermissions(is_admin=True, can_promote_members=True, can_restrict_members=True, can_invite_users=True)

    await promote_user_admin(bot, chat_id=-1001, chat_title="G", actor_user_id=1, user_id=2, permissions=perms, role="full")
    assert bot.calls[-1][0] == "promote_chat_member"
    assert bot.calls[-1][1]["can_promote_members"] is True

    await demote_user_admin(bot, chat_id=-1001, chat_title="G", actor_user_id=1, user_id=2, permissions=perms)
    assert bot.calls[-1][0] == "promote_chat_member"
    assert all(v is False for k, v in bot.calls[-1][1].items() if k.startswith("can_"))

    await set_admin_custom_title(bot, chat_id=-1001, chat_title="G", actor_user_id=1, user_id=2, custom_title="Fiscal", permissions=perms)
    assert bot.calls[-1][0] == "set_chat_administrator_custom_title"

    await ban_sender_chat(bot, chat_id=-1001, chat_title="G", actor_user_id=1, sender_chat_id=-1002, permissions=perms)
    assert bot.calls[-1][0] == "ban_chat_sender_chat"

    await unban_sender_chat(bot, chat_id=-1001, chat_title="G", actor_user_id=1, sender_chat_id=-1002, permissions=perms)
    assert bot.calls[-1][0] == "unban_chat_sender_chat"

    await export_primary_invite_link(bot, chat_id=-1001, chat_title="G", actor_user_id=1, permissions=perms)
    assert bot.calls[-1][0] == "export_chat_invite_link"

    await create_invite_link_full(bot, chat_id=-1001, chat_title="G", actor_user_id=1, permissions=perms, name="Entrada", duration=None, member_limit=10, creates_join_request=False)
    assert bot.calls[-1][0] == "create_chat_invite_link"
    assert bot.calls[-1][1]["member_limit"] == 10

    await edit_invite_link_full(bot, chat_id=-1001, chat_title="G", actor_user_id=1, permissions=perms, invite_link="https://t.me/+abc", name="Entrada", duration=None, member_limit=None, creates_join_request=True)
    assert bot.calls[-1][0] == "edit_chat_invite_link"
    assert bot.calls[-1][1]["creates_join_request"] is True

    await revoke_invite_link_full(bot, chat_id=-1001, chat_title="G", actor_user_id=1, permissions=perms, invite_link="https://t.me/+abc")
    assert bot.calls[-1][0] == "revoke_chat_invite_link"

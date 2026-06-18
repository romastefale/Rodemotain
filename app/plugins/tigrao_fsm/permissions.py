"""Permissões e superfície do painel isolado do Tigrão FSM."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


def is_authorized_user(user_id: int | None, *, owner_ids: Iterable[int] = (), moderator_ids: Iterable[int] = ()) -> bool:
    if user_id is None:
        return False
    return int(user_id) in {int(v) for v in owner_ids} | {int(v) for v in moderator_ids}


def is_private_panel_surface(chat_type: str | None) -> bool:
    return chat_type == "private"


@dataclass(frozen=True, slots=True)
class TigraoBotPermissions:
    """Espelho defensivo dos direitos administrativos atuais do Bot API.

    Nem todo direito já possui função operacional no painel; manter o espelho
    completo evita diagnóstico falso quando o Telegram/aiogram entregam flags
    recentes como can_manage_direct_messages ou can_manage_tags.
    """

    is_admin: bool = False
    is_anonymous: bool = False
    can_manage_chat: bool = False
    can_delete_messages: bool = False
    can_manage_video_chats: bool = False
    can_restrict_members: bool = False
    can_promote_members: bool = False
    can_change_info: bool = False
    can_invite_users: bool = False
    can_post_stories: bool = False
    can_edit_stories: bool = False
    can_delete_stories: bool = False
    can_post_messages: bool = False
    can_edit_messages: bool = False
    can_pin_messages: bool = False
    can_manage_topics: bool = False
    can_manage_direct_messages: bool = False
    can_manage_tags: bool = False

    @property
    def can_manage_user_actions(self) -> bool:
        return self.can_restrict_members

    @property
    def can_manage_links_and_join_approval(self) -> bool:
        return self.can_invite_users

    @property
    def can_delete_link_or_ddx_messages(self) -> bool:
        return self.can_delete_messages

    @property
    def can_manage_reactions(self) -> bool:
        return self.can_delete_messages


def _flag(member: Any, name: str) -> bool:
    return bool(getattr(member, name, False))


def permissions_from_chat_member(member: Any) -> TigraoBotPermissions:
    status = getattr(member, "status", None)
    status_value = getattr(status, "value", status)
    is_admin = status_value in {"administrator", "creator"}
    # O creator normalmente não carrega todas as flags bool; para fins de
    # diagnóstico operacional, creator equivale a autorização administrativa.
    is_creator = status_value == "creator"

    def value(name: str) -> bool:
        return True if is_creator else _flag(member, name)

    return TigraoBotPermissions(
        is_admin=is_admin,
        is_anonymous=value("is_anonymous"),
        can_manage_chat=value("can_manage_chat"),
        can_delete_messages=value("can_delete_messages"),
        can_manage_video_chats=value("can_manage_video_chats"),
        can_restrict_members=value("can_restrict_members"),
        can_promote_members=value("can_promote_members"),
        can_change_info=value("can_change_info"),
        can_invite_users=value("can_invite_users"),
        can_post_stories=value("can_post_stories"),
        can_edit_stories=value("can_edit_stories"),
        can_delete_stories=value("can_delete_stories"),
        can_post_messages=value("can_post_messages"),
        can_edit_messages=value("can_edit_messages"),
        can_pin_messages=value("can_pin_messages"),
        can_manage_topics=value("can_manage_topics"),
        can_manage_direct_messages=value("can_manage_direct_messages"),
        can_manage_tags=value("can_manage_tags"),
    )


async def get_bot_permissions(bot: Any, chat_id: int) -> TigraoBotPermissions:
    me = await bot.get_me()
    member = await bot.get_chat_member(chat_id, me.id)
    return permissions_from_chat_member(member)

"""Runtime anti-flood do Tigrão Moderador."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from aiogram.types import ChatPermissions as _AiogramChatPermissions
except Exception:  # pragma: no cover - fallback para testes/ambiente sem aiogram instalado
    _AiogramChatPermissions = None

from .. import storage
from ..permissions import get_bot_permissions

_BUCKETS: dict[tuple[int, int], deque[datetime]] = defaultdict(deque)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _chat_type(chat: Any) -> str | None:
    value = getattr(chat, "type", None)
    value = getattr(value, "value", value)
    return str(value) if value is not None else None


def _mute_permissions() -> Any:
    payload = {
        "can_send_messages": False,
        "can_send_audios": False,
        "can_send_documents": False,
        "can_send_photos": False,
        "can_send_videos": False,
        "can_send_video_notes": False,
        "can_send_voice_notes": False,
        "can_send_polls": False,
        "can_send_other_messages": False,
        "can_add_web_page_previews": False,
        "can_react_to_messages": False,
    }
    if _AiogramChatPermissions is not None:
        return _AiogramChatPermissions(**payload)
    return payload


async def handle(bot: Any, update: Any) -> bool:
    message = getattr(update, "message", None)
    if message is None:
        return False
    chat = getattr(message, "chat", None)
    user = getattr(message, "from_user", None)
    if chat is None or user is None or _chat_type(chat) not in {"group", "supergroup"}:
        return False
    chat_id = int(getattr(chat, "id"))
    user_id = int(getattr(user, "id"))
    if bool(getattr(user, "is_bot", False)):
        return False
    setting = storage.get_protection_setting(chat_id=chat_id, name="anti_flood")
    if not setting.get("enabled"):
        return False
    config = setting.get("config") or {}
    limit = int(config.get("limit") or 5)
    window_seconds = int(config.get("window_seconds") or 10)
    mute_seconds = int(config.get("mute_seconds") or 600)
    now = _utcnow()
    bucket = _BUCKETS[(chat_id, user_id)]
    cutoff = now - timedelta(seconds=window_seconds)
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    bucket.append(now)
    if len(bucket) <= limit:
        return False
    try:
        perms = await get_bot_permissions(bot, chat_id)
    except Exception:
        perms = None
    title = getattr(chat, "title", None) or str(chat_id)
    if perms and perms.is_admin and perms.can_delete_messages and bool(config.get("delete", True)):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=int(getattr(message, "message_id")))
        except Exception:
            pass
    if perms and perms.is_admin and perms.can_restrict_members:
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=_mute_permissions(),
                until_date=now + timedelta(seconds=mute_seconds),
                use_independent_chat_permissions=True,
            )
        except Exception:
            pass
    storage.log_event(
        action="anti_flood",
        result="acionado",
        detection="automatica",
        surface="message",
        chat_id=chat_id,
        chat_title=title,
        actor_user_id=user_id,
        target_user_id=user_id,
        details=f"Flood detectado: {len(bucket)} mensagens em {window_seconds}s. Mute: {mute_seconds}s.",
        metadata={"limit": limit, "window_seconds": window_seconds, "mute_seconds": mute_seconds},
    )
    return True

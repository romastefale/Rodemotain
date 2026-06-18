from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db.database import engine


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_tables() -> None:
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS tigrao_groups (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                username TEXT,
                chat_type TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
            """
        ))


def _chat_type_value(chat_type: Any | None) -> str | None:
    value = getattr(chat_type, "value", chat_type)
    return str(value) if value is not None else None


def remember_group(*, chat_id: int, title: str | None = None, username: str | None = None, chat_type: str | None = None) -> None:
    chat_type = _chat_type_value(chat_type)
    if chat_type not in {"group", "supergroup"}:
        return
    ensure_tables()
    now = utcnow().isoformat()
    with engine.begin() as conn:
        conn.execute(text(
            """
            INSERT INTO tigrao_groups (chat_id, title, username, chat_type, first_seen, last_seen)
            VALUES (:chat_id, :title, :username, :chat_type, :now, :now)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = COALESCE(excluded.title, tigrao_groups.title),
                username = COALESCE(excluded.username, tigrao_groups.username),
                chat_type = COALESCE(excluded.chat_type, tigrao_groups.chat_type),
                last_seen = excluded.last_seen
            """
        ), {"chat_id": int(chat_id), "title": title, "username": username, "chat_type": chat_type, "now": now})


def _chat_from_obj(obj: Any) -> Any | None:
    if obj is None:
        return None
    chat = getattr(obj, "chat", None)
    if chat is not None:
        return chat
    message = getattr(obj, "message", None)
    if message is not None:
        return getattr(message, "chat", None)
    return None


def remember_chat_from_update(update: Any) -> None:
    for attr in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
        "chat_join_request",
        "my_chat_member",
        "chat_member",
        "message_reaction",
        "message_reaction_count",
        "chat_boost",
        "removed_chat_boost",
    ):
        obj = getattr(update, attr, None)
        chat = _chat_from_obj(obj)
        if chat is None:
            continue
        try:
            remember_group(
                chat_id=int(getattr(chat, "id")),
                title=getattr(chat, "title", None),
                username=getattr(chat, "username", None),
                chat_type=getattr(chat, "type", None),
            )
        except Exception:
            continue


def list_groups(limit: int = 50) -> list[dict[str, Any]]:
    ensure_tables()
    with engine.begin() as conn:
        rows = conn.execute(text(
            """
            SELECT chat_id, title, username, chat_type, last_seen
            FROM tigrao_groups
            ORDER BY last_seen DESC
            LIMIT :limit
            """
        ), {"limit": int(limit)}).mappings().all()
    return [dict(row) for row in rows]

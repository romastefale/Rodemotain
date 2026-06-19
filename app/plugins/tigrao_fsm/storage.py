"""Storage persistente do Tigrão FSM.

Fase 4: logs, solicitações de entrada e autoaceite por IDs.
Usa o engine SQLite já existente do TR4 e mantém tudo isolado no plugin.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import text

from app.db.database import engine

from .models import JOIN_REQUEST_TTL, TigraoJoinAutoAccept, TigraoJoinRequest

PENDING = "pendente"
APPROVED = "aprovado"
DECLINED = "recusado"
FAILED = "falhou"
EXPIRED = "expirado"
WAITING_REQUEST = "aguardando_solicitação"
CANCELLED = "cancelado"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _json_safe(value: Any) -> Any:
    """Normaliza metadados para JSON antes de gravar no SQLite.

    Objetos retornados pela Bot API/aiogram podem conter datetime, timedelta,
    modelos Pydantic e outros tipos que ``json.dumps`` puro não serializa.
    Log não pode derrubar a ação real do bot; por isso os valores não JSON são
    convertidos para ISO/repr de forma previsível.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return _to_iso(value)
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in list(value)]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _json_safe(model_dump())
        except Exception:
            pass
    data = getattr(value, "__dict__", None)
    if isinstance(data, dict):
        try:
            return _json_safe(data)
        except Exception:
            pass
    return repr(value)


def _metadata_json(metadata: dict[str, Any] | None) -> str:
    return json.dumps(_json_safe(metadata or {}), ensure_ascii=False)


def ensure_tables() -> None:
    """Cria as tabelas tigrao_* de forma idempotente."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tigrao_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                chat_id INTEGER,
                chat_title TEXT,
                actor_user_id INTEGER,
                actor_username TEXT,
                actor_full_name TEXT,
                target_user_id INTEGER,
                target_username TEXT,
                target_full_name TEXT,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                detection TEXT NOT NULL,
                surface TEXT NOT NULL,
                details TEXT,
                metadata_json TEXT
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tigrao_logs_chat_created ON tigrao_logs(chat_id, created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tigrao_logs_action ON tigrao_logs(action)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tigrao_join_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                chat_title TEXT,
                user_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT,
                user_chat_id INTEGER,
                bio TEXT,
                invite_link TEXT,
                request_date TEXT NOT NULL,
                received_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL,
                processed_at TEXT,
                processed_by INTEGER,
                result_detail TEXT,
                query_id TEXT
            )
        """))
        try:
            conn.execute(text("ALTER TABLE tigrao_join_requests ADD COLUMN query_id TEXT"))
        except Exception:
            pass
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tigrao_join_requests_lookup ON tigrao_join_requests(chat_id, user_id, status, received_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tigrao_join_requests_query ON tigrao_join_requests(query_id, status)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tigrao_join_auto_accept (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                chat_title TEXT,
                invite_link TEXT,
                allowed_user_id INTEGER NOT NULL,
                allowed_username TEXT,
                allowed_full_name TEXT,
                created_by_owner_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL,
                approved_at TEXT,
                result_detail TEXT
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tigrao_join_auto_accept_lookup ON tigrao_join_auto_accept(chat_id, allowed_user_id, status, expires_at)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tigrao_ddx_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                filter_text TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT
            )
        """))
        # Migração idempotente para bancos criados antes da Fase 08.
        try:
            conn.execute(text("ALTER TABLE tigrao_ddx_filters ADD COLUMN expires_at TEXT"))
        except Exception:
            pass
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tigrao_ddx_filters_chat_enabled ON tigrao_ddx_filters(chat_id, enabled)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tigrao_ddx_filters_expires ON tigrao_ddx_filters(expires_at)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tigrao_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                chat_title TEXT,
                user_id INTEGER NOT NULL,
                reason TEXT,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tigrao_warnings_lookup ON tigrao_warnings(chat_id, user_id, active, created_at)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tigrao_protection_settings (
                chat_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                config_json TEXT,
                updated_by INTEGER,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, name)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tigrao_captcha_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                chat_title TEXT,
                user_id INTEGER NOT NULL,
                user_chat_id INTEGER,
                code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                processed_at TEXT
            )
        """))
        try:
            conn.execute(text("ALTER TABLE tigrao_captcha_challenges ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3"))
        except Exception:
            pass
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tigrao_captcha_lookup ON tigrao_captcha_challenges(user_id, code, status, expires_at)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tigrao_recent_messages (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                chat_title TEXT,
                sender_user_id INTEGER,
                sender_username TEXT,
                sender_full_name TEXT,
                message_text TEXT,
                message_date TEXT,
                saved_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tigrao_recent_messages_chat ON tigrao_recent_messages(chat_id, message_id)"))


def log_event(
    *,
    action: str,
    result: str,
    detection: str,
    surface: str,
    chat_id: int | None = None,
    chat_title: str | None = None,
    actor_user_id: int | None = None,
    actor_username: str | None = None,
    actor_full_name: str | None = None,
    target_user_id: int | None = None,
    target_username: str | None = None,
    target_full_name: str | None = None,
    details: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    ensure_tables()
    created_at = _to_iso(utcnow())
    with engine.begin() as conn:
        result_obj = conn.execute(
            text("""
                INSERT INTO tigrao_logs (
                    created_at, chat_id, chat_title, actor_user_id, actor_username,
                    actor_full_name, target_user_id, target_username, target_full_name,
                    action, result, detection, surface, details, metadata_json
                ) VALUES (
                    :created_at, :chat_id, :chat_title, :actor_user_id, :actor_username,
                    :actor_full_name, :target_user_id, :target_username, :target_full_name,
                    :action, :result, :detection, :surface, :details, :metadata_json
                )
            """),
            {
                "created_at": created_at,
                "chat_id": chat_id,
                "chat_title": chat_title,
                "actor_user_id": actor_user_id,
                "actor_username": actor_username,
                "actor_full_name": actor_full_name,
                "target_user_id": target_user_id,
                "target_username": target_username,
                "target_full_name": target_full_name,
                "action": action,
                "result": result,
                "detection": detection,
                "surface": surface,
                "details": details,
                "metadata_json": _metadata_json(metadata),
            },
        )
        return int(getattr(result_obj, "lastrowid", 0) or 0)


def list_logs(*, chat_id: int | None = None, limit: int = 10, action_prefix: str | None = None) -> list[dict[str, Any]]:
    ensure_tables()
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": int(limit)}
    if chat_id is not None:
        clauses.append("chat_id = :chat_id")
        params["chat_id"] = int(chat_id)
    if action_prefix:
        clauses.append("action LIKE :action_prefix")
        params["action_prefix"] = f"{action_prefix}%"
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with engine.begin() as conn:
        rows = conn.execute(
            text(f"""
                SELECT * FROM tigrao_logs
                {where}
                ORDER BY id DESC
                LIMIT :limit
            """),
            params,
        ).mappings().all()
    return [dict(row) for row in rows]


def save_join_request(request: TigraoJoinRequest) -> int:
    ensure_tables()
    with engine.begin() as conn:
        result_obj = conn.execute(
            text("""
                INSERT INTO tigrao_join_requests (
                    chat_id, chat_title, user_id, username, full_name, user_chat_id, bio,
                    invite_link, request_date, received_at, expires_at, status,
                    processed_at, processed_by, result_detail, query_id
                ) VALUES (
                    :chat_id, :chat_title, :user_id, :username, :full_name, :user_chat_id, :bio,
                    :invite_link, :request_date, :received_at, :expires_at, :status,
                    :processed_at, :processed_by, :result_detail, :query_id
                )
            """),
            {
                "chat_id": int(request.chat_id),
                "chat_title": request.chat_title,
                "user_id": int(request.user_id),
                "username": request.username,
                "full_name": request.full_name,
                "user_chat_id": int(request.user_chat_id) if request.user_chat_id is not None else None,
                "bio": request.bio,
                "invite_link": request.invite_link,
                "request_date": _to_iso(request.request_date),
                "received_at": _to_iso(request.received_at),
                "expires_at": _to_iso(request.expires_at),
                "status": request.status,
                "processed_at": _to_iso(request.processed_at),
                "processed_by": request.processed_by,
                "result_detail": request.result_detail,
                "query_id": request.query_id,
            },
        )
        return int(getattr(result_obj, "lastrowid", 0) or 0)


def _request_from_row(row: dict[str, Any]) -> TigraoJoinRequest:
    return TigraoJoinRequest(
        chat_id=int(row["chat_id"]),
        chat_title=row.get("chat_title") or str(row["chat_id"]),
        user_id=int(row["user_id"]),
        username=row.get("username"),
        full_name=row.get("full_name") or "User",
        user_chat_id=int(row["user_chat_id"]) if row.get("user_chat_id") is not None else None,
        bio=row.get("bio"),
        invite_link=row.get("invite_link"),
        request_date=_from_iso(row.get("request_date")) or utcnow(),
        received_at=_from_iso(row.get("received_at")) or utcnow(),
        expires_at=_from_iso(row.get("expires_at")) or utcnow(),
        status=row.get("status") or PENDING,
        processed_at=_from_iso(row.get("processed_at")),
        processed_by=int(row["processed_by"]) if row.get("processed_by") is not None else None,
        result_detail=row.get("result_detail"),
        query_id=row.get("query_id"),
    )


def find_pending_join_request_by_query_id(*, query_id: str, now: datetime | None = None) -> TigraoJoinRequest | None:
    ensure_tables()
    query_id = str(query_id or "").strip()
    if not query_id:
        return None
    now = now or utcnow()
    cutoff = now - JOIN_REQUEST_TTL
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT * FROM tigrao_join_requests
                WHERE query_id=:query_id AND status=:status AND received_at>=:cutoff
                ORDER BY id DESC
                LIMIT 1
            """),
            {"query_id": query_id, "status": PENDING, "cutoff": _to_iso(cutoff)},
        ).mappings().first()
    return _request_from_row(dict(row)) if row else None


def find_pending_join_request(*, chat_id: int, user_id: int, now: datetime | None = None) -> TigraoJoinRequest | None:
    ensure_tables()
    now = now or utcnow()
    cutoff = now - JOIN_REQUEST_TTL
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT * FROM tigrao_join_requests
                WHERE chat_id=:chat_id AND user_id=:user_id AND status=:status AND received_at>=:cutoff
                ORDER BY id DESC
                LIMIT 1
            """),
            {"chat_id": int(chat_id), "user_id": int(user_id), "status": PENDING, "cutoff": _to_iso(cutoff)},
        ).mappings().first()
    return _request_from_row(dict(row)) if row else None


def list_pending_join_requests(*, chat_id: int, limit: int = 10, now: datetime | None = None) -> list[TigraoJoinRequest]:
    ensure_tables()
    now = now or utcnow()
    cutoff = now - JOIN_REQUEST_TTL
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT * FROM tigrao_join_requests
                WHERE chat_id=:chat_id AND status=:status AND received_at>=:cutoff
                ORDER BY id DESC
                LIMIT :limit
            """),
            {"chat_id": int(chat_id), "status": PENDING, "cutoff": _to_iso(cutoff), "limit": int(limit)},
        ).mappings().all()
    return [_request_from_row(dict(row)) for row in rows]


def update_join_request_status(request: TigraoJoinRequest) -> None:
    ensure_tables()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tigrao_join_requests
                SET status=:status, processed_at=:processed_at, processed_by=:processed_by, result_detail=:result_detail
                WHERE chat_id=:chat_id AND user_id=:user_id AND request_date=:request_date
            """),
            {
                "status": request.status,
                "processed_at": _to_iso(request.processed_at),
                "processed_by": request.processed_by,
                "result_detail": request.result_detail,
                "chat_id": int(request.chat_id),
                "user_id": int(request.user_id),
                "request_date": _to_iso(request.request_date),
            },
        )


def create_auto_accept_records(
    *,
    chat_id: int,
    chat_title: str,
    invite_link: str,
    user_ids: Iterable[int],
    created_by_owner_id: int,
    created_at: datetime | None = None,
) -> list[TigraoJoinAutoAccept]:
    ensure_tables()
    created_at = created_at or utcnow()
    expires_at = created_at + JOIN_REQUEST_TTL
    records = [
        TigraoJoinAutoAccept(
            chat_id=int(chat_id),
            chat_title=chat_title,
            invite_link=invite_link,
            allowed_user_id=int(user_id),
            allowed_username=None,
            allowed_full_name=None,
            created_by_owner_id=int(created_by_owner_id),
            created_at=created_at,
            expires_at=expires_at,
        )
        for user_id in user_ids
    ]
    with engine.begin() as conn:
        for record in records:
            conn.execute(
                text("""
                    INSERT INTO tigrao_join_auto_accept (
                        chat_id, chat_title, invite_link, allowed_user_id, allowed_username,
                        allowed_full_name, created_by_owner_id, created_at, expires_at,
                        status, approved_at, result_detail
                    ) VALUES (
                        :chat_id, :chat_title, :invite_link, :allowed_user_id, :allowed_username,
                        :allowed_full_name, :created_by_owner_id, :created_at, :expires_at,
                        :status, :approved_at, :result_detail
                    )
                """),
                {
                    "chat_id": record.chat_id,
                    "chat_title": record.chat_title,
                    "invite_link": record.invite_link,
                    "allowed_user_id": record.allowed_user_id,
                    "allowed_username": record.allowed_username,
                    "allowed_full_name": record.allowed_full_name,
                    "created_by_owner_id": record.created_by_owner_id,
                    "created_at": _to_iso(record.created_at),
                    "expires_at": _to_iso(record.expires_at),
                    "status": record.status,
                    "approved_at": _to_iso(record.approved_at),
                    "result_detail": record.result_detail,
                },
            )
    return records


def _auto_from_row(row: dict[str, Any]) -> TigraoJoinAutoAccept:
    return TigraoJoinAutoAccept(
        chat_id=int(row["chat_id"]),
        chat_title=row.get("chat_title") or str(row["chat_id"]),
        invite_link=row.get("invite_link") or "",
        allowed_user_id=int(row["allowed_user_id"]),
        allowed_username=row.get("allowed_username"),
        allowed_full_name=row.get("allowed_full_name"),
        created_by_owner_id=int(row["created_by_owner_id"]),
        created_at=_from_iso(row.get("created_at")) or utcnow(),
        expires_at=_from_iso(row.get("expires_at")) or utcnow(),
        status=row.get("status") or WAITING_REQUEST,
        approved_at=_from_iso(row.get("approved_at")),
        result_detail=row.get("result_detail"),
    )


def get_active_auto_accept(*, chat_id: int, user_id: int, now: datetime | None = None) -> TigraoJoinAutoAccept | None:
    ensure_tables()
    now = now or utcnow()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT * FROM tigrao_join_auto_accept
                WHERE chat_id=:chat_id AND allowed_user_id=:user_id AND status=:status AND expires_at>=:now
                ORDER BY id DESC
                LIMIT 1
            """),
            {"chat_id": int(chat_id), "user_id": int(user_id), "status": WAITING_REQUEST, "now": _to_iso(now)},
        ).mappings().first()
    return _auto_from_row(dict(row)) if row else None


def update_auto_accept_status(record: TigraoJoinAutoAccept) -> None:
    ensure_tables()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tigrao_join_auto_accept
                SET status=:status, approved_at=:approved_at, result_detail=:result_detail
                WHERE chat_id=:chat_id AND allowed_user_id=:allowed_user_id
                  AND created_by_owner_id=:created_by_owner_id AND created_at=:created_at
            """),
            {
                "status": record.status,
                "approved_at": _to_iso(record.approved_at),
                "result_detail": record.result_detail,
                "chat_id": int(record.chat_id),
                "allowed_user_id": int(record.allowed_user_id),
                "created_by_owner_id": int(record.created_by_owner_id),
                "created_at": _to_iso(record.created_at),
            },
        )


def list_auto_accepts(*, chat_id: int, limit: int = 10, now: datetime | None = None) -> list[TigraoJoinAutoAccept]:
    ensure_tables()
    now = now or utcnow()
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT * FROM tigrao_join_auto_accept
                WHERE chat_id=:chat_id AND expires_at>=:now
                ORDER BY id DESC
                LIMIT :limit
            """),
            {"chat_id": int(chat_id), "now": _to_iso(now), "limit": int(limit)},
        ).mappings().all()
    return [_auto_from_row(dict(row)) for row in rows]


def create_ddx_filter(
    *,
    chat_id: int,
    filter_text: str,
    created_by: int,
    enabled: bool = True,
    duration: timedelta | None = None,
    created_at: datetime | None = None,
) -> int:
    ensure_tables()
    normalized = str(filter_text or "").strip()
    if not normalized:
        raise ValueError("filter_text obrigatório")
    created_at = created_at or utcnow()
    expires_at = created_at + duration if duration is not None else None
    with engine.begin() as conn:
        result_obj = conn.execute(
            text("""
                INSERT INTO tigrao_ddx_filters (chat_id, filter_text, created_by, created_at, enabled, expires_at)
                VALUES (:chat_id, :filter_text, :created_by, :created_at, :enabled, :expires_at)
            """),
            {
                "chat_id": int(chat_id),
                "filter_text": normalized,
                "created_by": int(created_by),
                "created_at": _to_iso(created_at),
                "enabled": 1 if enabled else 0,
                "expires_at": _to_iso(expires_at),
            },
        )
        return int(getattr(result_obj, "lastrowid", 0) or 0)


def list_ddx_filters(*, chat_id: int, enabled_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    ensure_tables()
    clauses = ["chat_id=:chat_id"]
    params: dict[str, Any] = {"chat_id": int(chat_id), "limit": int(limit)}
    if enabled_only:
        clauses.append("enabled=1")
        clauses.append("(expires_at IS NULL OR expires_at>=:now)")
        params["now"] = _to_iso(utcnow())
    where = " AND ".join(clauses)
    with engine.begin() as conn:
        rows = conn.execute(
            text(f"""
                SELECT * FROM tigrao_ddx_filters
                WHERE {where}
                ORDER BY id DESC
                LIMIT :limit
            """),
            params,
        ).mappings().all()
    return [dict(row) for row in rows]


def get_enabled_ddx_filters(*, chat_id: int) -> list[str]:
    return [str(row.get("filter_text") or "") for row in list_ddx_filters(chat_id=chat_id, enabled_only=True, limit=100) if row.get("filter_text")]


def set_ddx_enabled(*, chat_id: int, enabled: bool) -> int:
    ensure_tables()
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE tigrao_ddx_filters SET enabled=:enabled WHERE chat_id=:chat_id"),
            {"enabled": 1 if enabled else 0, "chat_id": int(chat_id)},
        )
        return int(getattr(result, "rowcount", 0) or 0)


def remove_ddx_filter(*, chat_id: int, filter_id: int) -> int:
    ensure_tables()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM tigrao_ddx_filters WHERE chat_id=:chat_id AND id=:filter_id"),
            {"chat_id": int(chat_id), "filter_id": int(filter_id)},
        )
        return int(getattr(result, "rowcount", 0) or 0)



# ---------- Mensagens recentes para ações contextuais ----------

def _chat_type_value(chat: Any) -> str | None:
    value = getattr(chat, "type", None)
    value = getattr(value, "value", value)
    return str(value) if value is not None else None


def _full_name_from_user(user: Any) -> str | None:
    if user is None:
        return None
    full = getattr(user, "full_name", None)
    if full:
        return str(full)
    first = str(getattr(user, "first_name", "") or "").strip()
    last = str(getattr(user, "last_name", "") or "").strip()
    name = " ".join(part for part in (first, last) if part).strip()
    return name or None


def remember_recent_message(message: Any) -> None:
    """Guarda resumo das últimas mensagens de grupo para prompts do painel.

    O painel por DM não tem acesso visual ao histórico do grupo. Este cache
    pequeno permite mostrar os 5 últimos IDs úteis quando uma ação depende de
    message_id/link, especialmente reações e apagamento.
    """
    chat = getattr(message, "chat", None)
    if _chat_type_value(chat) not in {"group", "supergroup"}:
        return
    try:
        chat_id = int(getattr(chat, "id"))
        message_id = int(getattr(message, "message_id"))
    except Exception:
        return
    user = getattr(message, "from_user", None)
    text_value = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    text_value = str(text_value or "").replace("\x00", "").strip()
    if len(text_value) > 300:
        text_value = text_value[:297] + "..."
    message_date = getattr(message, "date", None)
    if isinstance(message_date, datetime):
        if message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)
        message_date_iso = message_date.isoformat()
    else:
        message_date_iso = None
    ensure_tables()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO tigrao_recent_messages (
                chat_id, message_id, chat_title, sender_user_id, sender_username,
                sender_full_name, message_text, message_date, saved_at
            ) VALUES (
                :chat_id, :message_id, :chat_title, :sender_user_id, :sender_username,
                :sender_full_name, :message_text, :message_date, :saved_at
            )
            ON CONFLICT(chat_id, message_id) DO UPDATE SET
                chat_title=excluded.chat_title,
                sender_user_id=excluded.sender_user_id,
                sender_username=excluded.sender_username,
                sender_full_name=excluded.sender_full_name,
                message_text=excluded.message_text,
                message_date=excluded.message_date,
                saved_at=excluded.saved_at
        """), {
            "chat_id": chat_id,
            "message_id": message_id,
            "chat_title": getattr(chat, "title", None),
            "sender_user_id": int(getattr(user, "id")) if getattr(user, "id", None) is not None else None,
            "sender_username": getattr(user, "username", None),
            "sender_full_name": _full_name_from_user(user),
            "message_text": text_value,
            "message_date": message_date_iso,
            "saved_at": _to_iso(utcnow()),
        })
        # Mantém o cache pequeno por grupo.
        conn.execute(text("""
            DELETE FROM tigrao_recent_messages
            WHERE chat_id=:chat_id AND message_id NOT IN (
                SELECT message_id FROM tigrao_recent_messages
                WHERE chat_id=:chat_id
                ORDER BY message_id DESC
                LIMIT 50
            )
        """), {"chat_id": chat_id})


def remember_recent_message_from_update(update: Any) -> None:
    for attr in ("message", "edited_message"):
        message = getattr(update, attr, None)
        if message is not None:
            remember_recent_message(message)


def list_recent_messages(*, chat_id: int, limit: int = 5) -> list[dict[str, Any]]:
    ensure_tables()
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT * FROM tigrao_recent_messages
            WHERE chat_id=:chat_id
            ORDER BY message_id DESC
            LIMIT :limit
        """), {"chat_id": int(chat_id), "limit": int(limit)}).mappings().all()
    return [dict(row) for row in rows]

# ---------- Warnings / reincidência ----------

def add_warning(*, chat_id: int, chat_title: str | None, user_id: int, reason: str | None, created_by: int) -> int:
    ensure_tables()
    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO tigrao_warnings (chat_id, chat_title, user_id, reason, created_by, created_at, active)
            VALUES (:chat_id, :chat_title, :user_id, :reason, :created_by, :created_at, 1)
        """), {"chat_id": int(chat_id), "chat_title": chat_title, "user_id": int(user_id), "reason": reason, "created_by": int(created_by), "created_at": _to_iso(utcnow())})
        return int(getattr(result, "lastrowid", 0) or 0)


def list_warnings(*, chat_id: int, user_id: int | None = None, active_only: bool = True, limit: int = 20) -> list[dict[str, Any]]:
    ensure_tables()
    clauses = ["chat_id=:chat_id"]
    params: dict[str, Any] = {"chat_id": int(chat_id), "limit": int(limit)}
    if user_id is not None:
        clauses.append("user_id=:user_id")
        params["user_id"] = int(user_id)
    if active_only:
        clauses.append("active=1")
    with engine.begin() as conn:
        rows = conn.execute(text(f"""
            SELECT * FROM tigrao_warnings
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            LIMIT :limit
        """), params).mappings().all()
    return [dict(row) for row in rows]


def count_warnings(*, chat_id: int, user_id: int) -> int:
    ensure_tables()
    with engine.begin() as conn:
        value = conn.execute(text("""
            SELECT COUNT(*) FROM tigrao_warnings WHERE chat_id=:chat_id AND user_id=:user_id AND active=1
        """), {"chat_id": int(chat_id), "user_id": int(user_id)}).scalar()
    return int(value or 0)


def clear_warnings(*, chat_id: int, user_id: int | None = None) -> int:
    ensure_tables()
    clauses = ["chat_id=:chat_id", "active=1"]
    params: dict[str, Any] = {"chat_id": int(chat_id)}
    if user_id is not None:
        clauses.append("user_id=:user_id")
        params["user_id"] = int(user_id)
    with engine.begin() as conn:
        result = conn.execute(text(f"UPDATE tigrao_warnings SET active=0 WHERE {' AND '.join(clauses)}"), params)
        return int(getattr(result, "rowcount", 0) or 0)


# ---------- Proteções automáticas ----------
_DEFAULT_PROTECTION_CONFIG: dict[str, dict[str, Any]] = {
    "anti_flood": {"limit": 5, "window_seconds": 10, "mute_seconds": 600, "delete": True},
    "anti_raid": {"limit": 5, "window_seconds": 60, "action": "queue"},
    "captcha": {"ttl_seconds": 300, "max_attempts": 3},
}


def set_protection_setting(*, chat_id: int, name: str, enabled: bool, config: dict[str, Any] | None, updated_by: int | None = None) -> None:
    ensure_tables()
    name = str(name)
    merged = dict(_DEFAULT_PROTECTION_CONFIG.get(name, {}))
    if config:
        merged.update(config)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO tigrao_protection_settings (chat_id, name, enabled, config_json, updated_by, updated_at)
            VALUES (:chat_id, :name, :enabled, :config_json, :updated_by, :updated_at)
            ON CONFLICT(chat_id, name) DO UPDATE SET
                enabled=excluded.enabled,
                config_json=excluded.config_json,
                updated_by=excluded.updated_by,
                updated_at=excluded.updated_at
        """), {"chat_id": int(chat_id), "name": name, "enabled": 1 if enabled else 0, "config_json": json.dumps(merged, ensure_ascii=False), "updated_by": updated_by, "updated_at": _to_iso(utcnow())})


def get_protection_setting(*, chat_id: int, name: str) -> dict[str, Any]:
    ensure_tables()
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM tigrao_protection_settings WHERE chat_id=:chat_id AND name=:name"), {"chat_id": int(chat_id), "name": str(name)}).mappings().first()
    default = dict(_DEFAULT_PROTECTION_CONFIG.get(str(name), {}))
    if not row:
        return {"enabled": False, "config": default}
    try:
        config = json.loads(row.get("config_json") or "{}")
    except Exception:
        config = {}
    default.update(config)
    return {"enabled": bool(row.get("enabled")), "config": default, "updated_at": row.get("updated_at"), "updated_by": row.get("updated_by")}


def list_protection_settings(*, chat_id: int) -> dict[str, dict[str, Any]]:
    return {name: get_protection_setting(chat_id=chat_id, name=name) for name in _DEFAULT_PROTECTION_CONFIG}


# ---------- Captcha ----------

def create_captcha_challenge(*, chat_id: int, chat_title: str | None, user_id: int, user_chat_id: int | None, code: str, ttl_seconds: int = 300, max_attempts: int = 3) -> int:
    ensure_tables()
    now = utcnow()
    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO tigrao_captcha_challenges (chat_id, chat_title, user_id, user_chat_id, code, created_at, expires_at, status, attempts, max_attempts, processed_at)
            VALUES (:chat_id, :chat_title, :user_id, :user_chat_id, :code, :created_at, :expires_at, 'pendente', 0, :max_attempts, NULL)
        """), {"chat_id": int(chat_id), "chat_title": chat_title, "user_id": int(user_id), "user_chat_id": user_chat_id, "code": str(code), "created_at": _to_iso(now), "expires_at": _to_iso(now + timedelta(seconds=int(ttl_seconds))), "max_attempts": max(1, min(10, int(max_attempts)))})
        return int(getattr(result, "lastrowid", 0) or 0)


def verify_captcha_challenge(*, user_id: int, code: str, max_attempts: int | None = None) -> dict[str, Any] | None:
    ensure_tables()
    now_iso = _to_iso(utcnow())
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT * FROM tigrao_captcha_challenges
            WHERE user_id=:user_id AND status='pendente' AND expires_at>=:now
            ORDER BY id DESC LIMIT 1
        """), {"user_id": int(user_id), "now": now_iso}).mappings().first()
        if not row:
            return None
        data = dict(row)
        if str(data.get("code")) == str(code).strip():
            conn.execute(text("UPDATE tigrao_captcha_challenges SET status='aprovado', processed_at=:now WHERE id=:id"), {"now": now_iso, "id": data["id"]})
            data["status"] = "aprovado"
            return data
        effective_max_attempts = int(max_attempts if max_attempts is not None else (data.get("max_attempts") or 3))
        attempts = int(data.get("attempts") or 0) + 1
        status = "falhou" if attempts >= effective_max_attempts else "pendente"
        conn.execute(text("UPDATE tigrao_captcha_challenges SET attempts=:attempts, status=:status, processed_at=CASE WHEN :status != 'pendente' THEN :now ELSE processed_at END WHERE id=:id"), {"attempts": attempts, "status": status, "now": now_iso, "id": data["id"]})
        data["attempts"] = attempts
        data["status"] = status
        return data

"""Runtime de solicitações de entrada do Tigrão FSM."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any

from app.config.settings import TIGRAO_JOIN_REQUEST_WEBAPP_URL
from app.bot.api_compat import send_chat_join_request_web_app_compat

from ..models import TigraoJoinRequest
from ..permissions import get_bot_permissions
from ..services import approve_pending_join_request
from .. import storage

logger = logging.getLogger(__name__)


def _full_name(user: Any) -> str:
    first = getattr(user, "first_name", None) or ""
    last = getattr(user, "last_name", None) or ""
    name = " ".join(part for part in (first, last) if part).strip()
    return name or getattr(user, "full_name", None) or "User"


def _dt_from_telegram(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _invite_link_value(invite_link: Any) -> str | None:
    if invite_link is None:
        return None
    for attr in ("invite_link", "link"):
        value = getattr(invite_link, attr, None)
        if value:
            return str(value)
    return str(invite_link) if invite_link else None


def _request_from_update(join_request: Any) -> TigraoJoinRequest:
    chat = getattr(join_request, "chat", None)
    user = getattr(join_request, "from_user", None) or getattr(join_request, "from", None)
    chat_id = int(getattr(chat, "id"))
    user_id = int(getattr(user, "id"))
    request_date = _dt_from_telegram(getattr(join_request, "date", None))
    return TigraoJoinRequest.create(
        chat_id=chat_id,
        chat_title=getattr(chat, "title", None) or str(chat_id),
        user_id=user_id,
        username=getattr(user, "username", None),
        full_name=_full_name(user),
        user_chat_id=int(getattr(join_request, "user_chat_id")) if getattr(join_request, "user_chat_id", None) is not None else None,
        bio=getattr(join_request, "bio", None),
        invite_link=_invite_link_value(getattr(join_request, "invite_link", None)),
        request_date=request_date,
    )


async def _notify_owner(bot: Any, text: str, owner_user_id: int | None) -> None:
    if owner_user_id is None:
        return
    try:
        await bot.send_message(owner_user_id, text)
    except Exception:
        logger.debug("TIGRAO_JOIN_NOTIFY_OWNER_FAILED", exc_info=True)


async def _send_join_request_webapp_if_available(bot: Any, join_request: Any, request: TigraoJoinRequest) -> bool:
    query_id = getattr(join_request, "query_id", None)
    if not query_id or not TIGRAO_JOIN_REQUEST_WEBAPP_URL:
        return False
    try:
        await send_chat_join_request_web_app_compat(bot, chat_join_request_query_id=str(query_id), web_app_url=TIGRAO_JOIN_REQUEST_WEBAPP_URL)
    except Exception as exc:
        storage.log_event(
            action="join_request_webapp",
            result="falhou",
            detection="direta",
            surface="chat_join_request",
            chat_id=request.chat_id,
            chat_title=request.chat_title,
            actor_user_id=request.user_id,
            target_user_id=request.user_id,
            details=f"Falha ao abrir Mini App de entrada: {exc}",
            metadata={"query_id": str(query_id)},
        )
        return False
    storage.log_event(
        action="join_request_webapp",
        result="enviado",
        detection="direta",
        surface="chat_join_request",
        chat_id=request.chat_id,
        chat_title=request.chat_title,
        actor_user_id=request.user_id,
        target_user_id=request.user_id,
        details="Mini App de join request enviado ao usuário.",
        metadata={"query_id": str(query_id), "web_app_url": TIGRAO_JOIN_REQUEST_WEBAPP_URL},
    )
    return True


async def _captcha_gate(bot: Any, request: TigraoJoinRequest) -> bool:
    setting = storage.get_protection_setting(chat_id=request.chat_id, name="captcha")
    if not setting.get("enabled"):
        return False
    config = setting.get("config") or {}
    code = f"{secrets.randbelow(9000) + 1000}"
    ttl = int(config.get("ttl_seconds") or 300)
    max_attempts = int(config.get("max_attempts") or 3)
    storage.create_captcha_challenge(chat_id=request.chat_id, chat_title=request.chat_title, user_id=request.user_id, user_chat_id=request.user_chat_id, code=code, ttl_seconds=ttl, max_attempts=max_attempts)
    if request.user_chat_id is not None:
        try:
            await bot.send_message(
                request.user_chat_id,
                "Verificação de entrada\n\n"
                f"Grupo: {request.chat_title}\n"
                f"Código: {code}\n\n"
                f"Responda ao bot com: /captcha {code}\n"
                "A solicitação expira em poucos minutos.",
            )
        except Exception as exc:
            storage.log_event(action="captcha_send", result="falhou", detection="automatica", surface="chat_join_request", chat_id=request.chat_id, chat_title=request.chat_title, actor_user_id=request.user_id, target_user_id=request.user_id, details=str(exc))
    storage.log_event(action="captcha_created", result="pendente", detection="automatica", surface="chat_join_request", chat_id=request.chat_id, chat_title=request.chat_title, actor_user_id=request.user_id, target_user_id=request.user_id, details="Captcha criado para solicitação de entrada.", metadata={"ttl_seconds": ttl, "max_attempts": max_attempts})
    return True


async def _anti_raid_gate(bot: Any, request: TigraoJoinRequest) -> bool:
    setting = storage.get_protection_setting(chat_id=request.chat_id, name="anti_raid")
    if not setting.get("enabled"):
        return False
    config = setting.get("config") or {}
    limit = int(config.get("limit") or 5)
    window = int(config.get("window_seconds") or 60)
    action = str(config.get("action") or "queue")
    pending = storage.list_pending_join_requests(chat_id=request.chat_id, limit=100)
    cutoff = storage.utcnow() - timedelta(seconds=window)
    recent = [req for req in pending if req.received_at >= cutoff]
    if len(recent) < limit:
        return False
    detail = f"Anti-raid acionado: {len(recent)} solicitações em {window}s. Ação: {action}."
    if action == "decline":
        try:
            await bot.decline_chat_join_request(chat_id=request.chat_id, user_id=request.user_id)
            request.status = storage.DECLINED
            request.processed_at = storage.utcnow()
            request.result_detail = detail
            storage.update_join_request_status(request)
        except Exception as exc:
            detail = f"Anti-raid falhou ao recusar: {exc}"
    elif action == "lock":
        try:
            try:
                from aiogram.types import ChatPermissions as _AiogramChatPermissions
                perms = _AiogramChatPermissions(can_send_messages=False)
            except Exception:
                perms = {"can_send_messages": False}
            await bot.set_chat_permissions(chat_id=request.chat_id, permissions=perms, use_independent_chat_permissions=True)
        except Exception as exc:
            detail = f"Anti-raid falhou ao fechar grupo: {exc}"
    storage.log_event(action="anti_raid", result="acionado", detection="automatica", surface="chat_join_request", chat_id=request.chat_id, chat_title=request.chat_title, actor_user_id=request.user_id, target_user_id=request.user_id, details=detail, metadata={"limit": limit, "window_seconds": window, "action": action})
    return True


async def handle(bot: Any, update: Any) -> bool:
    """Processa chat_join_request quando o plugin está habilitado.

    Retorna True para consumir o update de solicitação de entrada, pois a ponte
    do Tigrão já salvou/avaliou o evento nessa
    superfície.
    """
    join_request = getattr(update, "chat_join_request", None)
    if join_request is None:
        return False

    request = _request_from_update(join_request)
    storage.save_join_request(request)
    storage.log_event(
        action="join_request_received",
        result="pendente",
        detection="direta",
        surface="chat_join_request",
        chat_id=request.chat_id,
        chat_title=request.chat_title,
        actor_user_id=request.user_id,
        actor_username=request.username,
        actor_full_name=request.full_name,
        target_user_id=request.user_id,
        target_username=request.username,
        target_full_name=request.full_name,
        details="Solicitação de entrada recebida e salva por 2h.",
        metadata={"invite_link": request.invite_link, "user_chat_id": request.user_chat_id},
    )

    await _send_join_request_webapp_if_available(bot, join_request, request)
    if await _anti_raid_gate(bot, request):
        return True
    if await _captcha_gate(bot, request):
        return True

    auto = storage.get_active_auto_accept(chat_id=request.chat_id, user_id=request.user_id)
    if auto is None:
        return True

    try:
        perms = await get_bot_permissions(bot, request.chat_id)
    except Exception:
        logger.debug("TIGRAO_JOIN_PERMISSION_CHECK_FAILED", exc_info=True)
        perms = None
    if perms is None or not perms.is_admin or not perms.can_invite_users:
        detail = "Autoaceite não executado: bot sem can_invite_users no momento da solicitação."
        request.status = storage.FAILED
        request.processed_at = storage.utcnow()
        request.result_detail = detail
        auto.status = storage.FAILED
        auto.result_detail = detail
        storage.update_join_request_status(request)
        storage.update_auto_accept_status(auto)
        storage.log_event(
            action="join_auto_accept",
            result="falhou_sem_permissao",
            detection="direta",
            surface="chat_join_request",
            chat_id=request.chat_id,
            chat_title=request.chat_title,
            actor_user_id=auto.created_by_owner_id,
            target_user_id=request.user_id,
            target_username=request.username,
            target_full_name=request.full_name,
            details=detail,
        )
        return True

    detail = await approve_pending_join_request(
        bot,
        request,
        processed_by=auto.created_by_owner_id,
        autoaccept=True,
        origin="ID autorizado no painel",
    )
    if request.status == "aprovado":
        auto.status = storage.APPROVED
        auto.approved_at = request.processed_at
    else:
        auto.status = storage.FAILED
    auto.result_detail = detail
    storage.update_join_request_status(request)
    storage.update_auto_accept_status(auto)
    storage.log_event(
        action="join_auto_accept",
        result=request.status,
        detection="direta",
        surface="chat_join_request",
        chat_id=request.chat_id,
        chat_title=request.chat_title,
        actor_user_id=auto.created_by_owner_id,
        target_user_id=request.user_id,
        target_username=request.username,
        target_full_name=request.full_name,
        details=detail,
    )
    await _notify_owner(bot, detail, auto.created_by_owner_id)
    return True

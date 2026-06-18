"""Ações avançadas reais do painel Tigrão FSM.

Camada operacional isolada para recursos adicionais da Bot API usados em
moderação pesada: ban/mute temporário livre, purge em lote, lockdown,
fixados, reações, alteração de dados e auditoria de administradores.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from . import storage
from .permissions import TigraoBotPermissions

try:  # aiogram é opcional nos testes estáticos locais.
    from aiogram.types import ChatPermissions as _AiogramChatPermissions
except Exception:  # pragma: no cover
    _AiogramChatPermissions = None


@dataclass(slots=True)
class AdvancedActionResult:
    ok: bool
    result: str
    detail: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _until_date(duration: timedelta | None) -> datetime | None:
    if duration is None:
        return None
    return _utcnow() + duration


def _all_send_permissions(value: bool) -> Any:
    if _AiogramChatPermissions is not None:
        return _AiogramChatPermissions(
            can_send_messages=value,
            can_send_audios=value,
            can_send_documents=value,
            can_send_photos=value,
            can_send_videos=value,
            can_send_video_notes=value,
            can_send_voice_notes=value,
            can_send_polls=value,
            can_send_other_messages=value,
            can_add_web_page_previews=value,
            can_react_to_messages=value,
            # Não conceder poderes semiadministrativos no unlock/unmute.
            can_edit_tag=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_manage_topics=False,
        )
    return {"can_send_messages": value, "can_react_to_messages": value}


def mute_permissions() -> Any:
    return _all_send_permissions(False)


def unlock_permissions() -> Any:
    return _all_send_permissions(True)


def _log(
    *,
    action: str,
    result: str,
    detail: str,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    target_user_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    storage.log_event(
        action=action,
        result=result,
        detection="direta",
        surface="callback",
        chat_id=chat_id,
        chat_title=chat_title,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        details=detail,
        metadata=metadata or {},
    )


async def ban_user_custom(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    user_id: int,
    permissions: TigraoBotPermissions,
    duration: timedelta | None,
    revoke_messages: bool = False,
) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_restrict_members:
        detail = "Permissão exigida ausente: can_restrict_members."
        _log(action="ban_custom", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        kwargs: dict[str, Any] = {"chat_id": chat_id, "user_id": user_id, "revoke_messages": revoke_messages}
        until = _until_date(duration)
        if until is not None:
            kwargs["until_date"] = until
        await bot.ban_chat_member(**kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="ban_custom", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
        return AdvancedActionResult(False, "falhou", detail)
    label = "permanente" if duration is None else str(duration)
    detail = f"Ban aplicado. Tempo: {label}."
    _log(action="ban_custom", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id, metadata={"duration_seconds": int(duration.total_seconds()) if duration else None, "revoke_messages": revoke_messages})
    return AdvancedActionResult(True, "concluido", detail)


async def mute_user_custom(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    user_id: int,
    permissions: TigraoBotPermissions,
    duration: timedelta | None,
) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_restrict_members:
        detail = "Permissão exigida ausente: can_restrict_members."
        _log(action="mute_custom", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "permissions": mute_permissions(),
            "use_independent_chat_permissions": True,
        }
        until = _until_date(duration)
        if until is not None:
            kwargs["until_date"] = until
        await bot.restrict_chat_member(**kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="mute_custom", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
        return AdvancedActionResult(False, "falhou", detail)
    label = "permanente" if duration is None else str(duration)
    detail = f"Mute aplicado. Tempo: {label}."
    _log(action="mute_custom", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id, metadata={"duration_seconds": int(duration.total_seconds()) if duration else None})
    return AdvancedActionResult(True, "concluido", detail)


async def purge_messages(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    message_ids: list[int],
    permissions: TigraoBotPermissions,
) -> AdvancedActionResult:
    clean = sorted({int(mid) for mid in message_ids if int(mid) > 0})
    if not clean:
        return AdvancedActionResult(False, "bloqueado_mensagem_invalida", "Nenhum message_id válido informado.")
    if len(clean) > 100:
        return AdvancedActionResult(False, "bloqueado_limite_api", "A Bot API aceita no máximo 100 mensagens por chamada deleteMessages.")
    if not permissions.is_admin or not permissions.can_delete_messages:
        detail = "Permissão exigida ausente: can_delete_messages."
        _log(action="purge_messages", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_ids": clean})
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        if hasattr(bot, "delete_messages"):
            await bot.delete_messages(chat_id=chat_id, message_ids=clean)
        else:
            # Compatibilidade defensiva: aiogram/Bot API antigo.
            for mid in clean:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="purge_messages", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_ids": clean})
        return AdvancedActionResult(False, "falhou", detail)
    detail = f"Purge solicitado para {len(clean)} mensagem(ns)."
    _log(action="purge_messages", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_ids": clean})
    return AdvancedActionResult(True, "concluido", detail)


async def set_group_lockdown(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    permissions: TigraoBotPermissions,
    locked: bool,
) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_restrict_members:
        detail = "Permissão exigida ausente: can_restrict_members."
        _log(action="lockdown" if locked else "unlock_group", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=_all_send_permissions(not locked),
            use_independent_chat_permissions=True,
        )
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="lockdown" if locked else "unlock_group", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "falhou", detail)
    detail = "Grupo fechado para envio de membros comuns." if locked else "Permissões padrão de envio reabertas para membros comuns."
    _log(action="lockdown" if locked else "unlock_group", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
    return AdvancedActionResult(True, "concluido", detail)


async def pin_message(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, message_id: int, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_pin_messages:
        detail = "Permissão exigida ausente: can_pin_messages."
        _log(action="pin_message", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_id": message_id})
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=True)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="pin_message", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_id": message_id})
        return AdvancedActionResult(False, "falhou", detail)
    detail = f"Mensagem fixada: {message_id}."
    _log(action="pin_message", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_id": message_id})
    return AdvancedActionResult(True, "concluido", detail)


async def unpin_message(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, message_id: int | None, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_pin_messages:
        detail = "Permissão exigida ausente: can_pin_messages."
        _log(action="unpin_message", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_id": message_id})
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        kwargs: dict[str, Any] = {"chat_id": chat_id}
        if message_id is not None:
            kwargs["message_id"] = int(message_id)
        await bot.unpin_chat_message(**kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="unpin_message", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_id": message_id})
        return AdvancedActionResult(False, "falhou", detail)
    detail = f"Mensagem desfixada: {message_id if message_id is not None else 'mais recente'}."
    _log(action="unpin_message", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_id": message_id})
    return AdvancedActionResult(True, "concluido", detail)


async def unpin_all_messages(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_pin_messages:
        detail = "Permissão exigida ausente: can_pin_messages."
        _log(action="unpin_all_messages", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        await bot.unpin_all_chat_messages(chat_id=chat_id)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="unpin_all_messages", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "falhou", detail)
    detail = "Todos os fixados foram removidos."
    _log(action="unpin_all_messages", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
    return AdvancedActionResult(True, "concluido", detail)


async def set_group_title(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, new_title: str, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    clean = str(new_title or "").strip()
    if not 1 <= len(clean) <= 128:
        return AdvancedActionResult(False, "bloqueado_entrada_invalida", "Título precisa ter 1 a 128 caracteres.")
    if not permissions.is_admin or not permissions.can_change_info:
        detail = "Permissão exigida ausente: can_change_info."
        _log(action="set_group_title", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        await bot.set_chat_title(chat_id=chat_id, title=clean)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="set_group_title", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "falhou", detail)
    detail = f"Título alterado para: {clean}"
    _log(action="set_group_title", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
    return AdvancedActionResult(True, "concluido", detail)


async def set_group_description(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, description: str, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    clean = str(description or "").strip()
    if len(clean) > 255:
        return AdvancedActionResult(False, "bloqueado_entrada_invalida", "Descrição precisa ter no máximo 255 caracteres.")
    if not permissions.is_admin or not permissions.can_change_info:
        detail = "Permissão exigida ausente: can_change_info."
        _log(action="set_group_description", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        await bot.set_chat_description(chat_id=chat_id, description=clean)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="set_group_description", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "falhou", detail)
    detail = "Descrição alterada."
    _log(action="set_group_description", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
    return AdvancedActionResult(True, "concluido", detail)


async def delete_message_reaction(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, message_id: int, user_id: int | None, actor_chat_id: int | None, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_delete_messages:
        detail = "Permissão exigida ausente: can_delete_messages."
        _log(action="delete_message_reaction", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_id": message_id, "user_id": user_id, "actor_chat_id": actor_chat_id})
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    if user_id is None and actor_chat_id is None:
        return AdvancedActionResult(False, "bloqueado_entrada_invalida", "Informe user_id ou actor_chat_id da reação.")
    try:
        kwargs: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id}
        if user_id is not None:
            kwargs["user_id"] = user_id
        if actor_chat_id is not None:
            kwargs["actor_chat_id"] = actor_chat_id
        await bot.delete_message_reaction(**kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="delete_message_reaction", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_id": message_id, "user_id": user_id, "actor_chat_id": actor_chat_id})
        return AdvancedActionResult(False, "falhou", detail)
    detail = "Reação removida da mensagem."
    _log(action="delete_message_reaction", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_id": message_id, "user_id": user_id, "actor_chat_id": actor_chat_id})
    return AdvancedActionResult(True, "concluido", detail)


async def delete_all_message_reactions(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, user_id: int | None, actor_chat_id: int | None, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_delete_messages:
        detail = "Permissão exigida ausente: can_delete_messages."
        _log(action="delete_all_message_reactions", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"user_id": user_id, "actor_chat_id": actor_chat_id})
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    if user_id is None and actor_chat_id is None:
        return AdvancedActionResult(False, "bloqueado_entrada_invalida", "Informe user_id ou actor_chat_id.")
    try:
        kwargs: dict[str, Any] = {"chat_id": chat_id}
        if user_id is not None:
            kwargs["user_id"] = user_id
        if actor_chat_id is not None:
            kwargs["actor_chat_id"] = actor_chat_id
        await bot.delete_all_message_reactions(**kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="delete_all_message_reactions", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"user_id": user_id, "actor_chat_id": actor_chat_id})
        return AdvancedActionResult(False, "falhou", detail)
    detail = "Remoção em massa de reações recentes solicitada."
    _log(action="delete_all_message_reactions", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"user_id": user_id, "actor_chat_id": actor_chat_id})
    return AdvancedActionResult(True, "concluido", detail)


async def format_admin_audit(bot: Any, *, chat_id: int) -> str:
    try:
        try:
            admins = await bot.get_chat_administrators(chat_id=chat_id, return_bots=True)
        except TypeError:
            admins = await bot.get_chat_administrators(chat_id=chat_id)
    except Exception as exc:
        return f"Falha ao consultar administradores: {exc}"
    lines = ["Auditoria de administradores/bots"]
    for member in admins:
        user = getattr(member, "user", None)
        name = getattr(user, "full_name", None) or getattr(user, "first_name", None) or getattr(user, "username", None) or getattr(user, "id", "desconhecido")
        is_bot = "bot" if getattr(user, "is_bot", False) else "humano"
        uid = getattr(user, "id", None)
        status = getattr(getattr(member, "status", None), "value", getattr(member, "status", None))
        flags = []
        for flag in ("can_delete_messages", "can_restrict_members", "can_promote_members", "can_change_info", "can_invite_users", "can_pin_messages", "can_manage_topics"):
            if getattr(member, flag, False):
                flags.append(flag.replace("can_", ""))
        lines.append(f"- {name} ({is_bot}) ID: {uid} status: {status} direitos: {', '.join(flags) if flags else 'sem flags'}")
    return "\n".join(lines[:60])


_ADMIN_RIGHT_FIELDS = (
    "can_manage_chat",
    "can_delete_messages",
    "can_manage_video_chats",
    "can_restrict_members",
    "can_promote_members",
    "can_change_info",
    "can_invite_users",
    "can_post_stories",
    "can_edit_stories",
    "can_delete_stories",
    "can_post_messages",
    "can_edit_messages",
    "can_pin_messages",
    "can_manage_topics",
    "can_manage_direct_messages",
    "can_manage_tags",
)

_ADMIN_ROLE_RIGHTS: dict[str, dict[str, bool]] = {
    "limited": {
        "can_manage_chat": True,
        "can_delete_messages": True,
        "can_invite_users": True,
        "can_pin_messages": True,
    },
    "moderator": {
        "can_manage_chat": True,
        "can_delete_messages": True,
        "can_restrict_members": True,
        "can_invite_users": True,
        "can_pin_messages": True,
        "can_manage_topics": True,
    },
    "admin": {
        "can_manage_chat": True,
        "can_delete_messages": True,
        "can_manage_video_chats": True,
        "can_restrict_members": True,
        "can_change_info": True,
        "can_invite_users": True,
        "can_post_stories": True,
        "can_edit_stories": True,
        "can_delete_stories": True,
        "can_post_messages": True,
        "can_edit_messages": True,
        "can_pin_messages": True,
        "can_manage_topics": True,
        "can_manage_direct_messages": True,
        "can_manage_tags": True,
    },
    "full": {
        "can_manage_chat": True,
        "can_delete_messages": True,
        "can_manage_video_chats": True,
        "can_restrict_members": True,
        "can_promote_members": True,
        "can_change_info": True,
        "can_invite_users": True,
        "can_post_stories": True,
        "can_edit_stories": True,
        "can_delete_stories": True,
        "can_post_messages": True,
        "can_edit_messages": True,
        "can_pin_messages": True,
        "can_manage_topics": True,
        "can_manage_direct_messages": True,
        "can_manage_tags": True,
    },
}


def _admin_rights_kwargs(role: str | None, custom_flags: dict[str, bool] | None = None, demote: bool = False) -> dict[str, bool]:
    if demote:
        return {field: False for field in _ADMIN_RIGHT_FIELDS}
    rights = {field: False for field in _ADMIN_RIGHT_FIELDS}
    if role == "custom" and custom_flags:
        for key, value in custom_flags.items():
            if key in rights:
                rights[key] = bool(value)
        rights["can_manage_chat"] = rights["can_manage_chat"] or any(rights.values())
        return rights
    for key, value in _ADMIN_ROLE_RIGHTS.get(role or "moderator", _ADMIN_ROLE_RIGHTS["moderator"]).items():
        rights[key] = value
    return rights


async def promote_user_admin(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    user_id: int,
    permissions: TigraoBotPermissions,
    role: str | None,
    custom_flags: dict[str, bool] | None = None,
) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_promote_members:
        detail = "Permissão exigida ausente: can_promote_members."
        _log(action="promote_admin", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    kwargs = _admin_rights_kwargs(role, custom_flags)
    try:
        await bot.promote_chat_member(chat_id=chat_id, user_id=user_id, **kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="promote_admin", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id, metadata={"role": role, "rights": kwargs})
        return AdvancedActionResult(False, "falhou", detail)
    detail = f"Usuário promovido/reconfigurado como admin. Perfil: {role or 'moderator'}."
    _log(action="promote_admin", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id, metadata={"role": role, "rights": kwargs})
    return AdvancedActionResult(True, "concluido", detail)


async def demote_user_admin(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    user_id: int,
    permissions: TigraoBotPermissions,
) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_promote_members:
        detail = "Permissão exigida ausente: can_promote_members."
        _log(action="demote_admin", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    kwargs = _admin_rights_kwargs(None, demote=True)
    try:
        await bot.promote_chat_member(chat_id=chat_id, user_id=user_id, **kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="demote_admin", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
        return AdvancedActionResult(False, "falhou", detail)
    detail = "Usuário rebaixado de administrador."
    _log(action="demote_admin", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
    return AdvancedActionResult(True, "concluido", detail)


async def set_admin_custom_title(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    user_id: int,
    custom_title: str,
    permissions: TigraoBotPermissions,
) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_promote_members:
        detail = "Permissão exigida ausente: can_promote_members."
        _log(action="set_admin_title", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    clean = str(custom_title or "").strip()
    if not 0 <= len(clean) <= 16:
        return AdvancedActionResult(False, "bloqueado_entrada_invalida", "Título precisa ter 0 a 16 caracteres.")
    try:
        await bot.set_chat_administrator_custom_title(chat_id=chat_id, user_id=user_id, custom_title=clean)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="set_admin_title", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id, metadata={"custom_title": clean})
        return AdvancedActionResult(False, "falhou", detail)
    detail = "Título customizado de admin alterado."
    _log(action="set_admin_title", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id, metadata={"custom_title": clean})
    return AdvancedActionResult(True, "concluido", detail)


async def ban_sender_chat(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    sender_chat_id: int,
    permissions: TigraoBotPermissions,
) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_restrict_members:
        detail = "Permissão exigida ausente: can_restrict_members."
        _log(action="ban_sender_chat", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"sender_chat_id": sender_chat_id})
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        await bot.ban_chat_sender_chat(chat_id=chat_id, sender_chat_id=sender_chat_id)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="ban_sender_chat", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"sender_chat_id": sender_chat_id})
        return AdvancedActionResult(False, "falhou", detail)
    detail = f"Sender chat/canal banido: {sender_chat_id}."
    _log(action="ban_sender_chat", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"sender_chat_id": sender_chat_id})
    return AdvancedActionResult(True, "concluido", detail)


async def unban_sender_chat(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    sender_chat_id: int,
    permissions: TigraoBotPermissions,
) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_restrict_members:
        detail = "Permissão exigida ausente: can_restrict_members."
        _log(action="unban_sender_chat", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"sender_chat_id": sender_chat_id})
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        await bot.unban_chat_sender_chat(chat_id=chat_id, sender_chat_id=sender_chat_id)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="unban_sender_chat", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"sender_chat_id": sender_chat_id})
        return AdvancedActionResult(False, "falhou", detail)
    detail = f"Sender chat/canal desbanido: {sender_chat_id}."
    _log(action="unban_sender_chat", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"sender_chat_id": sender_chat_id})
    return AdvancedActionResult(True, "concluido", detail)


def _invite_expire_date(duration: timedelta | None) -> datetime | None:
    return _until_date(duration) if duration is not None else None


async def export_primary_invite_link(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_invite_users:
        detail = "Permissão exigida ausente: can_invite_users."
        _log(action="export_invite_link", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        link = await bot.export_chat_invite_link(chat_id=chat_id)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="export_invite_link", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "falhou", detail)
    detail = f"Link primário exportado/renovado pelo bot:\n{link}"
    _log(action="export_invite_link", result="concluido", detail="Link primário exportado/renovado.", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"invite_link": str(link)})
    return AdvancedActionResult(True, "concluido", detail)


async def create_invite_link_full(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    permissions: TigraoBotPermissions,
    name: str | None,
    duration: timedelta | None,
    member_limit: int | None,
    creates_join_request: bool,
) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_invite_users:
        detail = "Permissão exigida ausente: can_invite_users."
        _log(action="create_invite_link", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    kwargs: dict[str, Any] = {"chat_id": chat_id, "creates_join_request": creates_join_request}
    if name:
        kwargs["name"] = name
    expire_date = _invite_expire_date(duration)
    if expire_date is not None:
        kwargs["expire_date"] = expire_date
    if member_limit is not None and not creates_join_request:
        kwargs["member_limit"] = member_limit
    try:
        invite = await bot.create_chat_invite_link(**kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="create_invite_link", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata=kwargs)
        return AdvancedActionResult(False, "falhou", detail)
    link = getattr(invite, "invite_link", None) or getattr(invite, "link", None) or str(invite)
    detail = f"Link de convite criado:\n{link}"
    _log(action="create_invite_link", result="concluido", detail="Link de convite criado.", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={**kwargs, "invite_link": link})
    return AdvancedActionResult(True, "concluido", detail)


async def edit_invite_link_full(
    bot: Any,
    *,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    permissions: TigraoBotPermissions,
    invite_link: str,
    name: str | None,
    duration: timedelta | None,
    member_limit: int | None,
    creates_join_request: bool,
) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_invite_users:
        detail = "Permissão exigida ausente: can_invite_users."
        _log(action="edit_invite_link", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    kwargs: dict[str, Any] = {"chat_id": chat_id, "invite_link": invite_link, "creates_join_request": creates_join_request}
    if name is not None:
        kwargs["name"] = name
    expire_date = _invite_expire_date(duration)
    if expire_date is not None:
        kwargs["expire_date"] = expire_date
    if member_limit is not None and not creates_join_request:
        kwargs["member_limit"] = member_limit
    try:
        edited = await bot.edit_chat_invite_link(**kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="edit_invite_link", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata=kwargs)
        return AdvancedActionResult(False, "falhou", detail)
    link = getattr(edited, "invite_link", None) or getattr(edited, "link", None) or invite_link
    detail = f"Link de convite editado:\n{link}"
    _log(action="edit_invite_link", result="concluido", detail="Link de convite editado.", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={**kwargs, "result_link": link})
    return AdvancedActionResult(True, "concluido", detail)


async def revoke_invite_link_full(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, permissions: TigraoBotPermissions, invite_link: str) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_invite_users:
        detail = "Permissão exigida ausente: can_invite_users."
        _log(action="revoke_invite_link", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        revoked = await bot.revoke_chat_invite_link(chat_id=chat_id, invite_link=invite_link)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="revoke_invite_link", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"invite_link": invite_link})
        return AdvancedActionResult(False, "falhou", detail)
    link = getattr(revoked, "invite_link", None) or getattr(revoked, "link", None) or invite_link
    detail = f"Link revogado:\n{link}"
    _log(action="revoke_invite_link", result="concluido", detail="Link revogado.", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"invite_link": invite_link, "result_link": link})
    return AdvancedActionResult(True, "concluido", detail)

# ---------- Etapa 02: foto, tópicos, tags, warnings e proteções ----------

async def set_member_tag_action(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, user_id: int, tag: str, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_manage_tags:
        detail = "Permissão exigida ausente: can_manage_tags."
        _log(action="set_member_tag", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    clean = str(tag or "").strip()
    if len(clean) > 16:
        return AdvancedActionResult(False, "bloqueado_entrada_invalida", "Tag precisa ter 0 a 16 caracteres.")
    try:
        await bot.set_chat_member_tag(chat_id=chat_id, user_id=user_id, tag=clean or None)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="set_member_tag", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id, metadata={"tag": clean})
        return AdvancedActionResult(False, "falhou", detail)
    detail = f"Tag do membro alterada para: {clean or '<vazia>'}."
    _log(action="set_member_tag", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id, metadata={"tag": clean})
    return AdvancedActionResult(True, "concluido", detail)


async def delete_group_photo(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_change_info:
        detail = "Permissão exigida ausente: can_change_info."
        _log(action="delete_group_photo", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        await bot.delete_chat_photo(chat_id=chat_id)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="delete_group_photo", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "falhou", detail)
    detail = "Foto do grupo removida."
    _log(action="delete_group_photo", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
    return AdvancedActionResult(True, "concluido", detail)


async def set_group_photo_file(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, photo: Any, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_change_info:
        detail = "Permissão exigida ausente: can_change_info."
        _log(action="set_group_photo", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    try:
        await bot.set_chat_photo(chat_id=chat_id, photo=photo)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="set_group_photo", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "falhou", detail)
    detail = "Foto do grupo alterada."
    _log(action="set_group_photo", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
    return AdvancedActionResult(True, "concluido", detail)


async def create_forum_topic_action(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, name: str, icon_color: int | None, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_manage_topics:
        detail = "Permissão exigida ausente: can_manage_topics."
        _log(action="create_forum_topic", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    kwargs: dict[str, Any] = {"chat_id": chat_id, "name": name}
    if icon_color is not None:
        kwargs["icon_color"] = icon_color
    try:
        topic = await bot.create_forum_topic(**kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="create_forum_topic", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata=kwargs)
        return AdvancedActionResult(False, "falhou", detail)
    thread_id = getattr(topic, "message_thread_id", None)
    detail = f"Tópico criado. Thread ID: {thread_id if thread_id is not None else 'não informado'}."
    _log(action="create_forum_topic", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"name": name, "icon_color": icon_color, "message_thread_id": thread_id})
    return AdvancedActionResult(True, "concluido", detail)


async def edit_forum_topic_action(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, message_thread_id: int, name: str, icon_color: int | None, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    if not permissions.is_admin or not permissions.can_manage_topics:
        detail = "Permissão exigida ausente: can_manage_topics."
        _log(action="edit_forum_topic", result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_thread_id": message_thread_id})
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    kwargs: dict[str, Any] = {"chat_id": chat_id, "message_thread_id": message_thread_id, "name": name}
    if icon_color is not None:
        kwargs["icon_color"] = icon_color
    try:
        await bot.edit_forum_topic(**kwargs)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action="edit_forum_topic", result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata=kwargs)
        return AdvancedActionResult(False, "falhou", detail)
    detail = f"Tópico editado. Thread ID: {message_thread_id}."
    _log(action="edit_forum_topic", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata=kwargs)
    return AdvancedActionResult(True, "concluido", detail)


_TOPIC_METHODS = {
    "topicclose": ("close_forum_topic", "Tópico fechado."),
    "topicreopen": ("reopen_forum_topic", "Tópico reaberto."),
    "topicdelete": ("delete_forum_topic", "Tópico apagado."),
    "topicunpin": ("unpin_all_forum_topic_messages", "Fixados do tópico removidos."),
}

async def manage_forum_topic_action(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, action: str, message_thread_id: int, permissions: TigraoBotPermissions) -> AdvancedActionResult:
    required_flag = "can_manage_topics"
    if action == "topicdelete":
        required_flag = "can_delete_messages"
    elif action == "topicunpin":
        required_flag = "can_pin_messages"
    if not permissions.is_admin or not bool(getattr(permissions, required_flag, False)):
        detail = f"Permissão exigida ausente: {required_flag}."
        _log(action=action, result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_thread_id": message_thread_id})
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    method_name, ok_detail = _TOPIC_METHODS.get(action, ("", ""))
    if not method_name:
        return AdvancedActionResult(False, "bloqueado_acao_desconhecida", "Ação de tópico desconhecida.")
    try:
        await getattr(bot, method_name)(chat_id=chat_id, message_thread_id=message_thread_id)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action=action, result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_thread_id": message_thread_id})
        return AdvancedActionResult(False, "falhou", detail)
    _log(action=action, result="concluido", detail=ok_detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"message_thread_id": message_thread_id})
    return AdvancedActionResult(True, "concluido", ok_detail)


_GENERAL_TOPIC_METHODS = {
    "topicgclose": ("close_general_forum_topic", "Tópico geral fechado."),
    "topicgreopen": ("reopen_general_forum_topic", "Tópico geral reaberto."),
    "topicghide": ("hide_general_forum_topic", "Tópico geral ocultado."),
    "topicgunhide": ("unhide_general_forum_topic", "Tópico geral reexibido."),
    "topicgunpin": ("unpin_all_general_forum_topic_messages", "Fixados do tópico geral removidos."),
}

async def manage_general_forum_topic_action(bot: Any, *, chat_id: int, chat_title: str, actor_user_id: int, action: str, permissions: TigraoBotPermissions, name: str | None = None) -> AdvancedActionResult:
    required_flag = "can_pin_messages" if action == "topicgunpin" else "can_manage_topics"
    if not permissions.is_admin or not bool(getattr(permissions, required_flag, False)):
        detail = f"Permissão exigida ausente: {required_flag}."
        _log(action=action, result="bloqueado_sem_permissao", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "bloqueado_sem_permissao", detail)
    if action == "topicgedit":
        clean = str(name or "").strip()
        if not 1 <= len(clean) <= 128:
            return AdvancedActionResult(False, "bloqueado_entrada_invalida", "Nome do tópico geral precisa ter 1 a 128 caracteres.")
        try:
            await bot.edit_general_forum_topic(chat_id=chat_id, name=clean)
        except Exception as exc:
            detail = f"Falha Telegram: {exc}"
            _log(action=action, result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
            return AdvancedActionResult(False, "falhou", detail)
        detail = "Tópico geral renomeado."
        _log(action=action, result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"name": clean})
        return AdvancedActionResult(True, "concluido", detail)
    method_name, ok_detail = _GENERAL_TOPIC_METHODS.get(action, ("", ""))
    if not method_name:
        return AdvancedActionResult(False, "bloqueado_acao_desconhecida", "Ação de tópico geral desconhecida.")
    try:
        await getattr(bot, method_name)(chat_id=chat_id)
    except Exception as exc:
        detail = f"Falha Telegram: {exc}"
        _log(action=action, result="falhou", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
        return AdvancedActionResult(False, "falhou", detail)
    _log(action=action, result="concluido", detail=ok_detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id)
    return AdvancedActionResult(True, "concluido", ok_detail)


def add_warning_action(*, chat_id: int, chat_title: str, actor_user_id: int, user_id: int, reason: str | None) -> AdvancedActionResult:
    warning_id = storage.add_warning(chat_id=chat_id, chat_title=chat_title, user_id=user_id, reason=reason, created_by=actor_user_id)
    count = storage.count_warnings(chat_id=chat_id, user_id=user_id)
    detail = f"Advertência registrada. ID: {warning_id}. Reincidência ativa do usuário: {count}."
    _log(action="warning_add", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id, metadata={"warning_id": warning_id, "count": count, "reason": reason})
    return AdvancedActionResult(True, "concluido", detail)


def clear_warning_action(*, chat_id: int, chat_title: str, actor_user_id: int, user_id: int | None) -> AdvancedActionResult:
    affected = storage.clear_warnings(chat_id=chat_id, user_id=user_id)
    detail = f"Advertências limpas: {affected}."
    _log(action="warning_clear", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=user_id)
    return AdvancedActionResult(True, "concluido", detail)


def format_warning_list(*, chat_id: int, user_id: int | None = None) -> str:
    rows = storage.list_warnings(chat_id=chat_id, user_id=user_id, limit=20)
    if not rows:
        return "Nenhuma advertência ativa encontrada."
    lines = ["Advertências / reincidência"]
    for row in rows:
        lines.append(f"ID: {row.get('id')} | usuário: {row.get('user_id')} | motivo: {row.get('reason') or 'sem motivo'} | data: {row.get('created_at')}")
    return "\n".join(lines)


def set_protection_action(*, chat_id: int, chat_title: str, actor_user_id: int, name: str, enabled: bool, config: dict[str, Any]) -> AdvancedActionResult:
    storage.set_protection_setting(chat_id=chat_id, name=name, enabled=enabled, config=config, updated_by=actor_user_id)
    detail = f"Proteção {name} {'ativada' if enabled else 'desativada'}. Configuração: {config}."
    _log(action=f"protection_{name}", result="concluido", detail=detail, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, metadata={"enabled": enabled, "config": config})
    return AdvancedActionResult(True, "concluido", detail)


def format_protection_status(*, chat_id: int) -> str:
    settings = storage.list_protection_settings(chat_id=chat_id)
    lines = ["Proteções automáticas"]
    for name, data in settings.items():
        lines.append(f"{name}: {'ativo' if data.get('enabled') else 'inativo'} — {data.get('config')}")
    return "\n".join(lines)

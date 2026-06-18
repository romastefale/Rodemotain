"""X9 inline do Rodemotain.

Superfície inline para executar ações rápidas do painel por @rodemotainbot.
A segurança é intencionalmente dupla: só usuários autorizados recebem opções
funcionais e cada callback revalida usuário, grupo, alvo protegido e permissões
reais do bot antes de executar qualquer ação.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.config.settings import TIGRAO_BOT_ACCESS_USER_IDS

from ..advanced_actions import (
    AdvancedActionResult,
    add_warning_action,
    format_admin_audit,
    format_protection_status,
    set_group_lockdown,
)
from ..destructive_actions import DestructiveActionRequest, execute_destructive_action, is_protected_target
from ..permissions import get_bot_permissions, is_authorized_user

try:  # aiogram existe em produção; testes estáticos locais podem não tê-lo instalado.
    from aiogram import F, Router
    from aiogram.types import (
        CallbackQuery,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        InlineQuery,
        InlineQueryResultArticle,
        InputTextMessageContent,
    )
except Exception:  # pragma: no cover - fallback apenas para import estático sem aiogram
    F = None
    Router = None
    CallbackQuery = Any  # type: ignore
    InlineKeyboardButton = None  # type: ignore
    InlineKeyboardMarkup = None  # type: ignore
    InlineQuery = Any  # type: ignore
    InlineQueryResultArticle = None  # type: ignore
    InputTextMessageContent = None  # type: ignore

logger = logging.getLogger(__name__)
router = Router(name="rodemotain_x9_inline") if Router is not None else None

X9_CALLBACK_PREFIX = "x9:"
X9_AUTO_DELETE_SECONDS = 60
X9_ACCESS_DENIED_TEXT = "Acesso negado."
X9_NEEDS_CHAT_TEXT = "Sem grupo definido. Use @rodemotainbot user_id chat_id."

TARGET_ACTIONS: dict[str, str] = {
    "ban": "Banir",
    "mute1h": "Mutar 1h",
    "mute24h": "Mutar 24h",
    "muteforever": "Mutar indef.",
    "unmute": "Desmutar",
    "unban": "Desbanir",
    "warn": "Advertir",
}

GROUP_ACTIONS: dict[str, str] = {
    "lock": "Fechar grupo",
    "unlock": "Reabrir grupo",
    "admins": "Auditar admins/bots",
    "protstatus": "Status proteções",
}

DESTRUCTIVE_OR_MUTATING_ACTIONS = {
    "ban",
    "mute1h",
    "mute24h",
    "muteforever",
    "unmute",
    "unban",
    "warn",
    "lock",
    "unlock",
}


@dataclass(frozen=True, slots=True)
class X9QuerySpec:
    target_user_id: int | None = None
    chat_id: int | None = None


def _uid(obj: Any) -> int | None:
    user = getattr(obj, "from_user", None)
    try:
        return int(getattr(user, "id"))
    except Exception:
        return None


def _authorized(user_id: int | None) -> bool:
    return is_authorized_user(user_id, owner_ids=TIGRAO_BOT_ACCESS_USER_IDS)


def parse_x9_query(query: str) -> X9QuerySpec:
    """Extrai user_id e chat_id de consultas inline.

    Formas aceitas:
    - vazio, "." ou "...": menu de grupo;
    - "123456": menu de ações para o usuário, resolvendo o grupo no clique;
    - "123456 -1009876543210": ações para usuário e grupo explícito.
    Separadores como "+" são aceitos porque extraímos inteiros por regex.
    """
    text = str(query or "").strip()
    numbers = [int(match) for match in re.findall(r"-?\d+", text)]
    target = numbers[0] if len(numbers) >= 1 else None
    chat = numbers[1] if len(numbers) >= 2 else None
    return X9QuerySpec(target_user_id=target, chat_id=chat)


def _callback_data(kind: str, action: str, target_user_id: int | None, chat_id: int | None) -> str:
    target = int(target_user_id or 0)
    chat = int(chat_id or 0)
    data = f"{X9_CALLBACK_PREFIX}{kind}:{action}:{target}:{chat}"
    if len(data.encode("utf-8")) > 64:
        raise ValueError("callback_data X9 excede 64 bytes")
    return data


def parse_x9_callback(data: str) -> tuple[str, str, int | None, int | None] | None:
    if not isinstance(data, str) or not data.startswith(X9_CALLBACK_PREFIX):
        return None
    tail = data[len(X9_CALLBACK_PREFIX):]
    parts = tail.split(":")
    if len(parts) != 4:
        return None
    kind, action, target_raw, chat_raw = parts
    if kind not in {"ask", "do", "cancel"}:
        return None
    if action not in {*TARGET_ACTIONS.keys(), *GROUP_ACTIONS.keys(), "none"}:
        return None
    try:
        target = int(target_raw)
        chat = int(chat_raw)
    except Exception:
        return None
    return kind, action, target if target else None, chat if chat else None


def _chat_type(chat: Any) -> str | None:
    value = getattr(chat, "type", None)
    value = getattr(value, "value", value)
    return str(value) if value is not None else None


def _callback_message(callback: Any) -> Any | None:
    message = getattr(callback, "message", None)
    if message is None:
        return None
    if getattr(message, "date", None) is None and getattr(message, "message_id", None) is None:
        return None
    return message


def _message_chat(callback: Any) -> Any | None:
    message = _callback_message(callback)
    return getattr(message, "chat", None) if message is not None else None


def _resolve_chat_id(callback: Any, explicit_chat_id: int | None) -> int | None:
    if explicit_chat_id is not None:
        return int(explicit_chat_id)
    chat = _message_chat(callback)
    if _chat_type(chat) in {"group", "supergroup"}:
        try:
            return int(getattr(chat, "id"))
        except Exception:
            return None
    return None


def _chat_title(callback: Any, chat_id: int) -> str:
    chat = _message_chat(callback)
    title = getattr(chat, "title", None)
    return str(title or chat_id)


def _button(text: str, data: str) -> Any:
    if InlineKeyboardButton is None:  # pragma: no cover
        return {"text": text, "callback_data": data}
    return InlineKeyboardButton(text=text, callback_data=data)


def _markup(rows: list[list[tuple[str, str]]]) -> Any:
    keyboard = [[_button(text, data) for text, data in row] for row in rows]
    if InlineKeyboardMarkup is None:  # pragma: no cover
        return keyboard
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def x9_action_keyboard(spec: X9QuerySpec) -> Any:
    target = spec.target_user_id
    chat = spec.chat_id
    if target is not None:
        rows = [
            [("Banir", _callback_data("ask", "ban", target, chat)), ("Mutar 1h", _callback_data("ask", "mute1h", target, chat))],
            [("Mutar 24h", _callback_data("ask", "mute24h", target, chat)), ("Mutar indef.", _callback_data("ask", "muteforever", target, chat))],
            [("Desmutar", _callback_data("ask", "unmute", target, chat)), ("Desbanir", _callback_data("ask", "unban", target, chat))],
            [("Advertir", _callback_data("ask", "warn", target, chat))],
            [("Auditar admins/bots", _callback_data("ask", "admins", target, chat))],
        ]
    else:
        rows = [
            [("Fechar grupo", _callback_data("ask", "lock", None, chat)), ("Reabrir grupo", _callback_data("ask", "unlock", None, chat))],
            [("Auditar admins/bots", _callback_data("ask", "admins", None, chat))],
            [("Status proteções", _callback_data("ask", "protstatus", None, chat))],
        ]
    return _markup(rows)


def x9_inline_message_text(spec: X9QuerySpec) -> str:
    if spec.target_user_id is None:
        if spec.chat_id is None:
            return "Rodemotain X9\nFunções rápidas para o grupo atual."
        return f"Rodemotain X9\nFunções rápidas para o grupo {spec.chat_id}."
    if spec.chat_id is None:
        return f"Rodemotain X9\nAlvo: {spec.target_user_id}\nGrupo: será resolvido no chat onde o botão for usado."
    return f"Rodemotain X9\nAlvo: {spec.target_user_id}\nGrupo: {spec.chat_id}."


def _inline_article(*, result_id: str, title: str, description: str, text: str, markup: Any | None = None) -> Any:
    if InlineQueryResultArticle is None or InputTextMessageContent is None:  # pragma: no cover
        return {"id": result_id, "title": title, "description": description, "text": text, "reply_markup": markup}
    return InlineQueryResultArticle(
        id=result_id[:64],
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(message_text=text),
        reply_markup=markup,
    )


def build_x9_inline_results(query: str, *, authorized: bool) -> list[Any]:
    if not authorized:
        return [
            _inline_article(
                result_id="x9-denied",
                title="Acesso negado",
                description="Somente usuários autorizados podem usar o X9.",
                text=X9_ACCESS_DENIED_TEXT,
                markup=None,
            )
        ]
    spec = parse_x9_query(query)
    if spec.target_user_id is None:
        title = "Rodemotain X9 — funções do grupo"
        description = "Use no grupo ou informe user_id chat_id quando estiver fora."
    elif spec.chat_id is None:
        title = f"Rodemotain X9 — alvo {spec.target_user_id}"
        description = "Use no grupo atual ou informe também o chat_id."
    else:
        title = f"Rodemotain X9 — alvo {spec.target_user_id}"
        description = f"Ações serão aplicadas no grupo {spec.chat_id}."
    return [
        _inline_article(
            result_id=f"x9-{spec.target_user_id or 0}-{spec.chat_id or 0}",
            title=title,
            description=description,
            text=x9_inline_message_text(spec),
            markup=x9_action_keyboard(spec),
        )
    ]


async def _delete_message_later(bot: Any, *, chat_id: int, message_id: int, delay_seconds: int = X9_AUTO_DELETE_SECONDS) -> None:
    try:
        await asyncio.sleep(delay_seconds)
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        logger.debug("RODEMOTAIN_X9_AUTO_DELETE_FAILED", exc_info=True)


def _schedule_delete_callback_message(bot: Any, callback: Any, *, delay_seconds: int = X9_AUTO_DELETE_SECONDS) -> None:
    message = _callback_message(callback)
    chat = getattr(message, "chat", None) if message is not None else None
    chat_id = getattr(chat, "id", None)
    message_id = getattr(message, "message_id", None)
    if bot is None or chat_id is None or message_id is None:
        return
    try:
        asyncio.create_task(_delete_message_later(bot, chat_id=int(chat_id), message_id=int(message_id), delay_seconds=delay_seconds))
    except RuntimeError:
        logger.debug("RODEMOTAIN_X9_AUTO_DELETE_SCHEDULE_FAILED", exc_info=True)


async def _safe_edit(callback: Any, text: str, markup: Any | None = None) -> None:
    message = _callback_message(callback)
    if message is not None and hasattr(message, "edit_text"):
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:
            logger.debug("RODEMOTAIN_X9_EDIT_FAILED", exc_info=True)
    try:
        await callback.answer(text[:200], show_alert=False)
    except Exception:
        logger.debug("RODEMOTAIN_X9_CALLBACK_ANSWER_FAILED", exc_info=True)


def _confirmation_text(action: str, *, chat_id: int, target_user_id: int | None) -> str:
    label = TARGET_ACTIONS.get(action) or GROUP_ACTIONS.get(action) or action
    lines = ["Confirmar ação X9", f"Ação: {label}", f"Grupo: {chat_id}"]
    if target_user_id is not None:
        lines.append(f"Alvo: {target_user_id}")
    lines.append("\nA execução será registrada em log.")
    return "\n".join(lines)


def _confirm_markup(action: str, target_user_id: int | None, chat_id: int) -> Any:
    return _markup([
        [("Confirmar", _callback_data("do", action, target_user_id, chat_id))],
        [("Cancelar", _callback_data("cancel", "none", target_user_id, chat_id))],
    ])


async def _target_is_admin(bot: Any, *, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        status = getattr(getattr(member, "status", None), "value", getattr(member, "status", None))
        return str(status) in {"administrator", "creator"}
    except Exception:
        return False


async def _execute_x9_action(bot: Any, callback: Any, *, action: str, target_user_id: int | None, chat_id: int) -> AdvancedActionResult:
    actor_user_id = _uid(callback) or 0
    chat_title = _chat_title(callback, chat_id)
    permissions = await get_bot_permissions(bot, chat_id)

    if action in {"admins", "protstatus"}:
        if action == "admins":
            text = await format_admin_audit(bot, chat_id=chat_id)
        else:
            text = format_protection_status(chat_id=chat_id)
        return AdvancedActionResult(True, "concluido", text)

    if action in {"lock", "unlock"}:
        return await set_group_lockdown(
            bot,
            chat_id=chat_id,
            chat_title=chat_title,
            actor_user_id=actor_user_id,
            permissions=permissions,
            locked=action == "lock",
        )

    if action == "warn":
        if target_user_id is None:
            return AdvancedActionResult(False, "bloqueado_alvo_invalido", "ID de usuário obrigatório.")
        if is_protected_target(target_user_id, owner_ids=TIGRAO_BOT_ACCESS_USER_IDS):
            return AdvancedActionResult(False, "bloqueado_alvo_protegido", "Ação bloqueada: alvo protegido.")
        return add_warning_action(
            chat_id=chat_id,
            chat_title=chat_title,
            actor_user_id=actor_user_id,
            user_id=target_user_id,
            reason="Advertência via X9 inline.",
        )

    if action in {"ban", "unban", "mute1h", "mute24h", "muteforever", "unmute"}:
        if target_user_id is None:
            return AdvancedActionResult(False, "bloqueado_alvo_invalido", "ID de usuário obrigatório.")
        try:
            me = await bot.get_me()
            bot_user_id = int(getattr(me, "id"))
        except Exception:
            bot_user_id = None
        target_admin = await _target_is_admin(bot, chat_id=chat_id, user_id=target_user_id)
        request = DestructiveActionRequest(
            action=action,
            chat_id=chat_id,
            chat_title=chat_title,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            confirmed=True,
            target_is_admin=target_admin,
        )
        return await execute_destructive_action(bot, request, permissions=permissions, bot_user_id=bot_user_id)

    return AdvancedActionResult(False, "bloqueado_acao_desconhecida", "Ação X9 desconhecida.")


async def _handle_x9_callback(callback: Any, bot: Any) -> None:
    actor_user_id = _uid(callback)
    if not _authorized(actor_user_id):
        await callback.answer(X9_ACCESS_DENIED_TEXT, show_alert=True)
        return
    parsed = parse_x9_callback(getattr(callback, "data", "") or "")
    if parsed is None:
        await callback.answer("X9 inválido.", show_alert=True)
        return
    kind, action, target_user_id, explicit_chat_id = parsed

    if kind == "cancel":
        await _safe_edit(callback, "Ação X9 cancelada.")
        _schedule_delete_callback_message(bot, callback)
        await callback.answer()
        return

    chat_id = _resolve_chat_id(callback, explicit_chat_id)
    if chat_id is None:
        await callback.answer(X9_NEEDS_CHAT_TEXT, show_alert=True)
        return

    if kind == "ask" and action in {"admins", "protstatus"}:
        result = await _execute_x9_action(bot, callback, action=action, target_user_id=target_user_id, chat_id=chat_id)
        prefix = "✅ Consulta concluída." if result.ok else "⚠️ Consulta falhou."
        await _safe_edit(callback, f"{prefix}\n\n{result.detail}")
        _schedule_delete_callback_message(bot, callback)
        await callback.answer()
        return

    if kind == "ask":
        if action in TARGET_ACTIONS and target_user_id is None:
            await callback.answer("ID de usuário obrigatório.", show_alert=True)
            return
        await _safe_edit(callback, _confirmation_text(action, chat_id=chat_id, target_user_id=target_user_id), _confirm_markup(action, target_user_id, chat_id))
        await callback.answer()
        return

    if kind == "do":
        result = await _execute_x9_action(bot, callback, action=action, target_user_id=target_user_id, chat_id=chat_id)
        prefix = "✅ Ação feita com sucesso." if result.ok else "⚠️ Ação não concluída."
        await _safe_edit(callback, f"{prefix}\n\n{result.detail}\n\nEsta mensagem será apagada em 1 minuto.")
        _schedule_delete_callback_message(bot, callback)
        await callback.answer()
        return

    await callback.answer()


if router is not None:  # pragma: no cover - exercido em runtime com aiogram instalado

    @router.inline_query()
    async def rodemotain_x9_inline_query(inline_query: InlineQuery, bot: Any) -> None:
        user_id = _uid(inline_query)
        results = build_x9_inline_results(getattr(inline_query, "query", "") or "", authorized=_authorized(user_id))
        await bot.answer_inline_query(
            inline_query_id=inline_query.id,
            results=results,
            cache_time=0,
            is_personal=True,
        )

    @router.callback_query(F.data.startswith(X9_CALLBACK_PREFIX))
    async def rodemotain_x9_callback(callback: CallbackQuery, bot: Any) -> None:
        await _handle_x9_callback(callback, bot)

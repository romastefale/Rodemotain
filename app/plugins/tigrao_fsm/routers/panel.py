"""Router real mínimo do painel Tigrão FSM."""
from __future__ import annotations

import asyncio
import logging
import json
import traceback
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, Filter
from aiogram.types import CallbackQuery, Message
try:
    from aiogram.types import BufferedInputFile
except Exception:  # pragma: no cover
    BufferedInputFile = None

from app.config.settings import DATA_DIR, BASE_URL, WEBHOOK_PATH, WEBHOOK_SECRET, RUN_POLLING, SET_WEBHOOK_ON_STARTUP, ALLOWED_UPDATES, TIGRAO_BOT_ACCESS_USER_IDS, TIGRAO_JOIN_REQUEST_WEBAPP_URL
from app.bot.group_registry import list_groups, remember_group

from .. import storage
from ..keyboards import (
    action_category_keyboard,
    action_category_title,
    action_category_parent,
    is_action_category_key,
    back_close_keyboard,
    confirm_cancel_keyboard,
    ddx_keyboard,
    destructive_actions_keyboard,
    group_admin_keyboard,
    group_selection_keyboard,
    home_keyboard,
    join_auto_question_keyboard,
    join_requests_keyboard,
    join_pending_keyboard,
    join_links_keyboard,
    join_auto_keyboard,
    logs_keyboard,
    parse_callback,
    post_action_keyboard,
    button,
    make_callback,
    to_inline_keyboard_markup,
)
from ..parsers import (
    parse_ddx_filter_input,
    parse_message_ids,
    parse_message_ref,
    parse_reaction_target,
    parse_timed_user_action,
    parse_user_ids,
    parse_admin_role_action,
    parse_admin_title_action,
    parse_sender_chat_action,
    parse_invite_create_action,
    parse_invite_edit_action,
    parse_invite_link_ref,
    parse_user_text_action,
    parse_topic_create_action,
    parse_topic_edit_action,
    parse_thread_id,
    parse_antiflood_setting,
    parse_antiraid_setting,
    parse_captcha_setting,
)
from ..destructive_actions import DestructiveActionRequest, execute_destructive_action, is_protected_target
from ..advanced_actions import (
    AdvancedActionResult,
    ban_user_custom,
    delete_all_message_reactions,
    delete_message_reaction,
    format_admin_audit,
    mute_user_custom,
    pin_message,
    purge_messages,
    set_group_description,
    set_group_lockdown,
    set_group_title,
    unpin_all_messages,
    unpin_message,
    promote_user_admin,
    demote_user_admin,
    set_admin_custom_title,
    ban_sender_chat,
    unban_sender_chat,
    export_primary_invite_link,
    create_invite_link_full,
    edit_invite_link_full,
    revoke_invite_link_full,
    set_member_tag_action,
    delete_group_photo,
    set_group_photo_file,
    create_forum_topic_action,
    edit_forum_topic_action,
    manage_forum_topic_action,
    manage_general_forum_topic_action,
    add_warning_action,
    clear_warning_action,
    format_warning_list,
    set_protection_action,
    format_protection_status,
    unlock_permissions,
)
from ..permissions import get_bot_permissions, is_authorized_user, permissions_from_chat_member
from ..services import approve_pending_join_request, create_join_request_link, decline_pending_join_request, format_logs
from ..state import close_session, create_session, get_session, get_user_session
from ..runtime.ddx_runtime import handle as ddx_handle
from ..runtime.join_request_runtime import handle as join_request_handle
from ..runtime.anti_flood_runtime import handle as anti_flood_handle

logger = logging.getLogger(__name__)
router = Router(name="tigrao_fsm_panel")

HOME_TEXT = "Rodemotain"
SESSION_EXPIRED_TEXT = "Sessão expirada. Use /tigrao novamente."
ENTRY_ACCESS_DENIED_TEXT = "Acesso negado.\nUse o botão para solucionar a entrada no grupo ou comando /captcha"
GROUP_COMMAND_TTL_SECONDS = 300
AUDIT_REPORT_TTL_SECONDS = 3600

START_TEXT_AUTHORIZED = """🐯 Rodemotain

Bot online.

/tigrao — abrir painel
/help — ver recursos

Use em DM para administrar seus grupos.
Ações sensíveis exigem Confirmar.
"""

START_TEXT_UNAUTHORIZED = ENTRY_ACCESS_DENIED_TEXT

HELP_TEXT_AUTHORIZED = """🐯 Rodemotain — ajuda

Comandos:
/start — status rápido
/help — esta ajuda
/tigrao — painel em DM
/diagnostico — relatório seguro .txt
/diagnostico_total — teste real em grupo de teste
/captcha código — fallback de entrada

No painel:
📥 entrada e links
👤 usuários e warns
💬 mensagens e reações
👑 admins — promover/rebaixar administradores
🎛️ grupo
🛡️ proteções — anti-raid e anti-flood
🧨 DDX
📊 logs

Ações sensíveis sempre pedem confirmação.
"""

HELP_TEXT_UNAUTHORIZED = ENTRY_ACCESS_DENIED_TEXT


def _uid(obj: Any) -> int | None:
    user = getattr(obj, "from_user", None)
    try:
        return int(getattr(user, "id"))
    except Exception:
        return None


def _authorized(user_id: int | None) -> bool:
    return is_authorized_user(user_id, owner_ids=TIGRAO_BOT_ACCESS_USER_IDS)


def _chat_type(chat: Any) -> str | None:
    value = getattr(chat, "type", None)
    value = getattr(value, "value", value)
    return str(value) if value is not None else None


def _remember_group_chat(chat: Any) -> None:
    try:
        remember_group(
            chat_id=int(getattr(chat, "id")),
            title=getattr(chat, "title", None),
            username=getattr(chat, "username", None),
            chat_type=_chat_type(chat),
        )
    except Exception:
        logger.debug("TIGRAO_REMEMBER_GROUP_FAILED", exc_info=True)


class TigraoGroupSurfaceFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return _chat_type(getattr(message, "chat", None)) in {"group", "supergroup"}


class TigraoWaitingTextFilter(Filter):
    """Permite capturar texto privado somente quando o painel espera resposta.

    Sem este filtro, um handler genérico de texto do Tigrão poderia interceptar
    mensagens privadas comuns do owner/moderador e impedir outros fluxos do bot.
    """

    async def __call__(self, message: Message) -> bool:
        user_id = _uid(message)
        if not _authorized(user_id):
            return False
        chat = getattr(message, "chat", None)
        if _chat_type(chat) != "private":
            return False
        session = get_user_session(user_id)
        return bool(session is not None and session.waiting_for)



def _flow_prompt_location_from_message(message: Any) -> tuple[int | None, int | None]:
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    message_id = getattr(message, "message_id", None)
    try:
        return (None if chat_id is None else int(chat_id), None if message_id is None else int(message_id))
    except Exception:
        return None, None


def _remember_flow_prompt(session: Any, message: Any) -> None:
    """Guarda a mensagem editada que virou instrução transitória do fluxo."""
    chat_id, message_id = _flow_prompt_location_from_message(message)
    if chat_id is None or message_id is None:
        return
    session.payload["flow_prompt_chat_id"] = chat_id
    session.payload["flow_prompt_message_id"] = message_id


def _forget_flow_prompt(session: Any) -> None:
    session.payload.pop("flow_prompt_chat_id", None)
    session.payload.pop("flow_prompt_message_id", None)


async def _delete_flow_prompt(bot: Any, session: Any) -> None:
    """Apaga a mensagem antiga do fluxo antes de criar nova confirmação/resultado."""
    chat_id = session.payload.pop("flow_prompt_chat_id", None)
    message_id = session.payload.pop("flow_prompt_message_id", None)
    if bot is None or chat_id is None or message_id is None:
        return
    try:
        await bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))
    except Exception:
        logger.debug("RODEMOTAIN_FLOW_PROMPT_DELETE_FAILED", exc_info=True)


async def _send_flow_confirmation(message: Message, bot: Any, session: Any, text: str) -> None:
    await _delete_flow_prompt(bot, session)
    await message.answer(text, reply_markup=to_inline_keyboard_markup(confirm_cancel_keyboard(session.session_id)))


async def _send_flow_result(message: Message, bot: Any, session: Any, text: str) -> None:
    await _delete_flow_prompt(bot, session)
    await message.answer(text, reply_markup=to_inline_keyboard_markup(post_action_keyboard(session.session_id)))


def _extract_invite_link(text: str) -> str | None:
    for token in str(text or "").replace("\n", " ").split():
        clean = token.strip(" <>.,;()[]{}\"'")
        if clean.startswith("https://t.me/") or clean.startswith("http://t.me/") or clean.startswith("t.me/"):
            return clean
    return None


async def _send_persistent_invite_link(callback: CallbackQuery, *, chat_title: str, link: str, label: str) -> None:
    """Envia o link em mensagem individual separada, fora do fluxo apagável/editável."""
    message = getattr(callback, "message", None)
    if message is None or not hasattr(message, "answer"):
        return
    text = f"{label}\nGrupo: {chat_title}\n\n{link}"
    try:
        await message.answer(text)
    except Exception:
        logger.debug("RODEMOTAIN_PERSISTENT_INVITE_LINK_SEND_FAILED", exc_info=True)


def _clean_telegram_error(detail: str) -> str:
    text = str(detail or "").strip()
    for prefix in (
        "Falha Telegram: Telegram server says - Bad Request: ",
        "Telegram server says - Bad Request: ",
        "Falha Telegram: ",
    ):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    known = {
        "RIGHT_FORBIDDEN": "O Telegram recusou os direitos solicitados. O alvo precisa estar no grupo, e o bot só pode conceder permissões que ele próprio possui.",
        "USER_NOT_PARTICIPANT": "O usuário ainda não está no grupo. Envie um link de entrada e promova depois que ele entrar.",
        "CHAT_ADMIN_REQUIRED": "O bot precisa ser administrador com a permissão correta para esta ação.",
    }
    return known.get(text, text or "Falha sem detalhe informado.")


def _result_message(ok: bool, result: str, detail: str) -> str:
    status = "✅ Concluído" if ok else "⚠️ Não concluído"
    return f"{status}\n{_clean_telegram_error(detail)}\n\nO que deseja fazer agora?"
def _confirm_text(session: Any, action: str, details: list[str]) -> str:
    chat_id, title, _ = _selected_group_or_text(session)
    lines = [
        "Confirmar",
        f"Grupo: {title}",
        f"Ação: {_ACTION_LABELS.get(action, action)}",
    ]
    lines.extend(str(item) for item in details if str(item).strip())
    lines.append("Toque em Confirmar para executar.")
    return "\n".join(lines)


def _home_markup(session_id: str) -> Any:
    return to_inline_keyboard_markup(home_keyboard(session_id))


async def _safe_edit(callback: CallbackQuery, text: str, markup: Any) -> None:
    """Edita a mensagem do painel e cai para answer sem quebrar o fluxo.

    Callbacks repetidos, mensagens antigas ou mensagens já apagadas podem fazer
    edit_text falhar. O painel não deve travar por isso.
    """
    message = callback.message
    if message is not None and hasattr(message, "edit_text"):
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:
            logger.debug("TIGRAO_SAFE_EDIT_FAILED", exc_info=True)
    try:
        await callback.answer()
    except Exception:
        logger.debug("TIGRAO_CALLBACK_ANSWER_FAILED", exc_info=True)



async def _safe_edit_flow_prompt(callback: CallbackQuery, session: Any, text: str, markup: Any) -> None:
    """Edita a mensagem como instrução transitória e guarda para limpeza futura."""
    await _safe_edit(callback, text, markup)
    if callback.message is not None:
        _remember_flow_prompt(session, callback.message)


async def _delete_message_later(bot: Any, *, chat_id: int, message_id: int, delay_seconds: int = GROUP_COMMAND_TTL_SECONDS) -> None:
    """Apaga uma mensagem depois de um intervalo sem bloquear o handler."""
    try:
        await asyncio.sleep(delay_seconds)
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        logger.debug("RODEMOTAIN_TEMP_MESSAGE_DELETE_FAILED", exc_info=True)


def _schedule_delete_message(bot: Any, *, chat_id: int | None, message_id: int | None, delay_seconds: int = GROUP_COMMAND_TTL_SECONDS) -> None:
    if bot is None or chat_id is None or message_id is None:
        return
    try:
        asyncio.create_task(_delete_message_later(bot, chat_id=int(chat_id), message_id=int(message_id), delay_seconds=delay_seconds))
    except RuntimeError:
        logger.debug("RODEMOTAIN_TEMP_MESSAGE_SCHEDULE_FAILED", exc_info=True)


async def _answer_group_temporarily(message: Message, bot: Any, text: str) -> None:
    """Responde em grupo e programa remoção automática da resposta em 5 minutos."""
    try:
        sent = await message.answer(text)
    except Exception:
        logger.debug("RODEMOTAIN_GROUP_TEMP_ANSWER_FAILED", exc_info=True)
        return
    chat = getattr(sent, "chat", None) or getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    message_id = getattr(sent, "message_id", None)
    _schedule_delete_message(bot, chat_id=chat_id, message_id=message_id)





def _safe_getattr_value(obj: Any, name: str, default: Any = None) -> Any:
    value = getattr(obj, name, default)
    value = getattr(value, "value", value)
    return value


def _yes_no(value: Any) -> str:
    return "sim" if bool(value) else "não"


def _format_permission_lines(perms: Any) -> list[str]:
    flags = [
        ("administrador", getattr(perms, "is_admin", False)),
        ("gerenciar chat", getattr(perms, "can_manage_chat", False)),
        ("apagar mensagens/DDX/reações", getattr(perms, "can_delete_messages", False)),
        ("restringir, mutar e banir", getattr(perms, "can_restrict_members", False)),
        ("promover/rebaixar admins", getattr(perms, "can_promote_members", False)),
        ("alterar dados do grupo", getattr(perms, "can_change_info", False)),
        ("links e solicitações de entrada", getattr(perms, "can_invite_users", False)),
        ("fixar mensagens", getattr(perms, "can_pin_messages", False)),
        ("tags de membros", getattr(perms, "can_manage_tags", False)),
    ]
    active = [label for label, ok in flags if ok]
    missing = [label for label, ok in flags if not ok]
    return [
        "Permissões ativas: " + (", ".join(active) if active else "nenhuma"),
        "Permissões ausentes: " + (", ".join(missing) if missing else "nenhuma crítica"),
    ]


def _safe_filename_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _serialize_object_public(obj: Any) -> dict[str, Any]:
    """Extrai campos úteis sem despejar token/payload inteiro no relatório."""
    fields = (
        "id", "username", "first_name", "last_name", "title", "type", "status",
        "url", "pending_update_count", "last_error_date", "last_error_message",
        "max_connections", "allowed_updates", "bio", "description", "invite_link",
    )
    result: dict[str, Any] = {}
    for field in fields:
        try:
            value = getattr(obj, field)
        except Exception:
            continue
        value = getattr(value, "value", value)
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            result[field] = value
        elif isinstance(value, (list, tuple)):
            result[field] = [getattr(v, "value", v) for v in value]
        else:
            result[field] = str(value)
    return result


async def _get_admins_compat(bot: Any, chat_id: int) -> list[Any]:
    try:
        return list(await bot.get_chat_administrators(chat_id=chat_id, return_bots=True))
    except TypeError:
        return list(await bot.get_chat_administrators(chat_id=chat_id))


async def _run_real_diagnostic(bot: Any, *, actor_user_id: int, request_chat: Any | None, explicit_chat_id: int | None = None) -> tuple[Path, str]:
    """Executa diagnóstico real sem ações destrutivas e salva relatório .txt."""
    started = datetime.now(timezone.utc)
    run_id = f"diag_{started.strftime('%Y%m%d_%H%M%S')}_{actor_user_id}"
    surface = "dm" if _chat_type(request_chat) == "private" else "grupo"
    request_chat_id = None
    request_chat_title = None
    if request_chat is not None:
        try:
            request_chat_id = int(getattr(request_chat, "id"))
        except Exception:
            request_chat_id = None
        request_chat_title = getattr(request_chat, "title", None)
    storage.log_event(
        action="diagnostic_start",
        result="iniciado",
        detection="direta",
        surface=surface,
        chat_id=request_chat_id if _chat_type(request_chat) in {"group", "supergroup"} else None,
        chat_title=request_chat_title,
        actor_user_id=actor_user_id,
        details="Diagnóstico real iniciado pelo operador autorizado.",
        metadata={"run_id": run_id},
    )

    lines: list[str] = []
    lines.append("RODEMOTAIN — DIAGNÓSTICO REAL")
    lines.append("=" * 34)
    lines.append(f"Run ID: {run_id}")
    lines.append(f"Início: {started.isoformat()}")
    lines.append(f"Operador: {actor_user_id}")
    lines.append(f"Superfície: {surface}")
    lines.append("")

    def section(title: str) -> None:
        lines.append("")
        lines.append(title.upper())
        lines.append("-" * len(title))

    me = None
    section("1. Configuração")
    lines.append(f"BASE_URL: {BASE_URL or 'não definido'}")
    lines.append(f"WEBHOOK_PATH: {WEBHOOK_PATH}")
    lines.append(f"WEBHOOK_SECRET: {'definido' if WEBHOOK_SECRET else 'não definido'}")
    lines.append(f"RUN_POLLING: {_yes_no(RUN_POLLING)}")
    lines.append(f"SET_WEBHOOK_ON_STARTUP: {_yes_no(SET_WEBHOOK_ON_STARTUP)}")
    lines.append(f"Mini App entrada: {TIGRAO_JOIN_REQUEST_WEBAPP_URL or 'não definido'}")
    lines.append(f"Allowed updates: {', '.join(ALLOWED_UPDATES)}")
    lines.append(f"DATA_DIR: {DATA_DIR}")
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / f".{run_id}.probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        lines.append("DATA_DIR gravável: sim")
    except Exception as exc:
        lines.append(f"DATA_DIR gravável: não — {type(exc).__name__}: {exc}")

    section("2. Bot API")
    try:
        me = await bot.get_me()
        info = _serialize_object_public(me)
        lines.append(f"getMe: sucesso")
        lines.append(f"Bot: {info.get('first_name') or 'sem nome'} @{info.get('username') or 'sem username'}")
        lines.append(f"ID do bot: {info.get('id')}")
        storage.log_event(action="diagnostic_get_me", result="ok", detection="direta", surface=surface, actor_user_id=actor_user_id, details="getMe executado com sucesso.", metadata={"run_id": run_id, "bot": info})
    except Exception as exc:
        lines.append(f"getMe: falhou — {type(exc).__name__}: {exc}")
        storage.log_event(action="diagnostic_get_me", result="falhou", detection="direta", surface=surface, actor_user_id=actor_user_id, details=str(exc), metadata={"run_id": run_id})

    try:
        webhook = await bot.get_webhook_info()
        info = _serialize_object_public(webhook)
        lines.append("getWebhookInfo: sucesso")
        lines.append(f"Webhook URL: {info.get('url') or 'vazio'}")
        lines.append(f"Updates pendentes: {info.get('pending_update_count', 'não informado')}")
        if info.get("last_error_message"):
            lines.append(f"Último erro do webhook: {info.get('last_error_message')}")
        storage.log_event(action="diagnostic_webhook", result="ok", detection="direta", surface=surface, actor_user_id=actor_user_id, details="getWebhookInfo executado com sucesso.", metadata={"run_id": run_id, "webhook": info})
    except Exception as exc:
        lines.append(f"getWebhookInfo: falhou — {type(exc).__name__}: {exc}")
        storage.log_event(action="diagnostic_webhook", result="falhou", detection="direta", surface=surface, actor_user_id=actor_user_id, details=str(exc), metadata={"run_id": run_id})

    try:
        commands = await bot.get_my_commands()
        labels = [f"/{getattr(cmd, 'command', '')}" for cmd in commands]
        lines.append(f"Comandos registrados: {', '.join(labels) if labels else 'nenhum'}")
    except Exception as exc:
        lines.append(f"getMyCommands: falhou — {type(exc).__name__}: {exc}")

    section("3. Banco e logs")
    try:
        storage.ensure_tables()
        log_id = storage.log_event(
            action="diagnostic_storage_write",
            result="ok",
            detection="direta",
            surface=surface,
            chat_id=request_chat_id if _chat_type(request_chat) in {"group", "supergroup"} else None,
            chat_title=request_chat_title,
            actor_user_id=actor_user_id,
            details="Escrita real de auditoria confirmada no banco.",
            metadata={"run_id": run_id},
        )
        lines.append(f"Escrita no banco: sucesso — log_id {log_id}")
        recent_count = len(storage.list_logs(limit=10))
        lines.append(f"Leitura de logs recentes: sucesso — {recent_count} item(ns)")
    except Exception as exc:
        lines.append(f"Banco/logs: falhou — {type(exc).__name__}: {exc}")

    section("4. Grupos conhecidos e permissões")
    candidates: list[dict[str, Any]] = []
    seen_chat_ids: set[int] = set()

    def add_candidate(chat_id: int | None, title: str | None = None, source: str = "manual") -> None:
        if chat_id is None:
            return
        if int(chat_id) in seen_chat_ids:
            return
        seen_chat_ids.add(int(chat_id))
        candidates.append({"chat_id": int(chat_id), "title": title, "source": source})

    add_candidate(explicit_chat_id, source="comando")
    if _chat_type(request_chat) in {"group", "supergroup"}:
        add_candidate(request_chat_id, request_chat_title, "grupo_atual")
    for group in list_groups(limit=25):
        add_candidate(int(group["chat_id"]), str(group.get("title") or group.get("chat_id")), "registro")

    if not candidates:
        lines.append("Nenhum grupo conhecido. Adicione o bot a um grupo e envie uma mensagem/comando para registrar.")
    bot_id = None
    if me is not None:
        try:
            bot_id = int(getattr(me, "id"))
        except Exception:
            bot_id = None
    for index, item in enumerate(candidates[:25], start=1):
        chat_id = int(item["chat_id"])
        title = str(item.get("title") or chat_id)
        lines.append("")
        lines.append(f"Grupo {index}: {title}")
        lines.append(f"ID: {chat_id}")
        lines.append(f"Origem: {item.get('source')}")
        check_result = "ok"
        check_detail: list[str] = []
        try:
            chat = await bot.get_chat(chat_id)
            chat_info = _serialize_object_public(chat)
            if chat_info.get("title"):
                title = str(chat_info.get("title"))
            lines.append(f"getChat: sucesso — {title}")
            if chat_info.get("username"):
                lines.append(f"Username do grupo: @{chat_info.get('username')}")
            check_detail.append("getChat ok")
        except Exception as exc:
            check_result = "falhou"
            lines.append(f"getChat: falhou — {type(exc).__name__}: {exc}")
            check_detail.append(f"getChat falhou: {exc}")
        if bot_id is not None:
            try:
                member = await bot.get_chat_member(chat_id, bot_id)
                status = _safe_getattr_value(member, "status", "desconhecido")
                perms = permissions_from_chat_member(member)
                lines.append(f"Status do bot: {status}")
                lines.extend(_format_permission_lines(perms))
                if not perms.is_admin:
                    lines.append("Alerta: o bot não está como administrador neste grupo.")
                if not perms.can_delete_messages:
                    lines.append("Alerta: sem apagar mensagens/DDX/reações.")
                if not perms.can_restrict_members:
                    lines.append("Alerta: sem ban/mute/restrições.")
                if not perms.can_invite_users:
                    lines.append("Alerta: sem links e aprovação de entrada.")
                check_detail.append("getChatMember ok")
            except Exception as exc:
                check_result = "falhou"
                lines.append(f"getChatMember(bot): falhou — {type(exc).__name__}: {exc}")
                check_detail.append(f"getChatMember falhou: {exc}")
        try:
            admins = await _get_admins_compat(bot, chat_id)
            bot_admins = [adm for adm in admins if bool(getattr(getattr(adm, "user", None), "is_bot", False))]
            lines.append(f"Administradores: {len(admins)} total; bots admins: {len(bot_admins)}")
            for adm in bot_admins[:8]:
                user = getattr(adm, "user", None)
                uname = getattr(user, "username", None)
                uid = getattr(user, "id", None)
                st = _safe_getattr_value(adm, "status", "desconhecido")
                lines.append(f"  • @{uname or 'sem_username'} — ID {uid} — {st}")
            check_detail.append("getChatAdministrators ok")
        except Exception as exc:
            check_result = "falhou"
            lines.append(f"getChatAdministrators: falhou — {type(exc).__name__}: {exc}")
            check_detail.append(f"getChatAdministrators falhou: {exc}")
        storage.log_event(
            action="diagnostic_group_check",
            result=check_result,
            detection="direta",
            surface=surface,
            chat_id=chat_id,
            chat_title=title,
            actor_user_id=actor_user_id,
            details="\n".join(check_detail),
            metadata={"run_id": run_id, "source": item.get("source")},
        )

    section("5. Logs recentes do Rodemotain")
    try:
        rows = storage.list_logs(limit=20)
        formatted = format_logs(rows)
        lines.append(formatted)
    except Exception as exc:
        lines.append(f"Falhou ao formatar logs recentes: {type(exc).__name__}: {exc}")

    finished = datetime.now(timezone.utc)
    duration = (finished - started).total_seconds()
    storage.log_event(
        action="diagnostic_finished",
        result="concluido",
        detection="direta",
        surface=surface,
        chat_id=request_chat_id if _chat_type(request_chat) in {"group", "supergroup"} else None,
        chat_title=request_chat_title,
        actor_user_id=actor_user_id,
        details=f"Diagnóstico concluído em {duration:.2f}s. Relatório salvo e enviado em DM quando possível.",
        metadata={"run_id": run_id, "duration_seconds": duration, "groups_checked": len(candidates[:25])},
    )
    section("6. Fechamento")
    lines.append(f"Fim: {finished.isoformat()}")
    lines.append(f"Duração: {duration:.2f}s")
    lines.append("Observação: o teste não executa ações destrutivas. Ele consulta permissões, webhook, comandos, grupos e grava logs reais de auditoria.")
    text = "\n".join(lines).strip() + "\n"
    reports_dir = DATA_DIR / "audit_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"rodemotain_diagnostico_{_safe_filename_timestamp()}_{actor_user_id}.txt"
    path.write_text(text, encoding="utf-8")
    return path, text



class _AuditMemoryHandler(logging.Handler):
    """Handler temporário para capturar logs emitidos durante uma auditoria."""

    def __init__(self, run_id: str, max_records: int = 1000) -> None:
        super().__init__(level=logging.DEBUG)
        self.run_id = str(run_id)
        self.max_records = int(max_records)
        self.records: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - logging não deve quebrar teste
        try:
            if len(self.records) >= self.max_records:
                return
            exc_text = None
            if record.exc_info:
                exc_text = "".join(traceback.format_exception(*record.exc_info))
            audit_data = getattr(record, "audit_data", None)
            self.records.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "audit_data": _json_safe(audit_data),
                "exception": exc_text,
            })
        except Exception:
            pass


class _AuditCapture:
    """Captura separada de eventos, erros e raw data durante diagnóstico."""

    def __init__(self, run_id: str) -> None:
        self.run_id = str(run_id)
        self.handler = _AuditMemoryHandler(run_id=run_id)
        self.started = False

    def start(self) -> None:
        if self.started:
            return
        logging.getLogger().addHandler(self.handler)
        self.started = True

    def stop(self) -> list[dict[str, Any]]:
        if self.started:
            try:
                logging.getLogger().removeHandler(self.handler)
            except Exception:
                pass
            self.started = False
        return list(self.handler.records)


def _json_safe(value: Any, *, limit: int = 6000) -> Any:
    """Converte objetos para JSON de auditoria sem quebrar o relatório."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, limit=limit) for item in list(value)[:80]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 80:
                out["__truncated__"] = True
                break
            out[str(key)] = _json_safe(item, limit=limit)
        return out
    data = getattr(value, "model_dump", None)
    if callable(data):
        try:
            return _json_safe(data(), limit=limit)
        except Exception:
            pass
    data = getattr(value, "__dict__", None)
    if isinstance(data, dict):
        try:
            return _json_safe(data, limit=limit)
        except Exception:
            pass
    text = repr(value)
    if len(text) > limit:
        text = text[:limit] + "...<truncado>"
    return text


def _telegram_raw_error(exc: Exception | None = None, *, detail: str | None = None, value: Any | None = None) -> dict[str, Any] | None:
    """Raw data seguro para diferenciar erro real de evento normal."""
    if exc is None and not detail and value is None:
        return None
    raw: dict[str, Any] = {}
    if exc is not None:
        raw.update({
            "exception_type": type(exc).__name__,
            "exception_module": type(exc).__module__,
            "exception_message": str(exc),
            "exception_repr": repr(exc),
            "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        })
        for attr in ("message", "description", "error_code", "parameters", "method", "url"):
            if hasattr(exc, attr):
                raw[attr] = _json_safe(getattr(exc, attr))
    if detail:
        raw["detail"] = str(detail)
        raw["detail_clean"] = _clean_telegram_error(str(detail))
    if value is not None:
        raw["returned_object"] = _json_safe(value)
    return raw


def _audit_kind(*, ok: bool, detail: str = "") -> str:
    if ok:
        return "evento"
    cleaned = str(detail or "").upper()
    if any(token in cleaned for token in ("RIGHT_FORBIDDEN", "CHAT_ADMIN_REQUIRED", "NOT ENOUGH RIGHTS", "PERMISSION", "PERMISS")):
        return "erro_permissao"
    if any(token in cleaned for token in ("USER_NOT_PARTICIPANT", "USER_ID_INVALID", "CHAT_NOT_FOUND")):
        return "erro_alvo_chat"
    if any(token in cleaned for token in ("TIMEOUT", "NETWORK", "CONNECTION")):
        return "erro_rede"
    return "erro_execucao"


def _append_audit_sections(lines: list[str], *, results: list[dict[str, Any]], process_logs: list[dict[str, Any]]) -> None:
    """Separa eventos de erros para evitar leitura equivocada no relatório final."""
    events = [row for row in results if row.get("ok") is True]
    failures = [row for row in results if row.get("ok") is not True]
    process_errors = [row for row in process_logs if str(row.get("level", "")).upper() in {"WARNING", "ERROR", "CRITICAL"}]

    lines.append("")
    lines.append("REGISTRO DE EVENTOS")
    lines.append("-------------------")
    if not events:
        lines.append("Nenhum evento de sucesso registrado.")
    for row in events:
        lines.append(f"• OK | {row.get('name')} | {row.get('duration_ms')} ms | {row.get('detail')}")

    lines.append("")
    lines.append("REGISTRO DE ERROS")
    lines.append("-----------------")
    if not failures and not process_errors:
        lines.append("Nenhum erro real registrado durante o teste.")
    for row in failures:
        lines.append(f"• {row.get('audit_kind', 'erro')} | {row.get('name')} | {row.get('duration_ms')} ms")
        lines.append(f"  Detalhe: {_clean_telegram_error(str(row.get('detail') or ''))}")
    for row in process_errors[:80]:
        lines.append(f"• {row.get('level')} | {row.get('logger')} | {row.get('message')}")

    lines.append("")
    lines.append("RAW DATA DE ERROS")
    lines.append("------------------")
    raw_errors = []
    for row in failures:
        raw_errors.append({
            "name": row.get("name"),
            "action": row.get("action"),
            "audit_kind": row.get("audit_kind"),
            "result": row.get("result"),
            "duration_ms": row.get("duration_ms"),
            "raw_error": row.get("raw_error"),
        })
    for row in process_errors[:80]:
        raw_errors.append({"process_log": row})
    if not raw_errors:
        lines.append("[]")
    else:
        lines.append(json.dumps(_json_safe(raw_errors), ensure_ascii=False, indent=2))

    lines.append("")
    lines.append("RAW DATA DE EVENTOS")
    lines.append("-------------------")
    lines.append(json.dumps(_json_safe(events), ensure_ascii=False, indent=2))

    lines.append("")
    lines.append("LOGS DO PROCESSO DURANTE O TESTE")
    lines.append("--------------------------------")
    if not process_logs:
        lines.append("Nenhum log do processo foi capturado no período.")
    else:
        lines.append(json.dumps(_json_safe(process_logs), ensure_ascii=False, indent=2))


async def _delete_file_later(path: Path, *, delay_seconds: int = AUDIT_REPORT_TTL_SECONDS) -> None:
    try:
        await asyncio.sleep(delay_seconds)
        Path(path).unlink(missing_ok=True)
    except Exception:
        logger.debug("RODEMOTAIN_AUDIT_REPORT_FILE_DELETE_FAILED", exc_info=True)


def _schedule_delete_file(path: Path | None, *, delay_seconds: int = AUDIT_REPORT_TTL_SECONDS) -> None:
    if path is None:
        return
    try:
        asyncio.create_task(_delete_file_later(Path(path), delay_seconds=delay_seconds))
    except RuntimeError:
        logger.debug("RODEMOTAIN_AUDIT_REPORT_FILE_SCHEDULE_FAILED", exc_info=True)


def _format_total_status(ok: bool) -> str:
    return "OK" if ok else "FALHOU"


def _total_result_detail(result: Any) -> str:
    if hasattr(result, "detail"):
        return str(getattr(result, "detail"))
    return str(result) if result is not None else "sem detalhe"


async def _total_step(
    *,
    lines: list[str],
    results: list[dict[str, Any]],
    name: str,
    action: str,
    runner: Any,
    chat_id: int,
    chat_title: str,
    actor_user_id: int,
    target_user_id: int | None = None,
) -> Any:
    """Executa uma etapa real do diagnóstico total e registra em log/relatório."""
    started = datetime.now(timezone.utc)
    raw_error: dict[str, Any] | None = None
    try:
        value = await runner() if callable(runner) else runner
        ok = bool(getattr(value, "ok", True))
        detail = _total_result_detail(value)
        result_code = str(getattr(value, "result", "ok" if ok else "falhou"))
        if not ok:
            raw_error = _telegram_raw_error(detail=detail, value=value)
    except Exception as exc:
        value = None
        ok = False
        result_code = "falhou"
        detail = f"{type(exc).__name__}: {exc}"
        raw_error = _telegram_raw_error(exc, detail=detail)
    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    status = _format_total_status(ok)
    audit_kind = _audit_kind(ok=ok, detail=detail)
    lines.append(f"[{status}] {name} — {_clean_telegram_error(detail) if not ok else detail} ({duration_ms} ms)")
    row = {"name": name, "action": action, "ok": ok, "result": result_code, "detail": detail, "duration_ms": duration_ms, "audit_kind": audit_kind, "raw_error": raw_error}
    results.append(row)
    log_payload = {"diagnostic_step": row, "chat_id": chat_id, "target_user_id": target_user_id}
    if ok:
        logger.info("diagnostic_total_event", extra={"audit_data": log_payload})
    else:
        logger.error("diagnostic_total_error", extra={"audit_data": log_payload})
    storage.log_event(
        action=f"diagnostic_total_{action}",
        result="ok" if ok else "falhou",
        detection="direta",
        surface="diagnostico_total",
        chat_id=chat_id,
        chat_title=chat_title,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        details=detail,
        metadata={"duration_ms": duration_ms, "audit_kind": audit_kind, "raw_error": raw_error},
    )
    return value


def _extract_total_args(text: str, request_chat: Any | None) -> tuple[int | None, int | None, bool, str | None]:
    """Aceita: /diagnostico_total <chat_id> [user_id] CONFIRMO_TOTAL.

    Em grupo, também aceita /diagnostico_total CONFIRMO_TOTAL ou
    /diagnostico_total <user_id> CONFIRMO_TOTAL.
    """
    raw_parts = str(text or "").split()
    args = raw_parts[1:]
    if not args or args[-1].upper() != "CONFIRMO_TOTAL":
        return None, None, False, "Falta confirmação. Use CONFIRMO_TOTAL no final."
    args = args[:-1]
    chat_id: int | None = None
    target_user_id: int | None = None
    request_chat_type = _chat_type(request_chat)
    request_chat_id = getattr(request_chat, "id", None)
    if request_chat_type in {"group", "supergroup"}:
        try:
            chat_id = int(request_chat_id)
        except Exception:
            chat_id = None
    ints: list[int] = []
    for arg in args:
        try:
            ints.append(int(arg))
        except Exception:
            return None, None, False, f"Argumento inválido: {arg}"
    if chat_id is None:
        if not ints:
            return None, None, False, "Informe o ID do grupo."
        chat_id = ints[0]
        if len(ints) >= 2:
            target_user_id = ints[1]
    else:
        if len(ints) == 1:
            # Em grupo, número positivo é alvo; número negativo troca o grupo.
            if ints[0] < 0:
                chat_id = ints[0]
            else:
                target_user_id = ints[0]
        elif len(ints) >= 2:
            chat_id = ints[0]
            target_user_id = ints[1]
    return chat_id, target_user_id, True, None


def _is_member_admin(member: Any) -> bool:
    status = _safe_getattr_value(member, "status", "")
    return str(status) in {"administrator", "creator"}


def _chat_permissions_snapshot(chat: Any) -> Any | None:
    return getattr(chat, "permissions", None)


async def _restore_chat_permissions(bot: Any, chat_id: int, original_permissions: Any | None) -> None:
    if original_permissions is not None:
        await bot.set_chat_permissions(chat_id=chat_id, permissions=original_permissions, use_independent_chat_permissions=True)
    else:
        await bot.set_chat_permissions(chat_id=chat_id, permissions=unlock_permissions(), use_independent_chat_permissions=True)


async def _run_total_diagnostic(
    bot: Any,
    *,
    actor_user_id: int,
    request_chat: Any | None,
    chat_id: int,
    target_user_id: int | None = None,
) -> tuple[Path, str]:
    """Executa teste real total em grupo de teste. Sem alvo, recusa porque seria parcial."""
    if target_user_id is None:
        raise ValueError("diagnostico_total exige target_user_id para ser total. Use um membro comum de grupo de teste.")
    started = datetime.now(timezone.utc)
    run_id = f"total_{started.strftime('%Y%m%d_%H%M%S')}_{actor_user_id}"
    results: list[dict[str, Any]] = []
    lines: list[str] = [
        "RODEMOTAIN — DIAGNÓSTICO TOTAL REAL",
        "=" * 38,
        f"Run ID: {run_id}",
        f"Início: {started.isoformat()}",
        f"Operador: {actor_user_id}",
        f"Grupo testado: {chat_id}",
        f"Alvo de teste: {target_user_id if target_user_id else 'não informado'}",
        "",
        "Atenção: este modo executa ações reais no grupo informado e tenta restaurar tudo ao final.",
        "Use somente em grupo de teste.",
        "",
    ]
    storage.log_event(
        action="diagnostic_total_start",
        result="iniciado",
        detection="direta",
        surface="diagnostico_total",
        chat_id=chat_id,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        details="Diagnóstico total real iniciado com confirmação explícita.",
        metadata={"run_id": run_id},
    )
    audit_capture = _AuditCapture(run_id=run_id)
    audit_capture.start()
    logger.info("diagnostic_total_capture_started", extra={"audit_data": {"run_id": run_id, "chat_id": chat_id, "target_user_id": target_user_id}})

    me = await _total_step(
        lines=lines,
        results=results,
        name="Bot API / getMe",
        action="get_me",
        runner=lambda: bot.get_me(),
        chat_id=chat_id,
        chat_title=str(chat_id),
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
    )
    bot_id = None
    try:
        bot_id = int(getattr(me, "id"))
    except Exception:
        pass

    chat = await _total_step(
        lines=lines,
        results=results,
        name="Grupo / getChat",
        action="get_chat",
        runner=lambda: bot.get_chat(chat_id),
        chat_id=chat_id,
        chat_title=str(chat_id),
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
    )
    chat_title = str(getattr(chat, "title", None) or chat_id)
    original_title = str(getattr(chat, "title", None) or "")
    original_description = getattr(chat, "description", None)
    original_permissions = _chat_permissions_snapshot(chat)

    bot_member = await _total_step(
        lines=lines,
        results=results,
        name="Permissões do bot / getChatMember",
        action="get_bot_member",
        runner=lambda: bot.get_chat_member(chat_id, bot_id) if bot_id is not None else None,
        chat_id=chat_id,
        chat_title=chat_title,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
    )
    permissions = permissions_from_chat_member(bot_member) if bot_member is not None else await get_bot_permissions(bot, chat_id)
    lines.append("")
    lines.append("Permissões detectadas:")
    lines.extend(_format_permission_lines(permissions))
    lines.append("")

    await _total_step(lines=lines, results=results, name="Administradores / getChatAdministrators", action="admins", runner=lambda: _get_admins_compat(bot, chat_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Auditoria / formatar administradores", action="admin_audit_format", runner=lambda: format_admin_audit(bot, chat_id=chat_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    test_msg = None
    async def send_probe() -> Any:
        return await bot.send_message(chat_id=chat_id, text=f"Rodemotain teste total\nRun: {run_id}")
    test_msg = await _total_step(lines=lines, results=results, name="Mensagem / enviar mensagem de teste", action="send_message", runner=send_probe, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    test_message_id = getattr(test_msg, "message_id", None)

    if test_message_id:
        await _total_step(lines=lines, results=results, name="Mensagem / editar mensagem de teste", action="edit_message", runner=lambda: bot.edit_message_text(chat_id=chat_id, message_id=test_message_id, text=f"Rodemotain teste total em andamento\nRun: {run_id}"), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
        await _total_step(lines=lines, results=results, name="Fixados / fixar mensagem de teste", action="pin", runner=lambda: pin_message(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, message_id=int(test_message_id), permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
        await _total_step(lines=lines, results=results, name="Fixados / desfixar mensagem de teste", action="unpin", runner=lambda: unpin_message(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, message_id=int(test_message_id), permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    purge_message_ids: list[int] = []
    async def send_purge_pair() -> str:
        m1 = await bot.send_message(chat_id=chat_id, text=f"Rodemotain teste purge 1\nRun: {run_id}")
        m2 = await bot.send_message(chat_id=chat_id, text=f"Rodemotain teste purge 2\nRun: {run_id}")
        purge_message_ids.extend([int(getattr(m1, "message_id")), int(getattr(m2, "message_id"))])
        return f"Mensagens criadas para purge: {purge_message_ids}"
    await _total_step(lines=lines, results=results, name="Mensagens / criar mensagens para purge", action="purge_probe_messages", runner=send_purge_pair, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    if purge_message_ids:
        await _total_step(lines=lines, results=results, name="Mensagens / purge em lote", action="purge_messages", runner=lambda: purge_messages(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, message_ids=purge_message_ids, permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    delmsg_id: int | None = None
    async def send_delmsg_probe() -> str:
        nonlocal delmsg_id
        m = await bot.send_message(chat_id=chat_id, text=f"Rodemotain teste delmsg\nRun: {run_id}")
        delmsg_id = int(getattr(m, "message_id"))
        return f"Mensagem criada para delmsg: {delmsg_id}"
    await _total_step(lines=lines, results=results, name="Mensagens / criar mensagem para delmsg", action="delmsg_probe_message", runner=send_delmsg_probe, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    if delmsg_id:
        await _total_step(lines=lines, results=results, name="Mensagens / apagar via ação delmsg", action="destructive_delmsg", runner=lambda: execute_destructive_action(bot, DestructiveActionRequest(action="delmsg", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, message_id=int(delmsg_id), confirmed=True), permissions=permissions, bot_user_id=bot_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    await _total_step(lines=lines, results=results, name="Links / criar link direto adicional", action="link_direct", runner=lambda: create_invite_link_full(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, permissions=permissions, name=f"diag direto {run_id[-8:]}", duration=timedelta(minutes=30), member_limit=1, creates_join_request=False), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    direct_link = _extract_invite_link(results[-1].get("detail", "")) if results else None
    if direct_link:
        await _total_step(lines=lines, results=results, name="Links / editar link direto criado", action="link_edit_direct", runner=lambda: edit_invite_link_full(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, permissions=permissions, invite_link=str(direct_link), name=f"diag edit {run_id[-8:]}", duration=timedelta(minutes=20), member_limit=1, creates_join_request=False), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
        await _total_step(lines=lines, results=results, name="Links / revogar link direto criado", action="link_revoke_direct", runner=lambda: revoke_invite_link_full(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, permissions=permissions, invite_link=str(direct_link)), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    await _total_step(lines=lines, results=results, name="Links / criar link com solicitação", action="link_request", runner=lambda: create_invite_link_full(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, permissions=permissions, name=f"diag solic {run_id[-8:]}", duration=timedelta(minutes=30), member_limit=None, creates_join_request=True), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    request_link = _extract_invite_link(results[-1].get("detail", "")) if results else None
    if request_link:
        await _total_step(lines=lines, results=results, name="Links / revogar link com solicitação", action="link_revoke_request", runner=lambda: revoke_invite_link_full(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, permissions=permissions, invite_link=str(request_link)), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    await _total_step(lines=lines, results=results, name="Links / gerar novo link principal do bot", action="link_export_primary", runner=lambda: export_primary_invite_link(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    if original_title:
        temp_title = (original_title[:110] + " • teste")[:128]
        await _total_step(lines=lines, results=results, name="Grupo / alterar título temporário", action="set_title", runner=lambda: set_group_title(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, new_title=temp_title, permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
        await _total_step(lines=lines, results=results, name="Grupo / restaurar título original", action="restore_title", runner=lambda: set_group_title(bot, chat_id=chat_id, chat_title=temp_title, actor_user_id=actor_user_id, new_title=original_title, permissions=permissions), chat_id=chat_id, chat_title=temp_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    desc_test = f"Diagnóstico total Rodemotain {run_id}. Descrição temporária."
    await _total_step(lines=lines, results=results, name="Grupo / alterar descrição temporária", action="set_description", runner=lambda: set_group_description(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, description=desc_test, permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Grupo / restaurar descrição original", action="restore_description", runner=lambda: set_group_description(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, description=str(original_description or ""), permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    await _total_step(lines=lines, results=results, name="Grupo / fechar grupo temporariamente", action="lockdown", runner=lambda: set_group_lockdown(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, permissions=permissions, locked=True), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Grupo / restaurar permissões padrão", action="restore_permissions", runner=lambda: _restore_chat_permissions(bot, chat_id, original_permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    # Testes de banco/proteções/DDX não dependem de interação externa.
    async def ddx_roundtrip() -> str:
        fid = storage.create_ddx_filter(chat_id=chat_id, filter_text=f"rodemotain_diag_{run_id}", created_by=actor_user_id, duration=timedelta(minutes=5))
        removed = storage.remove_ddx_filter(chat_id=chat_id, filter_id=fid)
        if removed != 1:
            raise RuntimeError("filtro DDX não foi removido")
        return f"Filtro DDX criado e removido. ID: {fid}"
    await _total_step(lines=lines, results=results, name="DDX / criar e remover filtro temporário", action="ddx_roundtrip", runner=ddx_roundtrip, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    for protection_name, config in (
        ("anti_flood", {"limit": 3, "window_seconds": 10, "mute_minutes": 1}),
        ("anti_raid", {"limit": 3, "window_seconds": 60, "mode": "queue"}),
        ("captcha", {"enabled": True, "max_attempts": 2, "ttl_minutes": 5}),
    ):
        await _total_step(lines=lines, results=results, name=f"Proteções / ativar e desativar {protection_name}", action=f"protection_{protection_name}", runner=lambda n=protection_name, c=config: _total_protection_roundtrip(chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, name=n, config=c), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    target_member = await _total_step(lines=lines, results=results, name="Alvo / getChatMember", action="target_get_member", runner=lambda: bot.get_chat_member(chat_id, int(target_user_id)), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    target_is_admin = _is_member_admin(target_member)
    if is_protected_target(target_user_id, bot_user_id=bot_id, target_is_admin=target_is_admin):
        raise ValueError("diagnostico_total exige alvo comum não protegido. O alvo informado é admin/criador/owner autorizado ou o próprio bot.")

    async def add_warning_probe() -> AdvancedActionResult:
        return add_warning_action(chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, user_id=int(target_user_id), reason=f"diagnóstico total {run_id}")
    async def clear_warning_probe() -> AdvancedActionResult:
        return clear_warning_action(chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, user_id=int(target_user_id))
    async def list_warning_probe() -> str:
        return format_warning_list(chat_id=chat_id, user_id=int(target_user_id))
    await _total_step(lines=lines, results=results, name="Warnings / advertência de teste", action="warn_add", runner=add_warning_probe, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Warnings / listar advertências", action="warn_list", runner=list_warning_probe, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Warnings / limpar advertência de teste", action="warn_clear", runner=clear_warning_probe, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Tags / definir tag temporária", action="set_member_tag", runner=lambda: set_member_tag_action(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, user_id=int(target_user_id), tag="Diag", permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Tags / limpar tag temporária", action="clear_member_tag", runner=lambda: set_member_tag_action(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, user_id=int(target_user_id), tag="", permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Usuário / mute 1h via ação destrutiva", action="mute1h_target", runner=lambda: execute_destructive_action(bot, DestructiveActionRequest(action="mute1h", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=int(target_user_id), confirmed=True), permissions=permissions, bot_user_id=bot_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Usuário / desmutar alvo após mute 1h", action="unmute_after_mute1h", runner=lambda: execute_destructive_action(bot, DestructiveActionRequest(action="unmute", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=int(target_user_id), confirmed=True), permissions=permissions, bot_user_id=bot_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Usuário / mute 24h via ação destrutiva", action="mute24h_target", runner=lambda: execute_destructive_action(bot, DestructiveActionRequest(action="mute24h", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=int(target_user_id), confirmed=True), permissions=permissions, bot_user_id=bot_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Usuário / desmutar alvo após mute 24h", action="unmute_after_mute24h", runner=lambda: execute_destructive_action(bot, DestructiveActionRequest(action="unmute", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=int(target_user_id), confirmed=True), permissions=permissions, bot_user_id=bot_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Usuário / mute permanente via ação destrutiva", action="muteforever_target", runner=lambda: execute_destructive_action(bot, DestructiveActionRequest(action="muteforever", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=int(target_user_id), confirmed=True), permissions=permissions, bot_user_id=bot_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Usuário / desmutar alvo após mute permanente", action="unmute_after_muteforever", runner=lambda: execute_destructive_action(bot, DestructiveActionRequest(action="unmute", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=int(target_user_id), confirmed=True), permissions=permissions, bot_user_id=bot_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Usuário / mutar alvo por 30s via ação custom", action="mute_custom_target", runner=lambda: mute_user_custom(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, user_id=int(target_user_id), permissions=permissions, duration=timedelta(seconds=30)), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Usuário / desmutar alvo após ação custom", action="unmute_after_custom", runner=lambda: execute_destructive_action(bot, DestructiveActionRequest(action="unmute", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=int(target_user_id), confirmed=True), permissions=permissions, bot_user_id=bot_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Admin / promover alvo temporariamente", action="promote_target", runner=lambda: promote_user_admin(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, user_id=int(target_user_id), permissions=permissions, role="moderator", custom_flags=None), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Admin / título customizado temporário", action="admin_title", runner=lambda: set_admin_custom_title(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, user_id=int(target_user_id), custom_title="Teste", permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Admin / rebaixar alvo", action="demote_target", runner=lambda: demote_user_admin(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, user_id=int(target_user_id), permissions=permissions), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Usuário / banir alvo via ação custom", action="ban_custom_target", runner=lambda: ban_user_custom(bot, chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, user_id=int(target_user_id), permissions=permissions, duration=timedelta(seconds=35), revoke_messages=False), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)
    await _total_step(lines=lines, results=results, name="Usuário / desbanir alvo", action="unban_target", runner=lambda: execute_destructive_action(bot, DestructiveActionRequest(action="unban", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=int(target_user_id), confirmed=True), permissions=permissions, bot_user_id=bot_id), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    if test_message_id:
        await _total_step(lines=lines, results=results, name="Mensagem / apagar mensagem de teste", action="delete_test_message", runner=lambda: bot.delete_message(chat_id=chat_id, message_id=int(test_message_id)), chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id)

    logger.info("diagnostic_total_capture_finished", extra={"audit_data": {"run_id": run_id, "steps": len(results)}})
    process_logs = audit_capture.stop()
    finished = datetime.now(timezone.utc)
    ok_count = sum(1 for row in results if row.get("ok"))
    fail_count = sum(1 for row in results if not row.get("ok"))
    lines.append("")
    lines.append("RESUMO")
    lines.append("------")
    lines.append(f"Etapas OK: {ok_count}")
    lines.append(f"Etapas com falha: {fail_count}")
    lines.append(f"Fim: {finished.isoformat()}")
    lines.append(f"Duração: {(finished - started).total_seconds():.2f}s")
    if target_user_id:
        lines.append("Observação: se o teste de banimento foi executado, o alvo pode precisar entrar novamente no grupo pelo link.")
    lines.append("Privacidade: este relatório será apagado do servidor e da DM do bot 1h após o envio, quando o Telegram permitir.")
    _append_audit_sections(lines, results=results, process_logs=process_logs)
    storage.log_event(action="diagnostic_total_finished", result="concluido" if fail_count == 0 else "concluido_com_falhas", detection="direta", surface="diagnostico_total", chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, target_user_id=target_user_id, details=f"Diagnóstico total finalizado. OK={ok_count}; falhas={fail_count}.", metadata={"run_id": run_id, "ok": ok_count, "failed": fail_count, "process_logs": len(process_logs)})
    text = "\n".join(lines).strip() + "\n"
    reports_dir = DATA_DIR / "audit_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"rodemotain_diagnostico_total_{_safe_filename_timestamp()}_{actor_user_id}.txt"
    path.write_text(text, encoding="utf-8")
    return path, text


async def _total_protection_roundtrip(*, chat_id: int, chat_title: str, actor_user_id: int, name: str, config: dict[str, Any]) -> str:
    set_protection_action(chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, name=name, enabled=True, config=config)
    set_protection_action(chat_id=chat_id, chat_title=chat_title, actor_user_id=actor_user_id, name=name, enabled=False, config=config)
    return f"{name} ativado e desativado para teste."


@router.message(Command("diagnostico_total"))
async def tigrao_total_diagnostic(message: Message, bot: Any) -> None:
    """Executa diagnóstico total real em grupo de teste, com relatório .txt em DM."""
    user_id = _uid(message)
    if not _authorized(user_id):
        await message.answer(ENTRY_ACCESS_DENIED_TEXT)
        return
    chat_id, target_user_id, confirmed, error = _extract_total_args(str(getattr(message, "text", "") or ""), getattr(message, "chat", None))
    if not confirmed or chat_id is None:
        help_text = (
            "Diagnóstico total real\n\n"
            "Use somente em grupo de teste.\n"
            "Ele executa ações reais, exige alvo de teste e tenta restaurar ao final.\n\n"
            "Em DM:\n"
            "/diagnostico_total -1001234567890 123456789 CONFIRMO_TOTAL\n\n"
            "Dentro do grupo:\n"
            "/diagnostico_total 123456789 CONFIRMO_TOTAL\n\n"
            "Obrigatório: 123456789 deve ser um membro comum de grupo de teste.\n"
            "Sem alvo não é diagnóstico total: ele precisa testar warn, tag, mutes, ban, promover, título de admin e rebaixar."
        )
        if error:
            help_text = f"{error}\n\n" + help_text
        await message.answer(help_text)
        return
    if target_user_id is None:
        await message.answer(
            "Diagnóstico total real exige target_user_id. Sem alvo ele fica parcial.\n\n"
            "Use um membro comum de grupo de teste:\n"
            "/diagnostico_total -1001234567890 123456789 CONFIRMO_TOTAL\n"
            "ou, dentro do grupo:\n"
            "/diagnostico_total 123456789 CONFIRMO_TOTAL"
        )
        return
    ack_text = "Diagnóstico total iniciado. Vou enviar o .txt na sua DM."
    if _chat_type(getattr(message, "chat", None)) in {"group", "supergroup"}:
        await _answer_group_temporarily(message, bot, ack_text)
    else:
        await message.answer(ack_text)
    try:
        path, report_text = await _run_total_diagnostic(
            bot,
            actor_user_id=int(user_id),
            request_chat=getattr(message, "chat", None),
            chat_id=int(chat_id),
            target_user_id=target_user_id,
        )
        caption = "Diagnóstico total concluído. Arquivo .txt anexado. Será apagado da DM e do servidor em 1h."
        sent_report = None
        if BufferedInputFile is not None:
            sent_report = await bot.send_document(chat_id=int(user_id), document=BufferedInputFile(path.read_bytes(), filename=path.name), caption=caption)
        else:  # pragma: no cover
            sent_report = await bot.send_message(chat_id=int(user_id), text=report_text[:3900])
        _schedule_delete_file(path, delay_seconds=AUDIT_REPORT_TTL_SECONDS)
        _schedule_delete_message(bot, chat_id=int(user_id), message_id=getattr(sent_report, "message_id", None), delay_seconds=AUDIT_REPORT_TTL_SECONDS)
        storage.log_event(action="diagnostic_total_report_sent", result="enviado", detection="direta", surface="dm", actor_user_id=int(user_id), chat_id=int(chat_id), target_user_id=target_user_id, details=f"Relatório total enviado e agendado para exclusão em 1h: {path.name}", metadata={"path": str(path), "ttl_seconds": AUDIT_REPORT_TTL_SECONDS})
    except Exception as exc:
        storage.log_event(action="diagnostic_total_failed", result="falhou", detection="direta", surface="dm", actor_user_id=int(user_id), chat_id=int(chat_id), target_user_id=target_user_id, details=str(exc))
        await message.answer(f"Não consegui concluir o diagnóstico total: {_clean_telegram_error(str(exc))}")


@router.message(Command("start"))
async def tigrao_start(message: Message, bot: Any | None = None) -> None:
    """Tutorial rápido e resposta de vida do bot.

Em grupos, a resposta é temporária e é apagada automaticamente em 5 minutos
para não poluir a conversa. Usuários não autorizados recebem somente a
orientação curta de entrada/captcha.
    """
    user_id = _uid(message)
    text = START_TEXT_AUTHORIZED if _authorized(user_id) else START_TEXT_UNAUTHORIZED
    if _chat_type(getattr(message, "chat", None)) in {"group", "supergroup"}:
        await _answer_group_temporarily(message, bot, text)
        return
    await message.answer(text)


@router.message(Command("help"))
async def tigrao_help(message: Message, bot: Any | None = None) -> None:
    """Lista comandos públicos e recursos do painel."""
    user_id = _uid(message)
    text = HELP_TEXT_AUTHORIZED if _authorized(user_id) else HELP_TEXT_UNAUTHORIZED
    if _chat_type(getattr(message, "chat", None)) in {"group", "supergroup"}:
        await _answer_group_temporarily(message, bot, text)
        return
    await message.answer(text)


@router.message(Command("diagnostico"))
async def tigrao_diagnostic(message: Message, bot: Any) -> None:
    """Executa diagnóstico real e envia relatório .txt em DM ao operador autorizado."""
    user_id = _uid(message)
    if not _authorized(user_id):
        await message.answer(ENTRY_ACCESS_DENIED_TEXT)
        return
    text = str(getattr(message, "text", "") or "").strip()
    explicit_chat_id: int | None = None
    parts = text.split(maxsplit=1)
    if len(parts) == 2:
        candidate = parts[1].strip()
        try:
            explicit_chat_id = int(candidate)
        except Exception:
            await message.answer("Use: /diagnostico ou /diagnostico -1001234567890")
            return
    ack_text = "Diagnóstico iniciado. Vou enviar o arquivo .txt na sua DM."
    if _chat_type(getattr(message, "chat", None)) in {"group", "supergroup"}:
        await _answer_group_temporarily(message, bot, ack_text)
    else:
        await message.answer(ack_text)
    try:
        path, report_text = await _run_real_diagnostic(bot, actor_user_id=int(user_id), request_chat=getattr(message, "chat", None), explicit_chat_id=explicit_chat_id)
        caption = "Diagnóstico concluído. Arquivo .txt anexado. Será apagado da DM e do servidor em 1h."
        sent_report = None
        if BufferedInputFile is not None:
            sent_report = await bot.send_document(
                chat_id=int(user_id),
                document=BufferedInputFile(path.read_bytes(), filename=path.name),
                caption=caption,
            )
        else:  # pragma: no cover
            sent_report = await bot.send_message(chat_id=int(user_id), text=report_text[:3900])
        _schedule_delete_file(path, delay_seconds=AUDIT_REPORT_TTL_SECONDS)
        _schedule_delete_message(bot, chat_id=int(user_id), message_id=getattr(sent_report, "message_id", None), delay_seconds=AUDIT_REPORT_TTL_SECONDS)
        storage.log_event(action="diagnostic_report_sent", result="enviado", detection="direta", surface="dm", actor_user_id=int(user_id), details=f"Relatório enviado e agendado para exclusão em 1h: {path.name}", metadata={"path": str(path), "ttl_seconds": AUDIT_REPORT_TTL_SECONDS})
    except Exception as exc:
        storage.log_event(action="diagnostic_failed", result="falhou", detection="direta", surface="dm", actor_user_id=int(user_id), details=str(exc))
        await message.answer(f"Não consegui concluir o diagnóstico: {_clean_telegram_error(str(exc))}")


@router.message(Command("tigrao"))
async def tigrao_panel(message: Message, bot: Any) -> None:
    user_id = _uid(message)
    if not _authorized(user_id):
        return
    session = create_session(owner_user_id=user_id, moderator_user_id=user_id)
    chat = getattr(message, "chat", None)
    _remember_group_chat(chat)
    if _chat_type(chat) == "private":
        await message.answer(HOME_TEXT, reply_markup=_home_markup(session.session_id))
        return
    try:
        await bot.send_message(user_id, HOME_TEXT, reply_markup=_home_markup(session.session_id))
    except Exception:
        logger.debug("TIGRAO_PANEL_DM_FAILED", exc_info=True)


@router.message(Command("captcha"))
async def tigrao_captcha_reply(message: Message, bot: Any) -> None:
    """Confere captcha de solicitação de entrada por código enviado em DM."""
    user_id = _uid(message)
    if user_id is None:
        return
    text = str(getattr(message, "text", "") or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Use: /captcha código")
        return
    challenge = storage.verify_captcha_challenge(user_id=user_id, code=parts[1].strip())
    if challenge is None:
        await message.answer("Captcha não encontrado, expirado ou já processado.")
        return
    chat_id = int(challenge["chat_id"])
    if challenge.get("status") != "aprovado":
        if challenge.get("status") == "falhou":
            try:
                perms = await get_bot_permissions(bot, chat_id)
                if perms.is_admin and perms.can_invite_users:
                    await bot.decline_chat_join_request(chat_id=chat_id, user_id=user_id)
                storage.log_event(action="captcha_decline", result="recusado", detection="automatica", surface="dm", chat_id=chat_id, chat_title=challenge.get("chat_title"), actor_user_id=user_id, target_user_id=user_id, details="Captcha excedeu tentativas; solicitação recusada quando possível.")
            except Exception as exc:
                storage.log_event(action="captcha_decline", result="falhou", detection="automatica", surface="dm", chat_id=chat_id, chat_title=challenge.get("chat_title"), actor_user_id=user_id, target_user_id=user_id, details=str(exc))
        await message.answer("Código incorreto ou tentativas excedidas.")
        return
    try:
        perms = await get_bot_permissions(bot, chat_id)
        if not perms.is_admin or not perms.can_invite_users:
            raise PermissionError("bot sem can_invite_users")
        await bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
        storage.log_event(action="captcha_approve", result="aprovado", detection="automatica", surface="dm", chat_id=chat_id, chat_title=challenge.get("chat_title"), actor_user_id=user_id, target_user_id=user_id, details="Captcha correto; solicitação aprovada.")
        await message.answer("Captcha correto. Entrada aprovada.")
    except Exception as exc:
        storage.log_event(action="captcha_approve", result="falhou", detection="automatica", surface="dm", chat_id=chat_id, chat_title=challenge.get("chat_title"), actor_user_id=user_id, target_user_id=user_id, details=str(exc))
        await message.answer(f"Captcha correto, mas falhou ao aprovar a entrada: {exc}")


@router.message(TigraoWaitingTextFilter(), F.photo)
async def tigrao_waiting_photo(message: Message, bot: Any) -> None:
    user_id = _uid(message)
    if not _authorized(user_id):
        return
    session = get_user_session(user_id)
    if session is None or session.waiting_for != "setphoto_upload":
        return
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    photos = list(getattr(message, "photo", None) or [])
    if not photos:
        await message.answer("Nenhuma foto recebida.")
        return
    largest = photos[-1]
    file_id = str(getattr(largest, "file_id", "") or "").strip()
    if not file_id:
        await message.answer("Não consegui obter o file_id da foto recebida.")
        return
    width = getattr(largest, "width", None)
    height = getattr(largest, "height", None)
    size = getattr(largest, "file_size", None)
    session.payload["pending_advanced_action"] = {
        "action": "setphoto",
        "file_id": file_id,
        "width": width,
        "height": height,
        "file_size": size,
    }
    session.waiting_for = None
    session.selected_action = None
    session.payload["nav_back"] = _action_back_target(session)
    details = [f"Arquivo Telegram: {file_id[:16]}...", f"Dimensão: {width or '?'}x{height or '?'}"]
    if size is not None:
        details.append(f"Tamanho: {size} bytes")
    await _send_flow_confirmation(message, bot, session, _advanced_confirmation_text(session, "setphoto", details))


@router.message(TigraoWaitingTextFilter(), F.text)
async def tigrao_waiting_message(message: Message, bot: Any) -> None:
    """Processa respostas de DM quando a sessão do painel está aguardando texto."""
    user_id = _uid(message)
    if not _authorized(user_id):
        return
    chat = getattr(message, "chat", None)
    if _chat_type(chat) != "private":
        return
    session = get_user_session(user_id)
    if session is None or not session.waiting_for:
        return
    text = str(getattr(message, "text", "") or "").strip()
    if session.waiting_for == "join_auto_ids":
        await _handle_join_auto_ids(message, bot, session, text)
    elif session.waiting_for == "join_pending_id":
        await _handle_join_pending_id(message, bot, session, text)
    elif session.waiting_for == "join_decline_id":
        await _handle_join_decline_id(message, bot, session, text)
    elif session.waiting_for == "destructive_user_id":
        await _handle_destructive_user_id(message, bot, session, text)
    elif session.waiting_for == "destructive_message_id":
        await _handle_destructive_message_id(message, bot, session, text)
    elif session.waiting_for == "advanced_text":
        await _handle_advanced_text(message, bot, session, text)
    elif session.waiting_for == "ddx_filter_text":
        await _handle_ddx_filter_text(message, bot, session, text)
    elif session.waiting_for == "ddx_remove_id":
        await _handle_ddx_remove_id(message, bot, session, text)


@router.chat_join_request()
async def tigrao_join_request_polling(join_request: Any, bot: Any) -> None:
    """Processa solicitações de entrada também no modo polling.

    No webhook, o mesmo runtime roda no before_dispatch e consome o update.
    No polling, este handler mantém o bot moderador funcional sem depender do
    endpoint HTTP.
    """
    _remember_group_chat(getattr(join_request, "chat", None))
    await join_request_handle(bot, SimpleNamespace(chat_join_request=join_request))


@router.message(TigraoGroupSurfaceFilter())
async def tigrao_group_runtime_probe(message: Message, bot: Any) -> None:
    """Registra grupos e executa DDX hard no polling sem resposta pública."""
    _remember_group_chat(getattr(message, "chat", None))
    storage.remember_recent_message(message)
    if await anti_flood_handle(bot, SimpleNamespace(message=message)):
        return
    await ddx_handle(bot, SimpleNamespace(message=message))


@router.callback_query(F.data.startswith("tgf:"))
async def tigrao_callback(callback: CallbackQuery, bot: Any) -> None:
    user_id = _uid(callback)
    if not _authorized(user_id):
        await callback.answer()
        return
    parsed = parse_callback(callback.data or "")
    if parsed is None:
        await callback.answer()
        return
    session_id, parts = parsed
    action = parts[0]
    session = get_session(session_id)
    if session is None:
        await _safe_edit(callback, SESSION_EXPIRED_TEXT, None)
        await callback.answer()
        return
    owner = session.moderator_user_id or session.owner_user_id
    if owner is not None and owner != user_id:
        await callback.answer()
        return

    if action == "close":
        close_session(session_id)
        try:
            if callback.message is not None:
                await callback.message.delete()
            await callback.answer()
            return
        except Exception:
            if callback.message is not None:
                await callback.message.edit_text("Painel fechado.")
            await callback.answer()
            return

    if action == "home":
        session.waiting_for = None
        session.payload.pop("nav_back", None)
        session.payload.pop("pending_destructive_action", None)
        session.payload.pop("pending_advanced_action", None)
        _forget_flow_prompt(session)
        await _safe_edit(callback, HOME_TEXT, _home_markup(session_id))
    elif action == "panel":
        session.waiting_for = None
        session.selected_action = None
        session.payload.pop("nav_back", None)
        session.payload.pop("pending_destructive_action", None)
        session.payload.pop("pending_advanced_action", None)
        _forget_flow_prompt(session)
        if session.selected_chat_id is not None:
            await _show_selected_group_panel(callback, bot, session)
        else:
            await _safe_edit(callback, HOME_TEXT, _home_markup(session_id))
    elif action == "back":
        await _go_back(callback, bot, session)
    elif action == "grp":
        session.waiting_for = None
        await _show_groups(callback, session_id)
    elif action.startswith("g") and action[1:].isdecimal():
        session.waiting_for = None
        await _show_group_detail(callback, bot, session_id, int(action[1:]))
    elif action == "logs":
        await _safe_edit(callback, "📊 Logs do Rodemotain", to_inline_keyboard_markup(logs_keyboard(session_id)))
    elif action in {"log_mod", "log_use", "log_join", "log_err"}:
        await _show_logs(callback, session, action)
    elif action == "join":
        await _show_join_menu(callback, session_id)
    elif action == "join_link":
        await _create_join_link(callback, bot, session, creates_join_request=True)
    elif action == "join_link_direct":
        await _create_join_link(callback, bot, session, creates_join_request=False)
    elif action == "join_noauto":
        await _show_join_menu(callback, session_id, "Link criado sem autoaceite adicional.")
    elif action == "join_pending_menu":
        session.payload["nav_back"] = "join"
        await _safe_edit(callback, "📥 Entrada — pedidos pendentes\n\nConsulte pedidos salvos por até 2h, aceite por ID ou recuse por ID.", to_inline_keyboard_markup(join_pending_keyboard(session.session_id)))
    elif action == "join_links_menu":
        session.payload["nav_back"] = "join"
        await _safe_edit(callback, "📥 Entrada — criação de links\n\nCrie link com solicitação de entrada ou link direto. O link gerado será enviado em mensagem individual separada.", to_inline_keyboard_markup(join_links_keyboard(session.session_id)))
    elif action == "join_auto_menu":
        session.payload["nav_back"] = "join"
        await _safe_edit(callback, "📥 Entrada — autorização automática\n\nInforme IDs que poderão ser aprovados automaticamente quando pedirem entrada.", to_inline_keyboard_markup(join_auto_keyboard(session.session_id)))
    elif action == "join_auto":
        await _join_auto_or_list(callback, session)
    elif action == "join_pending":
        await _join_pending(callback, session)
    elif action == "join_accept":
        session.waiting_for = "join_pending_id"
        session.payload["nav_back"] = "join"
        await _safe_edit_flow_prompt(callback, session, "Envie o ID Telegram que será aceito.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
    elif action == "join_decline":
        session.waiting_for = "join_decline_id"
        session.payload["nav_back"] = "join"
        await _safe_edit_flow_prompt(callback, session, "Envie o ID Telegram que será recusado.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
    elif action == "act":
        await _show_actions(callback, session)
    elif is_action_category_key(action):
        await _show_action_category(callback, session, action)
    elif action in {"ban", "unban", "mute1h", "mute24h", "muteforever", "unmute"}:
        await _prompt_destructive_user(callback, session, action)
    elif action == "delmsg":
        await _prompt_delete_message(callback, session)
    elif action in {"bantime", "mutetime", "purge", "pin", "unpin", "settitle", "setdesc", "react1", "reactall", "promote", "demote", "admintitle", "bansender", "unbansender", "linkcreate", "linkedit", "linkrevoke", "setphoto", "settag", "warnadd", "warnlist", "warnclear", "antiflood", "antiraid", "captcha"}:
        await _prompt_advanced_text(callback, session, action)
    elif action in {"admins", "protstatus"}:
        await _execute_advanced_no_text(callback, bot, session, action)
    elif action in {"lock", "unlock", "unpinall", "linkexport", "delphoto"}:
        await _prepare_advanced_confirmation(callback, bot, session, action)
    elif action == "confirm":
        await _confirm_pending_action(callback, bot, session)
    elif action == "cancel":
        session.selected_action = None
        session.waiting_for = None
        session.payload.pop("pending_destructive_action", None)
        session.payload.pop("pending_advanced_action", None)
        await _safe_edit(callback, "Ação cancelada.\n\nDeseja voltar ao painel principal ou fechar?", to_inline_keyboard_markup(post_action_keyboard(session.session_id)))
    elif action == "ddx":
        await _show_ddx(callback, session)
    elif action == "ddxon":
        await _set_ddx_enabled(callback, session, True)
    elif action == "ddxoff":
        await _set_ddx_enabled(callback, session, False)
    elif action == "ddxadd":
        await _prompt_ddx_filter(callback, session)
    elif action == "ddxlist":
        await _list_ddx(callback, session)
    elif action == "ddxremove":
        await _prompt_ddx_remove(callback, session)
    elif action == "react":
        await _safe_edit(
            callback,
            "⚛️ Reações\n\nAções rápidas para remover reação específica ou limpar reações recentes.",
            to_inline_keyboard_markup([
                [button("Remover reação de mensagem", make_callback(session.session_id, "react1"), style="danger")],
                [button("Remover reações recentes", make_callback(session.session_id, "reactall"), style="danger")],
                *back_close_keyboard(session.session_id),
            ]),
        )
    else:
        await callback.answer()
        return
    await callback.answer()



async def _go_back(callback: CallbackQuery, bot: Any, session: Any) -> None:
    """Volta pela navegação padrão do painel, sem executar ação pendente."""
    session.waiting_for = None
    session.selected_action = None
    session.payload.pop("pending_destructive_action", None)
    session.payload.pop("pending_advanced_action", None)
    _forget_flow_prompt(session)
    nav = session.payload.pop("nav_back", None)
    if nav == "act":
        await _show_actions(callback, session)
        return
    if nav == "join":
        await _show_join_menu(callback, session.session_id)
        return
    if nav == "ddx":
        await _show_ddx(callback, session)
        return
    if nav == "logs":
        await _safe_edit(callback, "📊 Logs do Rodemotain", to_inline_keyboard_markup(logs_keyboard(session.session_id)))
        return
    if isinstance(nav, str) and nav.startswith("cat_"):
        await _show_action_category(callback, session, nav)
        return
    if nav == "groups":
        await _show_groups(callback, session.session_id)
        return
    if session.selected_chat_id is not None:
        await _show_selected_group_panel(callback, bot, session)
        return
    await _safe_edit(callback, HOME_TEXT, _home_markup(session.session_id))

async def _show_groups(callback: CallbackQuery, session_id: str) -> None:
    session = get_session(session_id)
    if session is None:
        await _safe_edit(callback, SESSION_EXPIRED_TEXT, None)
        return
    try:
        groups = list_groups(limit=50)
    except Exception:
        logger.debug("TIGRAO_GROUP_LIST_FAILED", exc_info=True)
        groups = []
    session.payload["groups"] = [
        {
            "chat_id": int(g["chat_id"]),
            "title": g.get("title") or g.get("username") or str(g["chat_id"]),
            "username": g.get("username"),
        }
        for g in groups[:50]
        if g.get("chat_id") is not None
    ]
    if not session.payload["groups"]:
        await _safe_edit(callback, "Nenhum grupo disponível para seleção agora.", to_inline_keyboard_markup(back_close_keyboard(session_id)))
        return
    await _safe_edit(callback, "Selecione um grupo:", to_inline_keyboard_markup(group_selection_keyboard(session_id, session.payload["groups"])))


async def _show_group_detail(callback: CallbackQuery, bot: Any, session_id: str, index: int) -> None:
    session = get_session(session_id)
    groups = (session.payload.get("groups") if session else None) or []
    if index < 0 or index >= len(groups):
        await callback.answer()
        return
    group = groups[index]
    session.selected_chat_id = int(group["chat_id"])
    session.selected_group_title = str(group.get("title") or session.selected_chat_id)
    session.payload["nav_back"] = "groups"
    await _show_selected_group_panel(callback, bot, session)


async def _show_selected_group_panel(callback: CallbackQuery, bot: Any, session: Any) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        perms = permissions_from_chat_member(member)
    except Exception:
        logger.debug("TIGRAO_GROUP_PERMISSIONS_FAILED", exc_info=True)
        perms = None
    if perms is None or not perms.is_admin:
        text = (f"Grupo selecionado: {title}\nID do grupo: {chat_id}\nStatus do bot: não administrador\n"
                "Painel indisponível para este grupo.\nPromova o bot a administrador para usar o Rodemotain aqui.")
        await _safe_edit(callback, text, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    yesno = lambda v: "sim" if v else "não"
    text = (
        f"Grupo selecionado: {title}\nID do grupo: {chat_id}\nStatus do bot: administrador\n\n"
        f"Gerenciar chat: {yesno(perms.can_manage_chat)}\n"
        f"Apagar mensagens/DDX/reações: {yesno(perms.can_delete_messages)}\n"
        f"Restringir membros: {yesno(perms.can_restrict_members)}\n"
        f"Convidar/aprovar/recusar entradas: {yesno(perms.can_invite_users)}\n"
        f"Fixar mensagens: {yesno(perms.can_pin_messages)}\n"
        f"Alterar informações: {yesno(perms.can_change_info)}\n"
        f"Promover admins: {yesno(perms.can_promote_members)}\n"
        f"Tags: {yesno(perms.can_manage_tags)}\n"
        f"Vídeo chats: {yesno(perms.can_manage_video_chats)}\n"
        f"Canais — postar/editar: {yesno(perms.can_post_messages or perms.can_edit_messages)}\n"
        f"DMs de canal: {yesno(perms.can_manage_direct_messages)}"
    )
    await _safe_edit(callback, text, to_inline_keyboard_markup(group_admin_keyboard(
        session.session_id,
        destructive_actions_enabled=True,
        ddx_enabled=True,
        reactions_enabled=False,
    )))


def _selected_group_or_text(session: Any) -> tuple[int | None, str | None, str | None]:
    if session.selected_chat_id is None:
        return None, None, "Selecione um grupo antes de usar esta função."
    return int(session.selected_chat_id), session.selected_group_title or str(session.selected_chat_id), None


def _action_back_target(session: Any) -> str:
    """Retorna a categoria atual para o botão Voltar, sem perder compatibilidade."""
    category = str(session.payload.get("active_action_category") or "")
    return category if category.startswith("cat_") else "act"


async def _show_join_menu(callback: CallbackQuery, session_id: str, prefix: str | None = None) -> None:
    session = get_session(session_id)
    if session is not None:
        session.payload["nav_back"] = None
    text = "📥 Solicitações de entrada"
    if prefix:
        text = f"{prefix}\n\n{text}"
    await _safe_edit(callback, text, to_inline_keyboard_markup(join_requests_keyboard(session_id)))


async def _create_join_link(callback: CallbackQuery, bot: Any, session: Any, *, creates_join_request: bool) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    mode_label = "Link com solicitação" if creates_join_request else "Link direto de entrada"
    try:
        perms = await get_bot_permissions(bot, chat_id)
        if not perms.is_admin or not perms.can_invite_users:
            raise PermissionError("bot sem can_invite_users")
        if creates_join_request:
            invite = await create_join_request_link(bot, chat_id, name="Rodemotain")
        else:
            invite = await bot.create_chat_invite_link(chat_id=chat_id, name="Rodemotain direto", creates_join_request=False)
    except Exception as exc:
        storage.log_event(
            action="join_link_create",
            result="falhou",
            detection="direta",
            surface="callback",
            chat_id=chat_id,
            chat_title=title,
            actor_user_id=session.moderator_user_id or session.owner_user_id,
            details=str(exc),
            metadata={"creates_join_request": creates_join_request},
        )
        await _safe_edit(callback, f"Falha ao criar {mode_label.lower()}: {exc}", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    link = getattr(invite, "invite_link", None) or getattr(invite, "link", None) or str(invite)
    if creates_join_request:
        session.payload["last_invite_link"] = link
    else:
        session.payload.pop("last_invite_link", None)
    storage.log_event(
        action="join_link_create",
        result="criado",
        detection="direta",
        surface="callback",
        chat_id=chat_id,
        chat_title=title,
        actor_user_id=session.moderator_user_id or session.owner_user_id,
        details=f"{mode_label} criado.",
        metadata={"invite_link": link, "creates_join_request": creates_join_request},
    )
    await _send_persistent_invite_link(callback, chat_title=title, link=link, label=mode_label)
    if creates_join_request:
        text = "✅ Link com solicitação criado.\nEnviado em mensagem separada.\n\nAtivar autoaceite para IDs?"
        await _safe_edit(callback, text, to_inline_keyboard_markup(join_auto_question_keyboard(session.session_id)))
    else:
        session.payload["nav_back"] = "join"
        text = "✅ Link direto criado.\nEnviado em mensagem separada.\n\nNão exige aprovação."
        await _safe_edit(callback, text, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _join_auto_or_list(callback: CallbackQuery, session: Any) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    if session.payload.get("last_invite_link"):
        session.waiting_for = "join_auto_ids"
        session.payload["nav_back"] = "join"
        await _safe_edit_flow_prompt(callback, session, "Envie os IDs autorizados.\nUse uma linha por ID.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    rows = storage.list_auto_accepts(chat_id=chat_id, limit=10)
    if not rows:
        text = "Nenhuma autorização automática ativa encontrada."
    else:
        text = "Autorizações automáticas\n\n" + "\n".join(
            f"ID: {row.allowed_user_id} — status: {row.status} — expira: {row.expires_at.isoformat()}" for row in rows
        )
    await _safe_edit(callback, text, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _join_pending(callback: CallbackQuery, session: Any) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    pending = storage.list_pending_join_requests(chat_id=chat_id, limit=10)
    lines = ["Pendentes 2h"]
    if not pending:
        lines.append("Nenhuma solicitação pendente encontrada.")
    else:
        for req in pending:
            username = f"@{req.username}" if req.username else "não informado"
            lines.append(f"Usuário: {req.full_name}\nUsername: {username}\nID: {req.user_id}")
    lines.append("\nUse os botões Aceitar ID pendente ou Recusar ID pendente para agir sobre um pedido.")
    session.waiting_for = None
    session.payload["nav_back"] = "join"
    await _safe_edit(callback, "\n\n".join(lines), to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _handle_join_auto_ids(message: Message, bot: Any, session: Any, text: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    parsed = parse_user_ids(text)
    link = str(session.payload.get("last_invite_link") or "")
    if not link:
        await message.answer("Nenhum link com solicitação foi criado nesta sessão.")
        session.waiting_for = None
        return
    records = storage.create_auto_accept_records(
        chat_id=chat_id,
        chat_title=title,
        invite_link=link,
        user_ids=parsed.valid,
        created_by_owner_id=session.moderator_user_id or session.owner_user_id or 0,
    )
    approved_now = 0
    for user_id in parsed.valid:
        req = storage.find_pending_join_request(chat_id=chat_id, user_id=user_id)
        if req is None:
            continue
        try:
            perms = await get_bot_permissions(bot, chat_id)
            if not perms.is_admin or not perms.can_invite_users:
                continue
            detail = await approve_pending_join_request(bot, req, processed_by=session.moderator_user_id or session.owner_user_id, autoaccept=True, origin="ID autorizado no painel")
            storage.update_join_request_status(req)
            auto = storage.get_active_auto_accept(chat_id=chat_id, user_id=user_id)
            if auto is not None:
                auto.status = storage.APPROVED if req.status == "aprovado" else storage.FAILED
                auto.approved_at = req.processed_at
                auto.result_detail = detail
                storage.update_auto_accept_status(auto)
            if req.status == "aprovado":
                approved_now += 1
            storage.log_event(action="join_auto_accept", result=req.status, detection="indireta", surface="banco_pendente", chat_id=chat_id, chat_title=title, actor_user_id=session.moderator_user_id or session.owner_user_id, target_user_id=user_id, details=detail)
        except Exception as exc:
            storage.log_event(action="join_auto_accept", result="falhou", detection="indireta", surface="banco_pendente", chat_id=chat_id, chat_title=title, actor_user_id=session.moderator_user_id or session.owner_user_id, target_user_id=user_id, details=str(exc))
    waiting_future = max(0, len(parsed.valid) - approved_now)
    storage.log_event(action="join_auto_ids_saved", result="salvo", detection="direta", surface="dm", chat_id=chat_id, chat_title=title, actor_user_id=session.moderator_user_id or session.owner_user_id, details=f"IDs autorizados: {len(records)}; inválidos: {len(parsed.invalid)}")
    session.waiting_for = None
    session.payload.pop("last_invite_link", None)
    invalid_text = "\n".join(parsed.invalid) if parsed.invalid else "nenhum"
    await _send_flow_result(
        message,
        bot,
        session,
        f"Autoaceite ativado por 2h.\n"
        f"IDs autorizados: {len(parsed.valid)}\n"
        f"Pendentes aprovados agora: {approved_now}\n"
        f"Aguardando solicitação futura: {waiting_future}\n"
        f"Inválidos ignorados: {len(parsed.invalid)}\n{invalid_text}"
    )


async def _handle_join_pending_id(message: Message, bot: Any, session: Any, text: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    parsed = parse_user_ids(text)
    if len(parsed.valid) != 1:
        await message.answer("Envie exatamente um ID numérico válido.")
        return
    user_id = parsed.valid[0]
    req = storage.find_pending_join_request(chat_id=chat_id, user_id=user_id)
    if req is None:
        session.waiting_for = None
        await _send_flow_result(message, bot, session, "Nenhuma solicitação pendente desse ID foi encontrada nas últimas 2h.")
        return
    try:
        perms = await get_bot_permissions(bot, chat_id)
        if not perms.is_admin or not perms.can_invite_users:
            raise PermissionError("bot sem can_invite_users")
        detail = await approve_pending_join_request(bot, req, processed_by=session.moderator_user_id or session.owner_user_id, autoaccept=False, origin="aprovação manual por ID pendente")
        storage.update_join_request_status(req)
        storage.log_event(action="join_pending_approve", result=req.status, detection="indireta", surface="banco_pendente", chat_id=chat_id, chat_title=title, actor_user_id=session.moderator_user_id or session.owner_user_id, target_user_id=user_id, details=detail)
        await _send_flow_result(message, bot, session, detail)
    except Exception as exc:
        storage.log_event(action="join_pending_approve", result="falhou", detection="indireta", surface="banco_pendente", chat_id=chat_id, chat_title=title, actor_user_id=session.moderator_user_id or session.owner_user_id, target_user_id=user_id, details=str(exc))
        await _send_flow_result(message, bot, session, f"Falha ao aprovar ID pendente: {exc}")
    finally:
        session.waiting_for = None




async def _handle_join_decline_id(message: Message, bot: Any, session: Any, text: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    user_id = _positive_int(text)
    if user_id is None:
        await message.answer("Envie um ID numérico válido.")
        return
    try:
        perms = await get_bot_permissions(bot, chat_id)
        if not perms.is_admin or not perms.can_invite_users:
            raise PermissionError("bot sem can_invite_users")
        pending = storage.find_pending_join_request(chat_id=chat_id, user_id=user_id)
        if pending is None:
            await _send_flow_result(message, bot, session, "Não encontrei solicitação pendente para esse ID nos últimos registros ativos.")
            return
        detail = await decline_pending_join_request(bot, pending, processed_by=session.moderator_user_id or session.owner_user_id, origin="manual")
    except Exception as exc:
        storage.log_event(
            action="join_decline",
            result="falhou",
            detection="direta",
            surface="dm",
            chat_id=chat_id,
            chat_title=title,
            actor_user_id=session.moderator_user_id or session.owner_user_id,
            target_user_id=user_id,
            details=str(exc),
        )
        await _send_flow_result(message, bot, session, f"Falha ao recusar solicitação: {exc}")
        return
    session.waiting_for = None
    await _send_flow_result(message, bot, session, f"Solicitação recusada.\n{detail}")


async def _show_actions(callback: CallbackQuery, session: Any) -> None:
    session.payload["nav_back"] = None
    session.payload.pop("active_action_category", None)
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    text = (
        f"🎛️ Ações do grupo\n\n"
        f"Grupo: {title}\nID do grupo: {chat_id}\n\n"
        "Escolha uma categoria. As ações sensíveis continuam exigindo confirmação explícita."
    )
    await _safe_edit(callback, text, to_inline_keyboard_markup(destructive_actions_keyboard(session.session_id)))


async def _show_action_category(callback: CallbackQuery, session: Any, category: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.payload["active_action_category"] = category
    parent = action_category_parent(category)
    session.payload["nav_back"] = parent or "act"
    title_text = action_category_title(category)
    help_text = (
        "Escolha uma subcategoria. A cor do botão indica o risco: verde para ações de liberação/restauração, vermelho para ações restritivas ou destrutivas."
        if parent is None
        else "Escolha a função. Quando a ação alterar o grupo ou afetar um usuário, o painel pedirá confirmação."
    )
    text = (
        f"{title_text}\n\n"
        f"Grupo: {title}\nID do grupo: {chat_id}\n\n"
        f"{help_text}"
    )
    await _safe_edit(callback, text, to_inline_keyboard_markup(action_category_keyboard(session.session_id, category)))


_ACTION_LABELS = {
    "ban": "Banir usuário",
    "unban": "Desbanir usuário",
    "mute1h": "Mutar usuário por 1 hora",
    "mute24h": "Mutar usuário por 24 horas",
    "muteforever": "Mutar usuário indefinidamente",
    "unmute": "Desmutar usuário",
    "delmsg": "Apagar mensagem",
    "bantime": "Banir com tempo livre",
    "mutetime": "Mutar com tempo livre",
    "purge": "Purge 1–100 mensagens",
    "lock": "Fechar grupo / lockdown",
    "unlock": "Reabrir grupo / unlock",
    "pin": "Fixar mensagem",
    "unpin": "Desfixar mensagem",
    "unpinall": "Limpar todos os fixados",
    "settitle": "Alterar título",
    "setdesc": "Alterar descrição",
    "admins": "Auditar admins/bots",
    "react1": "Remover reação de mensagem",
    "reactall": "Remover reações recentes",
    "promote": "Promover administrador",
    "demote": "Rebaixar administrador",
    "admintitle": "Título customizado de admin",
    "bansender": "Banir sender chat/canal",
    "unbansender": "Desbanir sender chat/canal",
    "linkexport": "Gerar novo link principal do bot",
    "linkcreate": "Criar link adicional",
    "linkedit": "Editar link",
    "linkrevoke": "Revogar link",
    "setphoto": "Alterar foto do grupo",
    "delphoto": "Remover foto do grupo",
    "settag": "Tag real de membro",
    "warnadd": "Advertir usuário",
    "warnlist": "Listar advertências",
    "warnclear": "Limpar advertências",
    "protstatus": "Status proteções",
    "antiflood": "Configurar anti-flood",
    "antiraid": "Configurar anti-raid",
    "captcha": "Configurar captcha",
}


def _format_recent_message_quotes(chat_id: int | None) -> str:
    if chat_id is None:
        return ""
    rows = storage.list_recent_messages(chat_id=chat_id, limit=5)
    if not rows:
        return ""
    lines = ["Últimas 5 mensagens registradas para consulta:"]
    for row in rows:
        sender = row.get("sender_full_name") or row.get("sender_username") or row.get("sender_user_id") or "autor desconhecido"
        username = f" @{row.get('sender_username')}" if row.get("sender_username") else ""
        sender_id = f"ID {row.get('sender_user_id')}" if row.get("sender_user_id") is not None else "ID não informado"
        text = str(row.get("message_text") or "sem texto/caption").replace("\n", " ").strip()
        if len(text) > 110:
            text = text[:107] + "..."
        lines.append(f"> msg {row.get('message_id')} — {sender}{username} — {sender_id}")
        lines.append(f"> {text}")
    return "\n".join(lines)


def _advanced_prompt_text(action: str, chat_id: int | None) -> str:
    base = _ADVANCED_PROMPTS[action]
    if action in {"react1", "reactall", "purge", "pin", "unpin"}:
        recent = _format_recent_message_quotes(chat_id)
        if recent:
            return f"{base}\n\n{recent}"
    return base


async def _prompt_destructive_user(callback: CallbackQuery, session: Any, action: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.selected_action = action
    session.waiting_for = "destructive_user_id"
    session.payload["nav_back"] = _action_back_target(session)
    await _safe_edit_flow_prompt(callback, session, f"{_ACTION_LABELS[action]}\n\nEnvie o ID Telegram numérico do alvo.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _prompt_delete_message(callback: CallbackQuery, session: Any) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.selected_action = "delmsg"
    session.waiting_for = "destructive_message_id"
    session.payload["nav_back"] = _action_back_target(session)
    recent = _format_recent_message_quotes(chat_id)
    prompt = "Apagar mensagem\n\nEnvie o message_id numérico ou o link t.me da mensagem."
    if recent:
        prompt += "\n\n" + recent
    await _safe_edit_flow_prompt(callback, session, prompt, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


def _positive_int(text: str) -> int | None:
    try:
        value = int(str(text).strip())
    except Exception:
        return None
    return value if value > 0 else None


async def _handle_destructive_user_id(message: Message, bot: Any, session: Any, text: str) -> None:
    user_id = _positive_int(text)
    if user_id is None:
        await message.answer("Envie um ID numérico válido.")
        return
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    action = str(session.selected_action or "")
    session.payload["pending_destructive_action"] = {"action": action, "target_user_id": user_id}
    session.waiting_for = None
    await _send_flow_confirmation(
        message,
        bot,
        session,
        _confirm_text(session, action, [f"Alvo: {user_id}"]),
    )


async def _handle_destructive_message_id(message: Message, bot: Any, session: Any, text: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    parsed = parse_message_ref(text, selected_chat_id=chat_id)
    if parsed.message_id is None:
        detail = f" Motivo: {parsed.error}." if parsed.error else ""
        await message.answer("Envie um message_id numérico positivo ou um link t.me da mensagem." + detail)
        return
    message_id = parsed.message_id
    session.payload["pending_destructive_action"] = {
        "action": "delmsg",
        "message_id": message_id,
        "message_ref_raw": parsed.raw,
        "chat_id_from_link": parsed.chat_id_from_link,
    }
    session.waiting_for = None
    source_line = "Referência: link Telegram validado" if parsed.chat_id_from_link is not None else "Referência: message_id informado"
    await _send_flow_confirmation(
        message,
        bot,
        session,
        _confirm_text(session, "delmsg", [f"Mensagem: {message_id}", source_line]),
    )


async def _target_admin_status(bot: Any, chat_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return True
    try:
        member = await bot.get_chat_member(chat_id, int(user_id))
    except Exception:
        return False
    status = getattr(member, "status", None)
    status_value = getattr(status, "value", status)
    return status_value in {"administrator", "creator"}


async def _download_pending_photo(bot: Any, file_id: str) -> Any:
    """Baixa foto pendente somente no momento da confirmação.

    Mantém o padrão seguro do painel: receber a foto prepara a ação; a
    alteração real do grupo só acontece depois do botão Confirmar.
    """
    if not file_id:
        raise ValueError("file_id da foto ausente")
    if BufferedInputFile is None:
        raise RuntimeError("BufferedInputFile indisponível no aiogram atual")
    data = BytesIO()
    try:
        await bot.download(file_id, destination=data)
    except TypeError:
        telegram_file = await bot.get_file(file_id)
        await bot.download_file(telegram_file.file_path, destination=data)
    payload = data.getvalue()
    if not payload:
        raise ValueError("download da foto retornou arquivo vazio")
    return BufferedInputFile(payload, filename="tigrao_group_photo.jpg")


async def _confirm_pending_action(callback: CallbackQuery, bot: Any, session: Any) -> None:
    pending = session.payload.get("pending_destructive_action")
    if pending:
        await _execute_pending_destructive_action(callback, bot, session, pending)
        return
    pending_advanced = session.payload.get("pending_advanced_action")
    if pending_advanced:
        await _execute_pending_advanced_action(callback, bot, session, pending_advanced)
        return
    await _safe_edit(callback, "Nenhuma ação pendente para confirmar.", to_inline_keyboard_markup(post_action_keyboard(session.session_id)))


async def _execute_pending_destructive_action(callback: CallbackQuery, bot: Any, session: Any, pending: dict[str, Any]) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    try:
        perms = await get_bot_permissions(bot, chat_id)
        me = await bot.get_me()
        bot_id = int(getattr(me, "id"))
    except Exception as exc:
        storage.log_event(action="destructive_confirm", result="falhou", detection="direta", surface="callback", chat_id=chat_id, chat_title=title, actor_user_id=session.moderator_user_id or session.owner_user_id, details=str(exc))
        await _safe_edit(callback, f"Falha ao revalidar permissões: {exc}\n\nDeseja voltar ao painel principal ou fechar?", to_inline_keyboard_markup(post_action_keyboard(session.session_id)))
        return
    target_user_id = pending.get("target_user_id")
    target_is_admin = False
    if target_user_id is not None:
        target_is_admin = await _target_admin_status(bot, chat_id, int(target_user_id))
    request = DestructiveActionRequest(
        action=str(pending.get("action")),
        chat_id=chat_id,
        chat_title=title,
        actor_user_id=session.moderator_user_id or session.owner_user_id or 0,
        target_user_id=target_user_id,
        message_id=pending.get("message_id"),
        confirmed=True,
        target_is_admin=target_is_admin,
    )
    result = await execute_destructive_action(bot, request, permissions=perms, bot_user_id=bot_id)
    session.payload.pop("pending_destructive_action", None)
    session.selected_action = None
    session.waiting_for = None
    session.payload["nav_back"] = _action_back_target(session)
    await _safe_edit(callback, _result_message(result.ok, result.result, result.detail), to_inline_keyboard_markup(post_action_keyboard(session.session_id)))


def _duration_from_pending(value: int | None) -> timedelta | None:
    return None if value is None else timedelta(seconds=int(value))


def _duration_seconds(value: timedelta | None) -> int | None:
    return None if value is None else int(value.total_seconds())


async def _blocked_protected_target(bot: Any, chat_id: int, user_id: int, bot_id: int | None = None) -> bool:
    target_is_admin = await _target_admin_status(bot, chat_id, user_id)
    return is_protected_target(user_id, bot_user_id=bot_id, target_is_admin=target_is_admin)


async def _execute_pending_advanced_action(callback: CallbackQuery, bot: Any, session: Any, pending: dict[str, Any]) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    action = str(pending.get("action") or "")
    actor = session.moderator_user_id or session.owner_user_id or 0
    try:
        perms = await _revalidated_permissions(bot, chat_id)
        me = await bot.get_me()
        bot_id = int(getattr(me, "id"))
    except Exception as exc:
        storage.log_event(action="advanced_confirm", result="falhou", detection="direta", surface="callback", chat_id=chat_id, chat_title=title, actor_user_id=actor, details=str(exc), metadata={"action": action})
        await _safe_edit(callback, f"Falha ao revalidar permissões: {exc}\n\nDeseja voltar ao painel principal ou fechar?", to_inline_keyboard_markup(post_action_keyboard(session.session_id)))
        return

    if action in {"bantime", "mutetime"}:
        user_id = int(pending.get("user_id") or 0)
        if user_id <= 0:
            result = AdvancedActionResult(False, "bloqueado_alvo_invalido", "ID de usuário inválido.")
        elif await _blocked_protected_target(bot, chat_id, user_id, bot_id):
            storage.log_event(action=f"advanced_{action}", result="bloqueado_alvo_protegido", detection="direta", surface="callback", chat_id=chat_id, chat_title=title, actor_user_id=actor, target_user_id=user_id, details="Ação bloqueada: alvo protegido.")
            result = AdvancedActionResult(False, "bloqueado_alvo_protegido", "Ação bloqueada: alvo protegido, administrador/criador ou o próprio bot.")
        elif action == "bantime":
            result = await ban_user_custom(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, user_id=user_id, permissions=perms, duration=_duration_from_pending(pending.get("duration_seconds")))
        else:
            result = await mute_user_custom(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, user_id=user_id, permissions=perms, duration=_duration_from_pending(pending.get("duration_seconds")))
    elif action == "purge":
        result = await purge_messages(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, message_ids=[int(v) for v in pending.get("message_ids", [])], permissions=perms)
    elif action == "pin":
        result = await pin_message(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, message_id=int(pending.get("message_id") or 0), permissions=perms)
    elif action == "unpin":
        raw_message_id = pending.get("message_id")
        result = await unpin_message(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, message_id=None if raw_message_id is None else int(raw_message_id), permissions=perms)
    elif action == "settitle":
        result = await set_group_title(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, new_title=str(pending.get("new_title") or ""), permissions=perms)
    elif action == "setdesc":
        result = await set_group_description(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, description=str(pending.get("description") or ""), permissions=perms)
    elif action in {"lock", "unlock"}:
        result = await set_group_lockdown(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, permissions=perms, locked=(action == "lock"))
    elif action == "unpinall":
        result = await unpin_all_messages(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, permissions=perms)
    elif action == "react1":
        result = await delete_message_reaction(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, message_id=int(pending.get("message_id") or 0), user_id=pending.get("user_id"), actor_chat_id=pending.get("actor_chat_id"), permissions=perms)
    elif action == "reactall":
        result = await delete_all_message_reactions(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, user_id=pending.get("user_id"), actor_chat_id=pending.get("actor_chat_id"), permissions=perms)
    elif action == "promote":
        user_id = int(pending.get("user_id") or 0)
        if user_id <= 0 or user_id == bot_id:
            result = AdvancedActionResult(False, "bloqueado_alvo_invalido", "ID de usuário inválido ou igual ao próprio bot.")
        else:
            result = await promote_user_admin(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, user_id=user_id, permissions=perms, role=pending.get("role"), custom_flags=pending.get("custom_flags"))
    elif action == "demote":
        user_id = int(pending.get("user_id") or 0)
        if user_id <= 0 or user_id == bot_id:
            result = AdvancedActionResult(False, "bloqueado_alvo_invalido", "ID de usuário inválido ou igual ao próprio bot.")
        else:
            result = await demote_user_admin(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, user_id=user_id, permissions=perms)
    elif action == "admintitle":
        user_id = int(pending.get("user_id") or 0)
        if user_id <= 0 or user_id == bot_id:
            result = AdvancedActionResult(False, "bloqueado_alvo_invalido", "ID de usuário inválido ou igual ao próprio bot.")
        else:
            result = await set_admin_custom_title(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, user_id=user_id, custom_title=str(pending.get("custom_title") or ""), permissions=perms)
    elif action == "bansender":
        result = await ban_sender_chat(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, sender_chat_id=int(pending.get("sender_chat_id") or 0), permissions=perms)
    elif action == "unbansender":
        result = await unban_sender_chat(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, sender_chat_id=int(pending.get("sender_chat_id") or 0), permissions=perms)
    elif action == "linkexport":
        result = await export_primary_invite_link(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, permissions=perms)
    elif action == "linkcreate":
        result = await create_invite_link_full(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, permissions=perms, name=pending.get("name"), duration=_duration_from_pending(pending.get("duration_seconds")), member_limit=pending.get("member_limit"), creates_join_request=bool(pending.get("creates_join_request")))
    elif action == "linkedit":
        result = await edit_invite_link_full(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, permissions=perms, invite_link=str(pending.get("invite_link") or ""), name=pending.get("name"), duration=_duration_from_pending(pending.get("duration_seconds")), member_limit=pending.get("member_limit"), creates_join_request=bool(pending.get("creates_join_request")))
    elif action == "linkrevoke":
        result = await revoke_invite_link_full(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, permissions=perms, invite_link=str(pending.get("invite_link") or ""))
    elif action == "setphoto":
        try:
            photo = await _download_pending_photo(bot, str(pending.get("file_id") or ""))
            result = await set_group_photo_file(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, photo=photo, permissions=perms)
        except Exception as exc:
            result = AdvancedActionResult(False, "falhou", f"Falha ao preparar foto confirmada: {exc}")
    elif action == "delphoto":
        result = await delete_group_photo(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, permissions=perms)
    elif action == "settag":
        result = await set_member_tag_action(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, user_id=int(pending.get("user_id") or 0), tag=str(pending.get("tag") or ""), permissions=perms)
    elif action == "warnadd":
        result = add_warning_action(chat_id=chat_id, chat_title=title, actor_user_id=actor, user_id=int(pending.get("user_id") or 0), reason=pending.get("reason"))
    elif action == "warnclear":
        raw_user_id = pending.get("user_id")
        result = clear_warning_action(chat_id=chat_id, chat_title=title, actor_user_id=actor, user_id=None if raw_user_id is None else int(raw_user_id))
    elif action in {"antiflood", "antiraid", "captcha"}:
        result = set_protection_action(chat_id=chat_id, chat_title=title, actor_user_id=actor, name={"antiflood": "anti_flood", "antiraid": "anti_raid", "captcha": "captcha"}[action], enabled=bool(pending.get("enabled")), config=dict(pending.get("config") or {}))
    else:
        result = AdvancedActionResult(False, "bloqueado_acao_desconhecida", "Ação avançada desconhecida.")

    session.payload.pop("pending_advanced_action", None)
    session.selected_action = None
    session.waiting_for = None
    session.payload["nav_back"] = _action_back_target(session)
    if result.ok and action in {"linkexport", "linkcreate"}:
        link = _extract_invite_link(result.detail)
        if link:
            await _send_persistent_invite_link(callback, chat_title=title, link=link, label="Link de entrada gerado")
    await _safe_edit(callback, _result_message(result.ok, result.result, result.detail), to_inline_keyboard_markup(post_action_keyboard(session.session_id)))


_ADVANCED_PROMPTS = {
    "bantime": "⏱️ Ban por tempo\nEnvie:\nuser_id tempo\n\nEx.: 123456789 30m\nTambém aceita: user_id | tempo.",
    "mutetime": "⏱️ Mute livre\nEnvie:\nuser_id tempo\n\nEx.: 123456789 1h30m\nTambém aceita: user_id | tempo.",
    "purge": "🧹 Purge\nEnvie IDs, links ou intervalo.\nEx.: 10-25 ou 10 11 12.",
    "pin": "📌 Fixar\nEnvie o ID ou link da mensagem.",
    "unpin": "📍 Desfixar\nEnvie ID/link ou ultimo.",
    "settitle": "✏️ Título\nEnvie o novo título.\nLimite: 128 caracteres.",
    "setdesc": "📝 Descrição\nEnvie a nova descrição.\nUse - para limpar.",
    "react1": "⚛️ Remover reação\nEnvie:\nmensagem | user_id\nou\nmensagem | chat:<id>",
    "reactall": "🧹 Limpar reações recentes\nEnvie user_id ou chat:<id>.",
    "promote": "⬆️ Promover admin\nEnvie:\nuser_id perfil\n\nPerfis: leve, moderador, admin, total.\nO usuário precisa estar no grupo.",
    "demote": "⬇️ Rebaixar admin\nEnvie o ID do admin.",
    "admintitle": "🎖️ Título de admin\nEnvie:\nuser_id\ntítulo\n\nMáx.: 16 caracteres. Sem emoji.",
    "bansender": "📡 Banir sender\nEnvie o ID do canal/chat sender.",
    "unbansender": "📡 Desbanir sender\nEnvie o ID do canal/chat sender.",
    "linkcreate": "➕ Criar link adicional\nEnvie 4 linhas:\nnome\nexpiração\nlimite\nsolicitação\n\nEx.:\nEntrada VIP\n7d\n100\nnão\n\nTambém aceita: nome | expiração | limite | solicitação.",
    "linkedit": "✏️ Editar link\nEnvie 5 linhas:\nlink\nnome\nexpiração\nlimite\nsolicitação",
    "linkrevoke": "🧨 Revogar link\nEnvie o link criado pelo bot.",
    "setphoto": "🖼️ Foto do grupo\nEnvie a imagem nesta DM.\nDepois confirme.",
    "settag": "🏷️ Tag de membro\nEnvie:\nuser_id\ntag\n\nMáx.: 16 caracteres.",
    "warnadd": "⚠️ Advertir\nEnvie:\nuser_id\nmotivo",
    "warnlist": "📋 Ver warns\nEnvie um ID ou todos.",
    "warnclear": "🧹 Limpar warns\nEnvie um ID ou todos.",
    "antiflood": "🌊 Anti-flood\nEnvie:\non/off\nlimite\njanela\nmute\n\nEx.:\non\n5\n10s\n10m",
    "antiraid": "🚨 Anti-raid\nEnvie:\non/off\nlimite\njanela\nação\n\nAção: queue, decline ou lock.",
    "captcha": "🧩 Captcha\nEnvie:\non/off\ntempo\ntentativas\n\nEx.:\non\n5m\n3",
}


async def _prompt_advanced_text(callback: CallbackQuery, session: Any, action: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.selected_action = action
    session.waiting_for = "setphoto_upload" if action == "setphoto" else "advanced_text"
    session.payload["nav_back"] = _action_back_target(session)
    await _safe_edit_flow_prompt(callback, session, _advanced_prompt_text(action, chat_id), to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _revalidated_permissions(bot: Any, chat_id: int):
    return await get_bot_permissions(bot, chat_id)


def _advanced_confirmation_text(session: Any, action: str, details: list[str]) -> str:
    return _confirm_text(session, action, details)


async def _prepare_advanced_confirmation(callback: CallbackQuery, bot: Any, session: Any, action: str) -> None:
    # Compatibilidade de auditoria Fase11: {"lock", "unlock", "unpinall"}
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    if action not in {"lock", "unlock", "unpinall", "linkexport", "delphoto"}:
        await _safe_edit(callback, "Ação avançada sem texto desconhecida.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.selected_action = action
    session.waiting_for = None
    session.payload["pending_advanced_action"] = {"action": action}
    session.payload["nav_back"] = _action_back_target(session)
    risk = {
        "lock": "O grupo será fechado para envio de membros comuns.",
        "unlock": "As permissões padrão de envio serão reabertas para membros comuns.",
        "unpinall": "Todos os fixados visíveis para a Bot API serão removidos.",
        "linkexport": "Esta ação gera um novo link principal do bot. O link principal anterior gerado por este bot pode deixar de funcionar. Links criados por outros administradores não são reaproveitados pelo bot.",
        "delphoto": "A foto atual do grupo será removida.",
    }[action]
    await _safe_edit(callback, _advanced_confirmation_text(session, action, [risk]), to_inline_keyboard_markup(confirm_cancel_keyboard(session.session_id)))


async def _handle_advanced_text(message: Message, bot: Any, session: Any, text: str) -> None:
    action = str(session.selected_action or "")
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return

    pending: dict[str, Any] | None = None
    details: list[str] = []

    if action in {"bantime", "mutetime"}:
        parsed = parse_timed_user_action(text)
        if parsed.error or parsed.user_id is None:
            await message.answer(f"Entrada inválida: {parsed.error or 'ID ausente'}. Use: user_id | tempo.")
            return
        pending = {
            "action": action,
            "user_id": parsed.user_id,
            "duration_seconds": _duration_seconds(parsed.duration),
            "duration_label": parsed.duration_raw or "permanente",
        }
        details = [f"ID do alvo: {parsed.user_id}", f"Tempo: {parsed.duration_raw or 'permanente'}"]
    elif action == "purge":
        parsed_ids = parse_message_ids(text, selected_chat_id=chat_id, max_items=100)
        if parsed_ids.error or not parsed_ids.message_ids:
            await message.answer(f"Lista inválida: {parsed_ids.error or 'nenhum ID válido'}. Inválidos: {', '.join(parsed_ids.invalid) if parsed_ids.invalid else 'nenhum'}")
            return
        pending = {"action": action, "message_ids": parsed_ids.message_ids, "invalid_count": len(parsed_ids.invalid)}
        preview = ", ".join(str(mid) for mid in parsed_ids.message_ids[:15])
        if len(parsed_ids.message_ids) > 15:
            preview += ", ..."
        details = [f"Mensagens: {len(parsed_ids.message_ids)}", f"IDs: {preview}", f"Inválidos ignorados: {len(parsed_ids.invalid)}"]
    elif action in {"pin", "unpin"}:
        message_id = None
        if action == "unpin" and text.strip().casefold() in {"ultimo", "último", "mais recente", "recent"}:
            message_id = None
        else:
            parsed_ref = parse_message_ref(text, selected_chat_id=chat_id)
            if parsed_ref.message_id is None:
                await message.answer(f"Referência inválida: {parsed_ref.error or 'message_id ausente'}")
                return
            message_id = parsed_ref.message_id
        pending = {"action": action, "message_id": message_id}
        details = [f"Mensagem: {message_id if message_id is not None else 'fixado mais recente'}"]
    elif action == "promote":
        parsed_admin = parse_admin_role_action(text)
        if parsed_admin.error or parsed_admin.user_id is None:
            await message.answer(f"Entrada inválida: {parsed_admin.error or 'ID ausente'}. Use: user_id | perfil.")
            return
        pending = {"action": action, "user_id": parsed_admin.user_id, "role": parsed_admin.role, "custom_flags": parsed_admin.custom_flags}
        details = [f"ID do alvo: {parsed_admin.user_id}", f"Perfil: {parsed_admin.role or 'moderador'}"]
        if parsed_admin.custom_flags:
            enabled = [k for k, v in parsed_admin.custom_flags.items() if v]
            details.append("Flags: " + (", ".join(enabled) if enabled else "nenhuma"))
    elif action == "demote":
        parsed_ids = parse_user_ids(text)
        if len(parsed_ids.valid) != 1:
            await message.answer("Envie exatamente um user_id numérico válido para rebaixar.")
            return
        pending = {"action": action, "user_id": parsed_ids.valid[0]}
        details = [f"ID do alvo: {parsed_ids.valid[0]}", "Todos os privilégios administrativos serão removidos."]
    elif action == "admintitle":
        parsed_title = parse_admin_title_action(text)
        if parsed_title.error or parsed_title.user_id is None:
            await message.answer(f"Entrada inválida: {parsed_title.error or 'ID ausente'}. Use: user_id | título.")
            return
        pending = {"action": action, "user_id": parsed_title.user_id, "custom_title": parsed_title.title or ""}
        details = [f"ID do alvo: {parsed_title.user_id}", f"Título: {parsed_title.title or '<vazio>'}"]
    elif action in {"bansender", "unbansender"}:
        parsed_sender = parse_sender_chat_action(text)
        if parsed_sender.error or parsed_sender.sender_chat_id is None:
            await message.answer(f"Entrada inválida: {parsed_sender.error or 'sender_chat_id ausente'}.")
            return
        pending = {"action": action, "sender_chat_id": parsed_sender.sender_chat_id}
        details = [f"Sender chat/canal: {parsed_sender.sender_chat_id}"]
    elif action == "linkcreate":
        parsed_link = parse_invite_create_action(text)
        if parsed_link.error:
            await message.answer(f"Entrada inválida: {parsed_link.error}")
            return
        pending = {"action": action, "name": parsed_link.name, "duration_seconds": _duration_seconds(parsed_link.duration), "duration_label": parsed_link.duration_raw or "permanente", "member_limit": parsed_link.member_limit, "creates_join_request": parsed_link.creates_join_request}
        details = [f"Nome: {parsed_link.name or '<sem nome>'}", f"Expiração: {parsed_link.duration_raw or 'permanente'}", f"Limite: {parsed_link.member_limit or 'sem limite'}", f"Solicitação de entrada: {'sim' if parsed_link.creates_join_request else 'não'}"]
    elif action == "linkedit":
        parsed_edit = parse_invite_edit_action(text)
        if parsed_edit.error or parsed_edit.create is None or parsed_edit.invite_link is None:
            await message.answer(f"Entrada inválida: {parsed_edit.error or 'link ausente'}")
            return
        create = parsed_edit.create
        pending = {"action": action, "invite_link": parsed_edit.invite_link, "name": create.name, "duration_seconds": _duration_seconds(create.duration), "duration_label": create.duration_raw or "permanente", "member_limit": create.member_limit, "creates_join_request": create.creates_join_request}
        details = [f"Link: {parsed_edit.invite_link}", f"Nome: {create.name or '<sem nome>'}", f"Expiração: {create.duration_raw or 'permanente'}", f"Limite: {create.member_limit or 'sem limite'}", f"Solicitação de entrada: {'sim' if create.creates_join_request else 'não'}"]
    elif action == "linkrevoke":
        parsed_ref = parse_invite_link_ref(text)
        if parsed_ref.error or parsed_ref.invite_link is None:
            await message.answer(f"Entrada inválida: {parsed_ref.error or 'link ausente'}")
            return
        pending = {"action": action, "invite_link": parsed_ref.invite_link}
        details = [f"Link: {parsed_ref.invite_link}", "Esse link será revogado."]
    elif action == "setphoto":
        session.waiting_for = "setphoto_upload"
        await message.answer("Envie agora a imagem/foto que será usada como foto do grupo.")
        return
    elif action == "settag":
        parsed_tag = parse_user_text_action(text, max_text_len=16, allow_empty_text=True, label="tag")
        if parsed_tag.error or parsed_tag.user_id is None:
            await message.answer(f"Entrada inválida: {parsed_tag.error or 'ID ausente'}")
            return
        pending = {"action": action, "user_id": parsed_tag.user_id, "tag": parsed_tag.text or ""}
        details = [f"ID do alvo: {parsed_tag.user_id}", f"Tag: {parsed_tag.text or '<vazia>'}"]
    elif action == "warnadd":
        parsed_warn = parse_user_text_action(text, max_text_len=240, allow_empty_text=True, label="motivo")
        if parsed_warn.error or parsed_warn.user_id is None:
            await message.answer(f"Entrada inválida: {parsed_warn.error or 'ID ausente'}")
            return
        pending = {"action": action, "user_id": parsed_warn.user_id, "reason": parsed_warn.text or None}
        details = [f"ID do alvo: {parsed_warn.user_id}", f"Motivo: {parsed_warn.text or 'sem motivo'}"]
    elif action == "warnlist":
        user_id = None if text.strip().casefold() in {"todos", "all", "*"} else _positive_int(text)
        if user_id is None and text.strip().casefold() not in {"todos", "all", "*"}:
            await message.answer("Envie um ID ou todos.")
            return
        await _send_flow_result(message, bot, session, format_warning_list(chat_id=chat_id, user_id=user_id))
        session.waiting_for = None
        session.selected_action = None
        return
    elif action == "warnclear":
        user_id = None if text.strip().casefold() in {"todos", "all", "*"} else _positive_int(text)
        if user_id is None and text.strip().casefold() not in {"todos", "all", "*"}:
            await message.answer("Envie um ID ou todos.")
            return
        pending = {"action": action, "user_id": user_id}
        details = ["Alvo: todas as advertências" if user_id is None else f"ID do alvo: {user_id}"]
    elif action == "antiflood":
        parsed_prot = parse_antiflood_setting(text)
        if parsed_prot.error:
            await message.answer(f"Entrada inválida: {parsed_prot.error}")
            return
        pending = {"action": action, "enabled": parsed_prot.enabled, "config": parsed_prot.config}
        details = [f"Ativo: {'sim' if parsed_prot.enabled else 'não'}", f"Config: {parsed_prot.config}"]
    elif action == "antiraid":
        parsed_prot = parse_antiraid_setting(text)
        if parsed_prot.error:
            await message.answer(f"Entrada inválida: {parsed_prot.error}")
            return
        pending = {"action": action, "enabled": parsed_prot.enabled, "config": parsed_prot.config}
        details = [f"Ativo: {'sim' if parsed_prot.enabled else 'não'}", f"Config: {parsed_prot.config}"]
    elif action == "captcha":
        parsed_prot = parse_captcha_setting(text)
        if parsed_prot.error:
            await message.answer(f"Entrada inválida: {parsed_prot.error}")
            return
        pending = {"action": action, "enabled": parsed_prot.enabled, "config": parsed_prot.config}
        details = [f"Ativo: {'sim' if parsed_prot.enabled else 'não'}", f"Config: {parsed_prot.config}"]
    elif action == "settitle":
        clean = text.strip()
        if not 1 <= len(clean) <= 128:
            await message.answer("Título inválido: precisa ter 1 a 128 caracteres.")
            return
        pending = {"action": action, "new_title": clean}
        details = [f"Novo título: {clean}"]
    elif action == "setdesc":
        desc = "" if text.strip() == "-" else text.strip()
        if len(desc) > 255:
            await message.answer("Descrição inválida: precisa ter no máximo 255 caracteres.")
            return
        pending = {"action": action, "description": desc}
        details = ["Nova descrição: <vazia>" if not desc else f"Nova descrição: {desc}"]
    elif action in {"react1", "reactall"}:
        parsed_reaction = parse_reaction_target(text, selected_chat_id=chat_id, require_message=(action == "react1"))
        if parsed_reaction.error:
            await message.answer(f"Entrada inválida: {parsed_reaction.error}")
            return
        pending = {
            "action": action,
            "message_id": parsed_reaction.message_id,
            "user_id": parsed_reaction.user_id,
            "actor_chat_id": parsed_reaction.actor_chat_id,
        }
        actor_label = f"user_id {parsed_reaction.user_id}" if parsed_reaction.user_id is not None else f"chat {parsed_reaction.actor_chat_id}"
        details = [f"Ator da reação: {actor_label}"]
        if parsed_reaction.message_id is not None:
            details.insert(0, f"Mensagem: {parsed_reaction.message_id}")
    else:
        await message.answer("Ação avançada desconhecida ou sessão inválida.")
        session.waiting_for = None
        session.selected_action = None
        return

    session.payload["pending_advanced_action"] = pending
    session.waiting_for = None
    session.payload["nav_back"] = _action_back_target(session)
    # A confirmação nova usa confirm_cancel_keyboard via _send_flow_confirmation.
    await _send_flow_confirmation(message, bot, session, _advanced_confirmation_text(session, action, details))


async def _execute_advanced_no_text(callback: CallbackQuery, bot: Any, session: Any, action: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    actor = session.moderator_user_id or session.owner_user_id or 0
    if action == "admins":
        text = await format_admin_audit(bot, chat_id=chat_id)
        storage.log_event(action="admin_audit", result="consultado", detection="direta", surface="callback", chat_id=chat_id, chat_title=title, actor_user_id=actor, details="Auditoria de administradores consultada.")
        session.payload["nav_back"] = _action_back_target(session)
        await _safe_edit(callback, text[:3900], to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    if action == "protstatus":
        text = format_protection_status(chat_id=chat_id)
        storage.log_event(action="protection_status", result="consultado", detection="direta", surface="callback", chat_id=chat_id, chat_title=title, actor_user_id=actor, details="Status das proteções consultado.")
        session.payload["nav_back"] = _action_back_target(session)
        await _safe_edit(callback, text[:3900], to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    await _safe_edit(callback, "Ação sem texto desconhecida.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _show_ddx(callback: CallbackQuery, session: Any) -> None:
    session.payload["nav_back"] = None
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    await _safe_edit(callback, f"🧨 DDX hard\n\nGrupo: {title}\nID do grupo: {chat_id}", to_inline_keyboard_markup(ddx_keyboard(session.session_id)))


async def _set_ddx_enabled(callback: CallbackQuery, session: Any, enabled: bool) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    affected = storage.set_ddx_enabled(chat_id=chat_id, enabled=enabled)
    storage.log_event(action="ddx_enabled" if enabled else "ddx_disabled", result="concluido", detection="direta", surface="callback", chat_id=chat_id, chat_title=title, actor_user_id=session.moderator_user_id or session.owner_user_id, details=f"Filtros atualizados: {affected}")
    session.payload["nav_back"] = "ddx"
    await _safe_edit(callback, f"DDX {'ativado' if enabled else 'desativado'}. Filtros atualizados: {affected}", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _prompt_ddx_filter(callback: CallbackQuery, session: Any) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.waiting_for = "ddx_filter_text"
    session.payload["nav_back"] = "ddx"
    await _safe_edit_flow_prompt(
        callback,
        session,
        "Envie o filtro DDX hard.\n\n"
        "Formato por quebra de linha:\n"
        "linha 1: texto do filtro\n"
        "linha 2: tempo\n\n"
        "Exemplos:\n"
        "spam\n30m\n\n"
        "link proibido\n1h30m\n\n"
        "palavra proibida\n2d 4h\n\n"
        "termo\naté 2026-07-01T12:00:00Z\n\n"
        "golpe\npermanente\n\n"
        "Se enviar só o texto, o filtro fica permanente.",
        to_inline_keyboard_markup(back_close_keyboard(session.session_id)),
    )


async def _handle_ddx_filter_text(message: Message, bot: Any, session: Any, text: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    parsed = parse_ddx_filter_input(text)
    if parsed.error:
        await message.answer(
            "Filtro DDX inválido. "
            f"Motivo: {parsed.error}.\n\n"
            "Use duas linhas: texto do filtro e tempo. Exemplo: spam\n30m. Envie só o texto para permanente."
        )
        return
    filter_id = storage.create_ddx_filter(
        chat_id=chat_id,
        filter_text=parsed.filter_text,
        created_by=session.moderator_user_id or session.owner_user_id or 0,
        enabled=True,
        duration=parsed.duration,
    )
    duration_label = parsed.duration_raw or "permanente"
    storage.log_event(
        action="ddx_filter_add",
        result="concluido",
        detection="direta",
        surface="dm",
        chat_id=chat_id,
        chat_title=title,
        actor_user_id=session.moderator_user_id or session.owner_user_id,
        details=f"Filtro #{filter_id}: {parsed.filter_text}; tempo: {duration_label}",
    )
    session.waiting_for = None
    await _send_flow_result(message, bot, session, f"Filtro DDX adicionado. ID: {filter_id}\nTempo: {duration_label}")


async def _list_ddx(callback: CallbackQuery, session: Any) -> None:
    session.payload["nav_back"] = "ddx"
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    rows = storage.list_ddx_filters(chat_id=chat_id, limit=20)
    if not rows:
        text = "Nenhum filtro DDX encontrado."
    else:
        def _expires_label(row: dict) -> str:
            expires = row.get("expires_at")
            return "permanente" if not expires else f"expira: {expires}"
        text = "Filtros DDX\n\n" + "\n".join(
            f"#{row['id']} — {'ativo' if row.get('enabled') else 'inativo'} — {_expires_label(row)} — {row.get('filter_text')}"
            for row in rows
        )
    await _safe_edit(callback, text, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _prompt_ddx_remove(callback: CallbackQuery, session: Any) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.waiting_for = "ddx_remove_id"
    session.payload["nav_back"] = "ddx"
    await _safe_edit_flow_prompt(callback, session, "Envie o ID numérico do filtro DDX a remover.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _handle_ddx_remove_id(message: Message, bot: Any, session: Any, text: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    filter_id = _positive_int(text)
    if filter_id is None:
        await message.answer("Envie um ID de filtro numérico positivo.")
        return
    removed = storage.remove_ddx_filter(chat_id=chat_id, filter_id=filter_id)
    storage.log_event(action="ddx_filter_remove", result="concluido" if removed else "nao_encontrado", detection="direta", surface="dm", chat_id=chat_id, chat_title=title, actor_user_id=session.moderator_user_id or session.owner_user_id, details=f"Filtro removido: {filter_id}; linhas: {removed}")
    session.waiting_for = None
    await _send_flow_result(message, bot, session, "Filtro removido." if removed else "Filtro não encontrado.")


async def _show_logs(callback: CallbackQuery, session: Any, action: str) -> None:
    session.payload["nav_back"] = "logs"
    prefixes = {
        "log_mod": "mod",
        "log_use": "use",
        "log_join": "join",
        "log_err": "err",
    }
    rows = storage.list_logs(chat_id=session.selected_chat_id, action_prefix=prefixes.get(action), limit=10)
    text = format_logs(rows)
    await _safe_edit(callback, text, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))

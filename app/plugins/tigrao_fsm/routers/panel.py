"""Router real mínimo do painel Tigrão FSM."""
from __future__ import annotations

import logging
from io import BytesIO
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

from app.config.settings import TIGRAO_BOT_ACCESS_USER_IDS
from app.bot.group_registry import list_groups, remember_group

from .. import storage
from ..keyboards import (
    back_close_keyboard,
    confirm_cancel_keyboard,
    ddx_keyboard,
    destructive_actions_keyboard,
    group_admin_keyboard,
    group_selection_keyboard,
    home_keyboard,
    join_auto_question_keyboard,
    join_requests_keyboard,
    logs_keyboard,
    parse_callback,
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

START_TEXT_AUTHORIZED = """🐯 Rodemotain

Bot online.

Comandos principais:
/start - abre este tutorial rápido
/help - lista comandos e recursos
/tigrao - abre o painel de moderação
/captcha código - responde captcha de entrada

Uso básico:
1. Adicione o bot como administrador no grupo.
2. Dê as permissões necessárias: apagar mensagens, restringir membros, convidar usuários, fixar mensagens, gerenciar tópicos e alterar informações quando for usar essas funções.
3. No privado, use /tigrao para abrir o painel.
4. Selecione o grupo e execute as ações por botões. Ações sensíveis exigem Confirmar.
"""

START_TEXT_UNAUTHORIZED = """🐯 Rodemotain

Bot online, mas este bot é privado.

Seu Telegram ID não está autorizado em TIGRAO_BOT_ACCESS_USER_IDS.
Peça ao dono do bot para incluir seu ID na variável do Railway.
"""

HELP_TEXT_AUTHORIZED = """🐯 Rodemotain — comandos

/start
Mostra tutorial rápido e estado básico do bot.

/help
Lista comandos e recursos disponíveis.

/tigrao
Abre o painel de moderação. Em grupo, o bot tenta enviar o painel no seu privado. Em DM, abre direto.

/captcha código
Usado por novos membros para responder captcha de entrada quando o grupo está protegido por captcha.

Recursos pelo painel:
• seleção de grupos
• ban, unban, mute, unmute e tempos customizados
• apagar mensagem e purge em lote
• DDX temporário/permanente
• solicitações de entrada, fila, captcha, anti-raid e anti-flood
• links de convite
• promover/rebaixar administradores e título customizado
• banir sender chat/canal
• título, descrição e foto do grupo
• tópicos/fórum
• tags reais de membros
• warnings/reincidência
• fixados e reações
• auditoria de administradores/bots
• logs

Observação: as funções dependem das permissões de administrador concedidas ao bot no Telegram.
"""

HELP_TEXT_UNAUTHORIZED = """🐯 Rodemotain — comandos

/start
Mostra estado básico do bot.

/help
Mostra esta ajuda.

Este bot é privado. Para abrir o painel, seu ID precisa estar em TIGRAO_BOT_ACCESS_USER_IDS.
"""


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




@router.message(Command("start"))
async def tigrao_start(message: Message) -> None:
    """Tutorial rápido e resposta de vida do bot.

Responde também usuários não autorizados para deixar claro que o webhook e o
roteamento estão funcionando, sem abrir acesso ao painel.
    """
    user_id = _uid(message)
    if _authorized(user_id):
        await message.answer(START_TEXT_AUTHORIZED)
    else:
        await message.answer(START_TEXT_UNAUTHORIZED)


@router.message(Command("help"))
async def tigrao_help(message: Message) -> None:
    """Lista comandos públicos e recursos do painel."""
    user_id = _uid(message)
    if _authorized(user_id):
        await message.answer(HELP_TEXT_AUTHORIZED)
    else:
        await message.answer(HELP_TEXT_UNAUTHORIZED)

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
    session.payload["nav_back"] = "act"
    details = [f"Arquivo Telegram: {file_id[:16]}...", f"Dimensão: {width or '?'}x{height or '?'}"]
    if size is not None:
        details.append(f"Tamanho: {size} bytes")
    await message.answer(
        _advanced_confirmation_text(session, "setphoto", details),
        reply_markup=to_inline_keyboard_markup(confirm_cancel_keyboard(session.session_id)),
    )


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
        await _handle_destructive_user_id(message, session, text)
    elif session.waiting_for == "destructive_message_id":
        await _handle_destructive_message_id(message, session, text)
    elif session.waiting_for == "advanced_text":
        await _handle_advanced_text(message, bot, session, text)
    elif session.waiting_for == "ddx_filter_text":
        await _handle_ddx_filter_text(message, session, text)
    elif session.waiting_for == "ddx_remove_id":
        await _handle_ddx_remove_id(message, session, text)


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
        await _safe_edit(callback, "Logs do Rodemotain", to_inline_keyboard_markup(logs_keyboard(session_id)))
    elif action in {"log_mod", "log_use", "log_join", "log_err"}:
        await _show_logs(callback, session, action)
    elif action == "join":
        await _show_join_menu(callback, session_id)
    elif action == "join_link":
        await _create_join_link(callback, bot, session)
    elif action == "join_noauto":
        await _show_join_menu(callback, session_id, "Link criado sem autoaceite adicional.")
    elif action == "join_auto":
        await _join_auto_or_list(callback, session)
    elif action == "join_pending":
        await _join_pending(callback, session)
    elif action == "join_accept":
        session.waiting_for = "join_pending_id"
        session.payload["nav_back"] = "join"
        await _safe_edit(callback, "Envie o ID Telegram pendente que deve ser aceito.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
    elif action == "join_decline":
        session.waiting_for = "join_decline_id"
        session.payload["nav_back"] = "join"
        await _safe_edit(callback, "Envie o ID Telegram pendente que deve ser recusado.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
    elif action == "act":
        await _show_actions(callback, session)
    elif action in {"ban", "unban", "mute1h", "mute24h", "muteforever", "unmute"}:
        await _prompt_destructive_user(callback, session, action)
    elif action == "delmsg":
        await _prompt_delete_message(callback, session)
    elif action in {"bantime", "mutetime", "purge", "pin", "unpin", "settitle", "setdesc", "react1", "reactall", "promote", "demote", "admintitle", "bansender", "unbansender", "linkcreate", "linkedit", "linkrevoke", "setphoto", "topiccreate", "topicedit", "topicclose", "topicreopen", "topicdelete", "topicunpin", "topicgedit", "settag", "warnadd", "warnlist", "warnclear", "antiflood", "antiraid", "captcha"}:
        await _prompt_advanced_text(callback, session, action)
    elif action in {"admins", "protstatus"}:
        await _execute_advanced_no_text(callback, bot, session, action)
    elif action in {"lock", "unlock", "unpinall", "linkexport", "delphoto", "topicgclose", "topicgreopen", "topicghide", "topicgunhide", "topicgunpin"}:
        await _prepare_advanced_confirmation(callback, bot, session, action)
    elif action == "confirm":
        await _confirm_pending_action(callback, bot, session)
    elif action == "cancel":
        session.selected_action = None
        session.waiting_for = None
        session.payload.pop("pending_destructive_action", None)
        session.payload.pop("pending_advanced_action", None)
        await _safe_edit(callback, "Ação cancelada.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
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
            "Reações\n\nAs ações reais de reação estão disponíveis abaixo e também dentro de Ações do grupo.",
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
        await _safe_edit(callback, "Logs do Rodemotain", to_inline_keyboard_markup(logs_keyboard(session.session_id)))
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
        f"Tópicos: {yesno(perms.can_manage_topics)}\n"
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


async def _show_join_menu(callback: CallbackQuery, session_id: str, prefix: str | None = None) -> None:
    session = get_session(session_id)
    if session is not None:
        session.payload["nav_back"] = None
    text = "Solicitações de entrada"
    if prefix:
        text = f"{prefix}\n\n{text}"
    await _safe_edit(callback, text, to_inline_keyboard_markup(join_requests_keyboard(session_id)))


async def _create_join_link(callback: CallbackQuery, bot: Any, session: Any) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    try:
        perms = await get_bot_permissions(bot, chat_id)
        if not perms.is_admin or not perms.can_invite_users:
            raise PermissionError("bot sem can_invite_users")
        invite = await create_join_request_link(bot, chat_id, name="Rodemotain")
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
        )
        await _safe_edit(callback, f"Falha ao criar link com solicitação: {exc}", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    link = getattr(invite, "invite_link", None) or getattr(invite, "link", None) or str(invite)
    session.payload["last_invite_link"] = link
    storage.log_event(
        action="join_link_create",
        result="criado",
        detection="direta",
        surface="callback",
        chat_id=chat_id,
        chat_title=title,
        actor_user_id=session.moderator_user_id or session.owner_user_id,
        details="Link com solicitação criado.",
        metadata={"invite_link": link},
    )
    text = f"Link criado com solicitação.\n\n{link}\n\nDeseja ativar autoaceite para IDs específicos?"
    await _safe_edit(callback, text, to_inline_keyboard_markup(join_auto_question_keyboard(session.session_id)))


async def _join_auto_or_list(callback: CallbackQuery, session: Any) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    if session.payload.get("last_invite_link"):
        session.waiting_for = "join_auto_ids"
        session.payload["nav_back"] = "join"
        await _safe_edit(callback, "Envie um ou mais IDs Telegram. Pode separar por espaço, vírgula ou quebra de linha.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
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
    await message.answer(
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
        await message.answer("Envie exatamente um ID Telegram numérico válido.")
        return
    user_id = parsed.valid[0]
    req = storage.find_pending_join_request(chat_id=chat_id, user_id=user_id)
    if req is None:
        await message.answer("Nenhuma solicitação pendente desse ID foi encontrada nas últimas 2h.")
        session.waiting_for = None
        return
    try:
        perms = await get_bot_permissions(bot, chat_id)
        if not perms.is_admin or not perms.can_invite_users:
            raise PermissionError("bot sem can_invite_users")
        detail = await approve_pending_join_request(bot, req, processed_by=session.moderator_user_id or session.owner_user_id, autoaccept=False, origin="aprovação manual por ID pendente")
        storage.update_join_request_status(req)
        storage.log_event(action="join_pending_approve", result=req.status, detection="indireta", surface="banco_pendente", chat_id=chat_id, chat_title=title, actor_user_id=session.moderator_user_id or session.owner_user_id, target_user_id=user_id, details=detail)
        await message.answer(detail)
    except Exception as exc:
        storage.log_event(action="join_pending_approve", result="falhou", detection="indireta", surface="banco_pendente", chat_id=chat_id, chat_title=title, actor_user_id=session.moderator_user_id or session.owner_user_id, target_user_id=user_id, details=str(exc))
        await message.answer(f"Falha ao aprovar ID pendente: {exc}")
    finally:
        session.waiting_for = None




async def _handle_join_decline_id(message: Message, bot: Any, session: Any, text: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    user_id = _positive_int(text)
    if user_id is None:
        await message.answer("Envie um ID Telegram numérico positivo.")
        return
    try:
        perms = await get_bot_permissions(bot, chat_id)
        if not perms.is_admin or not perms.can_invite_users:
            raise PermissionError("bot sem can_invite_users")
        pending = storage.find_pending_join_request(chat_id=chat_id, user_id=user_id)
        if pending is None:
            await message.answer("Não encontrei solicitação pendente para esse ID nos últimos registros ativos.")
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
        await message.answer(f"Falha ao recusar solicitação: {exc}")
        return
    session.waiting_for = None
    await message.answer(f"Solicitação recusada.\n{detail}")


async def _show_actions(callback: CallbackQuery, session: Any) -> None:
    session.payload["nav_back"] = None
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    text = f"Ações do grupo\n\nGrupo: {title}\nID do grupo: {chat_id}\n\nToda ação exige confirmação explícita."
    await _safe_edit(callback, text, to_inline_keyboard_markup(destructive_actions_keyboard(session.session_id)))


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
    "linkexport": "Exportar link primário",
    "linkcreate": "Criar link completo",
    "linkedit": "Editar link",
    "linkrevoke": "Revogar link",
    "setphoto": "Alterar foto do grupo",
    "delphoto": "Remover foto do grupo",
    "topiccreate": "Criar tópico",
    "topicedit": "Editar tópico",
    "topicclose": "Fechar tópico",
    "topicreopen": "Reabrir tópico",
    "topicdelete": "Apagar tópico",
    "topicunpin": "Limpar fixados do tópico",
    "topicgclose": "Fechar tópico geral",
    "topicgreopen": "Reabrir tópico geral",
    "topicgedit": "Renomear tópico geral",
    "topicghide": "Ocultar tópico geral",
    "topicgunhide": "Reexibir tópico geral",
    "topicgunpin": "Limpar fixados do tópico geral",
    "settag": "Tag real de membro",
    "warnadd": "Advertir usuário",
    "warnlist": "Listar advertências",
    "warnclear": "Limpar advertências",
    "protstatus": "Status proteções",
    "antiflood": "Configurar anti-flood",
    "antiraid": "Configurar anti-raid",
    "captcha": "Configurar captcha",
}


async def _prompt_destructive_user(callback: CallbackQuery, session: Any, action: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.selected_action = action
    session.waiting_for = "destructive_user_id"
    session.payload["nav_back"] = "act"
    await _safe_edit(callback, f"{_ACTION_LABELS[action]}\n\nEnvie o ID Telegram numérico do alvo.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _prompt_delete_message(callback: CallbackQuery, session: Any) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.selected_action = "delmsg"
    session.waiting_for = "destructive_message_id"
    session.payload["nav_back"] = "act"
    await _safe_edit(callback, "Apagar mensagem\n\nEnvie o message_id numérico ou o link t.me da mensagem.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


def _positive_int(text: str) -> int | None:
    try:
        value = int(str(text).strip())
    except Exception:
        return None
    return value if value > 0 else None


async def _handle_destructive_user_id(message: Message, session: Any, text: str) -> None:
    user_id = _positive_int(text)
    if user_id is None:
        await message.answer("Envie um ID Telegram numérico positivo.")
        return
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    action = str(session.selected_action or "")
    session.payload["pending_destructive_action"] = {"action": action, "target_user_id": user_id}
    session.waiting_for = None
    await message.answer(
        "Confirmar ação\n\n"
        f"Grupo: {title}\nID do grupo: {chat_id}\n\n"
        f"Ação: {_ACTION_LABELS.get(action, action)}\nID do alvo: {user_id}\n\n"
        "A ação real só será executada após confirmação.",
        reply_markup=to_inline_keyboard_markup(confirm_cancel_keyboard(session.session_id)),
    )


async def _handle_destructive_message_id(message: Message, session: Any, text: str) -> None:
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
    await message.answer(
        "Confirmar ação\n\n"
        f"Grupo: {title}\nID do grupo: {chat_id}\n\n"
        f"Ação: Apagar mensagem\nID da mensagem: {message_id}\n{source_line}\n\n"
        "A ação real só será executada após confirmação.",
        reply_markup=to_inline_keyboard_markup(confirm_cancel_keyboard(session.session_id)),
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
    await _safe_edit(callback, "Nenhuma ação pendente para confirmar.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


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
        await _safe_edit(callback, f"Falha ao revalidar permissões: {exc}", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
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
    session.payload["nav_back"] = "act"
    await _safe_edit(callback, f"Resultado: {result.result}\n{result.detail}", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


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
        await _safe_edit(callback, f"Falha ao revalidar permissões: {exc}", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
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
    elif action == "topiccreate":
        result = await create_forum_topic_action(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, name=str(pending.get("name") or ""), icon_color=pending.get("icon_color"), permissions=perms)
    elif action == "topicedit":
        result = await edit_forum_topic_action(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, message_thread_id=int(pending.get("message_thread_id") or 0), name=str(pending.get("name") or ""), icon_color=pending.get("icon_color"), permissions=perms)
    elif action in {"topicclose", "topicreopen", "topicdelete", "topicunpin"}:
        result = await manage_forum_topic_action(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, action=action, message_thread_id=int(pending.get("message_thread_id") or 0), permissions=perms)
    elif action in {"topicgclose", "topicgreopen", "topicghide", "topicgunhide", "topicgunpin", "topicgedit"}:
        result = await manage_general_forum_topic_action(bot, chat_id=chat_id, chat_title=title, actor_user_id=actor, action=action, permissions=perms, name=pending.get("name"))
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
    session.payload["nav_back"] = "act"
    await _safe_edit(callback, f"Resultado: {result.result}\n{result.detail}", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


_ADVANCED_PROMPTS = {
    "bantime": (
        "Banir com tempo livre\n\n"
        "Envie: user_id | tempo\n"
        "Exemplos: 123456 | 30m, 123456 | 7d, 123456 | permanente."
    ),
    "mutetime": (
        "Mutar com tempo livre\n\n"
        "Envie: user_id | tempo\n"
        "Exemplos: 123456 | 10m, 123456 | 1h30m, 123456 | permanente."
    ),
    "purge": (
        "Purge 1–100 mensagens\n\n"
        "Envie IDs ou links separados por vírgula/espaço. Também aceita intervalo, por exemplo: 10-25."
    ),
    "pin": "Fixar mensagem\n\nEnvie o message_id ou link t.me da mensagem.",
    "unpin": "Desfixar mensagem\n\nEnvie o message_id/link ou a palavra ultimo para desfixar o fixado mais recente.",
    "settitle": "Alterar título\n\nEnvie o novo título do grupo, entre 1 e 128 caracteres.",
    "setdesc": "Alterar descrição\n\nEnvie a nova descrição do grupo, até 255 caracteres. Envie '-' para limpar.",
    "react1": (
        "Remover reação de mensagem\n\n"
        "Envie: message_id/link | user_id\n"
        "Para reação feita como canal/chat, use: message_id/link | chat:<actor_chat_id>."
    ),
    "reactall": (
        "Remover reações recentes do ator\n\n"
        "Envie user_id ou chat:<actor_chat_id>. A Bot API remove até 10000 reações recentes desse ator."
    ),
    "promote": (
        "Promover administrador\n\n"
        "Envie: user_id | perfil\n"
        "Perfis: leve, moderador, admin, total. Também aceita flags: delete, restrict, invite, pin, info, topics, tags, promote."
    ),
    "demote": "Rebaixar administrador\n\nEnvie o user_id do administrador que deve ser rebaixado.",
    "admintitle": "Título customizado de admin\n\nEnvie: user_id | título. Máximo 16 caracteres, sem emoji. Use título vazio para limpar.",
    "bansender": "Banir sender chat/canal\n\nEnvie o sender_chat_id do canal/chat que envia como identidade.",
    "unbansender": "Desbanir sender chat/canal\n\nEnvie o sender_chat_id do canal/chat.",
    "linkcreate": (
        "Criar link completo\n\n"
        "Envie: nome | expiração | limite | solicitação\n"
        "Exemplo: Entrada VIP | 7d | 100 | não\n"
        "Para link com aprovação: Entrada | 2h | 0 | sim"
    ),
    "linkedit": (
        "Editar link\n\n"
        "Envie: link | nome | expiração | limite | solicitação\n"
        "Exemplo: https://t.me/+abc | Entrada | 7d | 100 | não"
    ),
    "linkrevoke": "Revogar link\n\nEnvie o link de convite criado pelo bot.",
    "setphoto": "Alterar foto do grupo\n\nEnvie uma imagem/foto nesta DM. A foto ficará pendente e só será aplicada depois do botão Confirmar.",
    "topiccreate": "Criar tópico\n\nEnvie: nome | cor opcional. Cores permitidas: 7322096, 16766590, 13338331, 9367192, 16749490, 16478047.",
    "topicedit": "Editar tópico\n\nEnvie: thread_id | nome | cor opcional. Nome vazio mantém/limpa conforme Bot API.",
    "topicclose": "Fechar tópico\n\nEnvie o message_thread_id do tópico.",
    "topicreopen": "Reabrir tópico\n\nEnvie o message_thread_id do tópico.",
    "topicdelete": "Apagar tópico\n\nEnvie o message_thread_id do tópico.",
    "topicunpin": "Limpar fixados do tópico\n\nEnvie o message_thread_id do tópico.",
    "topicgedit": "Renomear tópico geral\n\nEnvie o novo nome do tópico geral.",
    "settag": "Tag real de membro\n\nEnvie: user_id | tag. Máximo 16 caracteres, sem emoji. Use tag vazia para limpar.",
    "warnadd": "Advertir usuário\n\nEnvie: user_id | motivo.",
    "warnlist": "Listar advertências\n\nEnvie user_id específico ou a palavra todos.",
    "warnclear": "Limpar advertências\n\nEnvie user_id específico ou a palavra todos.",
    "antiflood": "Config anti-flood\n\nEnvie: on/off | limite | janela | mute. Exemplo: on | 5 | 10s | 10m.",
    "antiraid": "Config anti-raid\n\nEnvie: on/off | limite | janela | ação. Ação: queue, decline ou lock. Exemplo: on | 5 | 1m | queue.",
    "captcha": "Config captcha\n\nEnvie: on/off | tempo | tentativas. Exemplo: on | 5m | 3.",
}


async def _prompt_advanced_text(callback: CallbackQuery, session: Any, action: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.selected_action = action
    session.waiting_for = "setphoto_upload" if action == "setphoto" else "advanced_text"
    session.payload["nav_back"] = "act"
    await _safe_edit(callback, _ADVANCED_PROMPTS[action], to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _revalidated_permissions(bot: Any, chat_id: int):
    return await get_bot_permissions(bot, chat_id)


def _advanced_confirmation_text(session: Any, action: str, details: list[str]) -> str:
    chat_id, title, _ = _selected_group_or_text(session)
    return (
        "Confirmar ação\n\n"
        f"Grupo: {title}\nID do grupo: {chat_id}\n\n"
        f"Ação: {_ACTION_LABELS.get(action, action)}\n"
        + "\n".join(details)
        + "\n\nA ação real só será executada após tocar em Confirmar."
    )


async def _prepare_advanced_confirmation(callback: CallbackQuery, bot: Any, session: Any, action: str) -> None:
    # Compatibilidade de auditoria Fase11: {"lock", "unlock", "unpinall"}
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    if action not in {"lock", "unlock", "unpinall", "linkexport", "delphoto", "topicgclose", "topicgreopen", "topicghide", "topicgunhide", "topicgunpin"}:
        await _safe_edit(callback, "Ação avançada sem texto desconhecida.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    session.selected_action = action
    session.waiting_for = None
    session.payload["pending_advanced_action"] = {"action": action}
    session.payload["nav_back"] = "act"
    risk = {
        "lock": "O grupo será fechado para envio de membros comuns.",
        "unlock": "As permissões padrão de envio serão reabertas para membros comuns.",
        "unpinall": "Todos os fixados visíveis para a Bot API serão removidos.",
        "linkexport": "O link primário gerado pelo bot será exportado/renovado. Links primários anteriores do bot podem ser substituídos.",
        "delphoto": "A foto atual do grupo será removida.",
        "topicgclose": "O tópico geral será fechado.",
        "topicgreopen": "O tópico geral será reaberto.",
        "topicghide": "O tópico geral será ocultado.",
        "topicgunhide": "O tópico geral será reexibido.",
        "topicgunpin": "Todos os fixados do tópico geral serão removidos.",
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
    elif action == "topiccreate":
        parsed_topic = parse_topic_create_action(text)
        if parsed_topic.error or parsed_topic.name is None:
            await message.answer(f"Entrada inválida: {parsed_topic.error or 'nome ausente'}")
            return
        pending = {"action": action, "name": parsed_topic.name, "icon_color": parsed_topic.icon_color}
        details = [f"Nome: {parsed_topic.name}", f"Cor: {parsed_topic.icon_color or 'padrão'}"]
    elif action == "topicedit":
        parsed_topic = parse_topic_edit_action(text)
        if parsed_topic.error or parsed_topic.message_thread_id is None:
            await message.answer(f"Entrada inválida: {parsed_topic.error or 'thread_id ausente'}")
            return
        pending = {"action": action, "message_thread_id": parsed_topic.message_thread_id, "name": parsed_topic.name or "", "icon_color": parsed_topic.icon_color}
        details = [f"Thread ID: {parsed_topic.message_thread_id}", f"Nome: {parsed_topic.name or '<vazio>'}", f"Cor: {parsed_topic.icon_color or 'sem alteração'}"]
    elif action in {"topicclose", "topicreopen", "topicdelete", "topicunpin"}:
        thread_id, err = parse_thread_id(text)
        if err or thread_id is None:
            await message.answer(f"Entrada inválida: {err or 'thread_id ausente'}")
            return
        pending = {"action": action, "message_thread_id": thread_id}
        details = [f"Thread ID: {thread_id}"]
    elif action == "topicgedit":
        clean = text.strip()
        if not 1 <= len(clean) <= 128:
            await message.answer("Nome inválido: precisa ter 1 a 128 caracteres.")
            return
        pending = {"action": action, "name": clean}
        details = [f"Novo nome: {clean}"]
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
            await message.answer("Envie user_id numérico ou todos.")
            return
        await message.answer(format_warning_list(chat_id=chat_id, user_id=user_id))
        session.waiting_for = None
        session.selected_action = None
        return
    elif action == "warnclear":
        user_id = None if text.strip().casefold() in {"todos", "all", "*"} else _positive_int(text)
        if user_id is None and text.strip().casefold() not in {"todos", "all", "*"}:
            await message.answer("Envie user_id numérico ou todos.")
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
    session.payload["nav_back"] = "act"
    await message.answer(
        _advanced_confirmation_text(session, action, details),
        reply_markup=to_inline_keyboard_markup(confirm_cancel_keyboard(session.session_id)),
    )


async def _execute_advanced_no_text(callback: CallbackQuery, bot: Any, session: Any, action: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    actor = session.moderator_user_id or session.owner_user_id or 0
    if action == "admins":
        text = await format_admin_audit(bot, chat_id=chat_id)
        storage.log_event(action="admin_audit", result="consultado", detection="direta", surface="callback", chat_id=chat_id, chat_title=title, actor_user_id=actor, details="Auditoria de administradores consultada.")
        session.payload["nav_back"] = "act"
        await _safe_edit(callback, text[:3900], to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    if action == "protstatus":
        text = format_protection_status(chat_id=chat_id)
        storage.log_event(action="protection_status", result="consultado", detection="direta", surface="callback", chat_id=chat_id, chat_title=title, actor_user_id=actor, details="Status das proteções consultado.")
        session.payload["nav_back"] = "act"
        await _safe_edit(callback, text[:3900], to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    await _safe_edit(callback, "Ação sem texto desconhecida.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _show_ddx(callback: CallbackQuery, session: Any) -> None:
    session.payload["nav_back"] = None
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await _safe_edit(callback, error, to_inline_keyboard_markup(back_close_keyboard(session.session_id)))
        return
    await _safe_edit(callback, f"DDX hard\n\nGrupo: {title}\nID do grupo: {chat_id}", to_inline_keyboard_markup(ddx_keyboard(session.session_id)))


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
    await _safe_edit(
        callback,
        "Envie o filtro DDX hard.\n\n"
        "Formato: texto | tempo\n"
        "Exemplos:\n"
        "spam | 30m\n"
        "link proibido | 1h30m\n"
        "palavra proibida | 2d 4h\n"
        "termo | até 2026-07-01T12:00:00Z\n"
        "golpe | permanente\n\n"
        "Se enviar só o texto, o filtro fica permanente.",
        to_inline_keyboard_markup(back_close_keyboard(session.session_id)),
    )


async def _handle_ddx_filter_text(message: Message, session: Any, text: str) -> None:
    chat_id, title, error = _selected_group_or_text(session)
    if error:
        await message.answer(error)
        return
    parsed = parse_ddx_filter_input(text)
    if parsed.error:
        await message.answer(
            "Filtro DDX inválido. "
            f"Motivo: {parsed.error}.\n\n"
            "Use: texto | tempo. Exemplos: spam | 30m, spam | 1h30m, termo | até 2026-07-01T12:00:00Z. Envie só o texto para permanente."
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
    await message.answer(f"Filtro DDX adicionado. ID: {filter_id}\nTempo: {duration_label}")


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
    await _safe_edit(callback, "Envie o ID numérico do filtro DDX a remover.", to_inline_keyboard_markup(back_close_keyboard(session.session_id)))


async def _handle_ddx_remove_id(message: Message, session: Any, text: str) -> None:
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
    await message.answer("Filtro removido." if removed else "Filtro não encontrado.")


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

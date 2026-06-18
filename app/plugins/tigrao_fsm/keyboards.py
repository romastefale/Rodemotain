"""Teclados seguros do Tigrão FSM isolado."""
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any, Literal

try:  # aiogram é opcional nesta fase isolada; fallback não deve quebrar import.
    from aiogram.types import CopyTextButton as _AiogramCopyTextButton
    from aiogram.types import InlineKeyboardButton as _AiogramInlineKeyboardButton
    from aiogram.types import InlineKeyboardMarkup as _AiogramInlineKeyboardMarkup
except Exception:  # pragma: no cover - depende da instalação local do aiogram.
    _AiogramCopyTextButton = None
    _AiogramInlineKeyboardButton = None
    _AiogramInlineKeyboardMarkup = None

ButtonStyle = Literal["primary", "success", "danger"]
CALLBACK_PREFIX = "tgf:"
MAX_CALLBACK_DATA_BYTES = 64
ALLOWED_BUTTON_STYLES: tuple[ButtonStyle, ...] = ("primary", "success", "danger")
_ALLOWED_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")
CALLBACK_ACTIONS = frozenset({
    "home",
    "grp",
    "grp_sel",
    "logs",
    "log_mod",
    "log_use",
    "log_join",
    "log_err",
    "join",
    "join_link",
    "join_auto",
    "join_pending",
    "join_accept",
    "join_decline",
    "join_noauto",
    "ddx",
    "act",
    "ban",
    "unban",
    "mute1h",
    "mute24h",
    "muteforever",
    "unmute",
    "bantime",
    "mutetime",
    "purge",
    "lock",
    "unlock",
    "pin",
    "unpin",
    "unpinall",
    "settitle",
    "setdesc",
    "admins",
    "react1",
    "reactall",
    "promote",
    "demote",
    "admintitle",
    "bansender",
    "unbansender",
    "linkexport",
    "linkcreate",
    "linkedit",
    "linkrevoke",
    "setphoto",
    "delphoto",
    "topiccreate",
    "topicedit",
    "topicclose",
    "topicreopen",
    "topicdelete",
    "topicunpin",
    "topicgclose",
    "topicgreopen",
    "topicgedit",
    "topicghide",
    "topicgunhide",
    "topicgunpin",
    "settag",
    "warnadd",
    "warnlist",
    "warnclear",
    "protstatus",
    "antiflood",
    "antiraid",
    "captcha",
    "delmsg",
    "ddxon",
    "ddxoff",
    "ddxadd",
    "ddxlist",
    "ddxremove",
    "react",
    "confirm",
    "cancel",
    "back",
    "close",
    *(f"g{i}" for i in range(50)),
})


@dataclass(frozen=True, slots=True)
class TigraoButtonSpec:
    text: str
    callback_data: str | None = None
    url: str | None = None
    copy_text: str | None = None
    style: ButtonStyle = "primary"


def _valid_token(value: str | None) -> bool:
    return bool(value) and ":" not in value and bool(_ALLOWED_TOKEN_RE.fullmatch(value))


def _callback_is_valid(data: str) -> bool:
    if not data or len(data.encode("utf-8")) > MAX_CALLBACK_DATA_BYTES:
        return False
    if not data.startswith(CALLBACK_PREFIX):
        return False
    tail = data[len(CALLBACK_PREFIX):]
    pieces = tail.split(":")
    if len(pieces) != 2:
        return False
    sid, action = pieces
    return _valid_token(sid) and _valid_token(action) and action in CALLBACK_ACTIONS


def make_callback(session_id: str, *parts: str) -> str:
    if not _valid_token(session_id):
        raise ValueError("invalid Tigrão session_id")
    if len(parts) != 1 or not _valid_token(parts[0]) or parts[0] not in CALLBACK_ACTIONS:
        raise ValueError("invalid Tigrão callback action")
    callback = f"{CALLBACK_PREFIX}{session_id}:{parts[0]}"
    if not _callback_is_valid(callback):
        raise ValueError("invalid or too long Tigrão callback_data")
    return callback


def parse_callback(data: str) -> tuple[str, tuple[str, ...]] | None:
    if not isinstance(data, str) or not _callback_is_valid(data):
        return None
    sid, action = data[len(CALLBACK_PREFIX):].split(":")
    return sid, (action,)


def _validate_single_action(callback_data: str | None, url: str | None, copy_text: str | None) -> None:
    actions = [callback_data is not None, url is not None, copy_text is not None]
    if sum(actions) != 1:
        raise ValueError("exactly one button action is required")
    if callback_data is not None and not _callback_is_valid(callback_data):
        raise ValueError("invalid internal Tigrão callback_data")
    if copy_text is not None and not (1 <= len(copy_text) <= 256):
        raise ValueError("copy_text must contain 1 to 256 characters")


def button(
    text: str,
    callback_data: str | None = None,
    *,
    url: str | None = None,
    copy_text: str | None = None,
    style: ButtonStyle = "primary",
) -> TigraoButtonSpec:
    if style not in ALLOWED_BUTTON_STYLES:
        raise ValueError(f"unsupported Tigrão button style: {style}")
    _validate_single_action(callback_data, url, copy_text)
    return TigraoButtonSpec(text=text, callback_data=callback_data, url=url, copy_text=copy_text, style=style)


def _copy_text_button(value: str) -> Any | None:
    """Constrói CopyTextButton real ou informa que o fallback deve preservar o spec.

    A Bot API/aiogram esperam um objeto CopyTextButton; nunca passe string crua
    para InlineKeyboardButton.copy_text.
    """
    if _AiogramCopyTextButton is None:
        return None
    try:
        return _AiogramCopyTextButton(text=value)
    except TypeError:
        return None


def _button_kwargs(spec: TigraoButtonSpec) -> dict[str, Any] | None:
    kwargs: dict[str, Any] = {"text": spec.text}
    if spec.callback_data is not None:
        kwargs["callback_data"] = spec.callback_data
    elif spec.url is not None:
        kwargs["url"] = spec.url
    elif spec.copy_text is not None:
        copy_text_button = _copy_text_button(spec.copy_text)
        if copy_text_button is None:
            return None
        kwargs["copy_text"] = copy_text_button
    return kwargs


def to_inline_keyboard_button(spec: TigraoButtonSpec) -> Any:
    if _AiogramInlineKeyboardButton is None:
        return spec

    kwargs = _button_kwargs(spec)
    if kwargs is None:
        return spec
    try:
        sig = inspect.signature(_AiogramInlineKeyboardButton)
        if "style" in sig.parameters:
            kwargs["style"] = spec.style
    except (TypeError, ValueError):
        kwargs["style"] = spec.style
    try:
        return _AiogramInlineKeyboardButton(**kwargs)
    except TypeError:
        kwargs.pop("style", None)
        try:
            return _AiogramInlineKeyboardButton(**kwargs)
        except TypeError:
            return spec


def to_inline_keyboard_markup(rows: list[list[TigraoButtonSpec]]) -> Any:
    keyboard = [[to_inline_keyboard_button(spec) for spec in row] for row in rows]
    if _AiogramInlineKeyboardMarkup is None:
        return keyboard
    try:
        return _AiogramInlineKeyboardMarkup(inline_keyboard=keyboard)
    except TypeError:
        return keyboard


def home_keyboard(session_id: str) -> list[list[TigraoButtonSpec]]:
    return [
        [button("Selecionar grupo", make_callback(session_id, "grp"), style="primary")],
        [button("Fechar", make_callback(session_id, "close"), style="danger")],
    ]


def group_selection_keyboard(session_id: str, groups: list[dict]) -> list[list[TigraoButtonSpec]]:
    rows: list[list[TigraoButtonSpec]] = []
    for idx, group in enumerate(groups[:50]):
        title = str(group.get("title") or group.get("username") or group.get("chat_id") or "Grupo")[:40]
        rows.append([button(title, make_callback(session_id, f"g{idx}"), style="primary")])
    rows.append([button("Voltar", make_callback(session_id, "back"), style="primary")])
    rows.append([button("Fechar", make_callback(session_id, "close"), style="danger")])
    return rows


def back_close_keyboard(session_id: str) -> list[list[TigraoButtonSpec]]:
    return [
        [button("Voltar", make_callback(session_id, "back"), style="primary")],
        [button("Fechar", make_callback(session_id, "close"), style="danger")],
    ]


def group_admin_keyboard(
    session_id: str,
    *,
    destructive_actions_enabled: bool = False,
    ddx_enabled: bool = False,
    reactions_enabled: bool = False,
) -> list[list[TigraoButtonSpec]]:
    rows: list[list[TigraoButtonSpec]] = [
        [button("Logs", make_callback(session_id, "logs"), style="primary")],
        [button("Solicitações de entrada", make_callback(session_id, "join"), style="primary")],
    ]
    if destructive_actions_enabled:
        rows.append([button("Ações do grupo", make_callback(session_id, "act"), style="danger")])
    if ddx_enabled:
        rows.append([button("DDX hard", make_callback(session_id, "ddx"), style="danger")])
    if reactions_enabled:
        rows.append([button("Reações", make_callback(session_id, "react"), style="danger")])
    rows.extend([
        [button("Voltar", make_callback(session_id, "back"), style="primary")],
        [button("Fechar", make_callback(session_id, "close"), style="danger")],
    ])
    return rows


def join_requests_keyboard(session_id: str) -> list[list[TigraoButtonSpec]]:
    return [
        [button("Ver pendentes 2h", make_callback(session_id, "join_pending"), style="primary")],
        [button("Aceitar ID pendente", make_callback(session_id, "join_accept"), style="success")],
        [button("Recusar ID pendente", make_callback(session_id, "join_decline"), style="danger")],
        [button("Criar link com solicitação", make_callback(session_id, "join_link"), style="primary")],
        [button("Autorizações automáticas", make_callback(session_id, "join_auto"), style="primary")],
        [button("Voltar", make_callback(session_id, "back"), style="primary")],
        [button("Fechar", make_callback(session_id, "close"), style="danger")],
    ]


def join_auto_question_keyboard(session_id: str) -> list[list[TigraoButtonSpec]]:
    return [
        [button("Sim, informar IDs", make_callback(session_id, "join_auto"), style="success")],
        [button("Não, só criar link", make_callback(session_id, "join_noauto"), style="primary")],
        [button("Voltar", make_callback(session_id, "join"), style="primary")],
        [button("Fechar", make_callback(session_id, "close"), style="danger")],
    ]


def logs_keyboard(session_id: str) -> list[list[TigraoButtonSpec]]:
    return [
        [button("Moderação", make_callback(session_id, "log_mod"), style="primary")],
        [button("Uso", make_callback(session_id, "log_use"), style="primary")],
        [button("Entradas", make_callback(session_id, "log_join"), style="primary")],
        [button("Erros", make_callback(session_id, "log_err"), style="primary")],
        [button("Voltar", make_callback(session_id, "back"), style="primary")],
        [button("Fechar", make_callback(session_id, "close"), style="danger")],
    ]


def destructive_actions_keyboard(session_id: str) -> list[list[TigraoButtonSpec]]:
    return [
        [button("Banir usuário", make_callback(session_id, "ban"), style="danger")],
        [button("Banir com tempo livre", make_callback(session_id, "bantime"), style="danger")],
        [button("Desbanir usuário", make_callback(session_id, "unban"), style="success")],
        [button("Mutar 1 hora", make_callback(session_id, "mute1h"), style="danger")],
        [button("Mutar 24 horas", make_callback(session_id, "mute24h"), style="danger")],
        [button("Mutar indefinido", make_callback(session_id, "muteforever"), style="danger")],
        [button("Mutar com tempo livre", make_callback(session_id, "mutetime"), style="danger")],
        [button("Desmutar usuário", make_callback(session_id, "unmute"), style="success")],
        [button("Apagar mensagem", make_callback(session_id, "delmsg"), style="danger")],
        [button("Purge 1–100 mensagens", make_callback(session_id, "purge"), style="danger")],
        [button("Fechar grupo / lockdown", make_callback(session_id, "lock"), style="danger")],
        [button("Reabrir grupo / unlock", make_callback(session_id, "unlock"), style="success")],
        [button("Fixar mensagem", make_callback(session_id, "pin"), style="primary")],
        [button("Desfixar mensagem", make_callback(session_id, "unpin"), style="primary")],
        [button("Limpar todos os fixados", make_callback(session_id, "unpinall"), style="danger")],
        [button("Alterar título", make_callback(session_id, "settitle"), style="danger")],
        [button("Alterar descrição", make_callback(session_id, "setdesc"), style="danger")],
        [button("Promover admin", make_callback(session_id, "promote"), style="danger")],
        [button("Rebaixar admin", make_callback(session_id, "demote"), style="danger")],
        [button("Título custom de admin", make_callback(session_id, "admintitle"), style="danger")],
        [button("Banir sender chat/canal", make_callback(session_id, "bansender"), style="danger")],
        [button("Desbanir sender chat/canal", make_callback(session_id, "unbansender"), style="success")],
        [button("Exportar link primário", make_callback(session_id, "linkexport"), style="danger")],
        [button("Criar link completo", make_callback(session_id, "linkcreate"), style="primary")],
        [button("Editar link", make_callback(session_id, "linkedit"), style="primary")],
        [button("Revogar link", make_callback(session_id, "linkrevoke"), style="danger")],
        [button("Alterar foto do grupo", make_callback(session_id, "setphoto"), style="danger")],
        [button("Remover foto do grupo", make_callback(session_id, "delphoto"), style="danger")],
        [button("Criar tópico", make_callback(session_id, "topiccreate"), style="primary")],
        [button("Editar tópico", make_callback(session_id, "topicedit"), style="primary")],
        [button("Fechar tópico", make_callback(session_id, "topicclose"), style="danger")],
        [button("Reabrir tópico", make_callback(session_id, "topicreopen"), style="success")],
        [button("Apagar tópico", make_callback(session_id, "topicdelete"), style="danger")],
        [button("Limpar fixados do tópico", make_callback(session_id, "topicunpin"), style="danger")],
        [button("Fechar tópico geral", make_callback(session_id, "topicgclose"), style="danger")],
        [button("Reabrir tópico geral", make_callback(session_id, "topicgreopen"), style="success")],
        [button("Renomear tópico geral", make_callback(session_id, "topicgedit"), style="primary")],
        [button("Ocultar tópico geral", make_callback(session_id, "topicghide"), style="danger")],
        [button("Reexibir tópico geral", make_callback(session_id, "topicgunhide"), style="success")],
        [button("Limpar fixados do geral", make_callback(session_id, "topicgunpin"), style="danger")],
        [button("Tag real de membro", make_callback(session_id, "settag"), style="danger")],
        [button("Advertir usuário", make_callback(session_id, "warnadd"), style="danger")],
        [button("Listar advertências", make_callback(session_id, "warnlist"), style="primary")],
        [button("Limpar advertências", make_callback(session_id, "warnclear"), style="danger")],
        [button("Status proteções", make_callback(session_id, "protstatus"), style="primary")],
        [button("Config anti-flood", make_callback(session_id, "antiflood"), style="danger")],
        [button("Config anti-raid", make_callback(session_id, "antiraid"), style="danger")],
        [button("Config captcha", make_callback(session_id, "captcha"), style="danger")],
        [button("Auditar admins/bots", make_callback(session_id, "admins"), style="primary")],
        [button("Remover reação de mensagem", make_callback(session_id, "react1"), style="danger")],
        [button("Remover reações recentes", make_callback(session_id, "reactall"), style="danger")],
        [button("Voltar", make_callback(session_id, "back"), style="primary")],
        [button("Fechar", make_callback(session_id, "close"), style="danger")],
    ]


def confirm_cancel_keyboard(session_id: str) -> list[list[TigraoButtonSpec]]:
    return [
        [button("Confirmar", make_callback(session_id, "confirm"), style="danger")],
        [button("Cancelar", make_callback(session_id, "cancel"), style="primary")],
    ]


def ddx_keyboard(session_id: str) -> list[list[TigraoButtonSpec]]:
    return [
        [button("Ativar DDX", make_callback(session_id, "ddxon"), style="success")],
        [button("Desativar DDX", make_callback(session_id, "ddxoff"), style="danger")],
        [button("Adicionar filtro", make_callback(session_id, "ddxadd"), style="primary")],
        [button("Listar filtros", make_callback(session_id, "ddxlist"), style="primary")],
        [button("Remover filtro", make_callback(session_id, "ddxremove"), style="danger")],
        [button("Voltar", make_callback(session_id, "back"), style="primary")],
        [button("Fechar", make_callback(session_id, "close"), style="danger")],
    ]


def reactions_keyboard(session_id: str) -> list[list[TigraoButtonSpec]]:
    return [
        [button("Voltar", make_callback(session_id, "back"), style="primary")],
        [button("Fechar", make_callback(session_id, "close"), style="danger")],
    ]

"""Parsers isolados do Tigrão FSM."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_SPLIT_RE = re.compile(r"[\s,]+")


@dataclass(frozen=True, slots=True)
class ParsedDuration:
    duration: timedelta | None
    raw: str = ""
    error: str | None = None
    until: datetime | None = None


_DURATION_TOKEN_RE = re.compile(
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>segundos|segundo|semanas|semana|minutos|minuto|months|month|years|year|horas|hora|meses|segs|mins|dias|anos|seg|sem|min|hrs|hr|dia|mes|ano|s|m|h|d|w|a)",
    re.IGNORECASE,
)
_DURATION_UNITS_SECONDS: dict[str, int] = {
    "s": 1,
    "seg": 1,
    "segs": 1,
    "segundo": 1,
    "segundos": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minuto": 60,
    "minutos": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hora": 3600,
    "horas": 3600,
    "d": 86400,
    "dia": 86400,
    "dias": 86400,
    "w": 604800,
    "sem": 604800,
    "semana": 604800,
    "semanas": 604800,
    # aproximações operacionais para expiração interna de regras.
    "mes": 2592000,
    "meses": 2592000,
    "month": 2592000,
    "months": 2592000,
    "a": 31536000,
    "ano": 31536000,
    "anos": 31536000,
    "year": 31536000,
    "years": 31536000,
}
_PERMANENT_DURATION_TOKENS = {
    "",
    "0",
    "permanente",
    "permanentemente",
    "fixo",
    "infinito",
    "indefinido",
    "sem prazo",
    "sem tempo",
    "forever",
    "permanent",
}
_ABSOLUTE_PREFIXES = ("ate ", "até ", "until ")


def _parse_absolute_until(raw: str) -> ParsedDuration | None:
    lowered = raw.casefold().strip()
    prefix = next((p for p in _ABSOLUTE_PREFIXES if lowered.startswith(p)), None)
    if prefix is None:
        return None
    value = raw[len(prefix):].strip()
    if not value:
        return ParsedDuration(duration=None, raw=raw, error="data absoluta ausente")
    try:
        # Aceita ISO 8601: 2026-07-01T12:00:00Z ou com offset.
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return ParsedDuration(duration=None, raw=raw, error="data absoluta inválida; use ISO 8601")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if parsed <= now:
        return ParsedDuration(duration=None, raw=raw, error="data absoluta precisa estar no futuro")
    return ParsedDuration(duration=parsed - now, raw=raw, until=parsed)


def parse_duration(text: str) -> ParsedDuration:
    """Converte duração humana em ``timedelta``.

    Aceita duração simples ou composta: ``30s``, ``10m``, ``2h``,
    ``1h30m``, ``2d 4h``, ``1 semana``. Também aceita prazo absoluto
    ISO-8601: ``até 2026-07-01T12:00:00Z``. Retorna ``duration=None`` para
    permanente/sem expiração.
    """
    raw = str(text or "").strip()
    lowered = raw.casefold()
    if lowered in _PERMANENT_DURATION_TOKENS:
        return ParsedDuration(duration=None, raw=raw)

    absolute = _parse_absolute_until(raw)
    if absolute is not None:
        return absolute

    total_seconds = 0.0
    pos = 0
    found = False
    for match in _DURATION_TOKEN_RE.finditer(raw):
        gap = raw[pos:match.start()]
        if gap.strip() not in {"", ",", "+"}:
            return ParsedDuration(duration=None, raw=raw, error="sintaxe de duração inválida")
        amount = float(match.group("amount").replace(",", "."))
        unit = match.group("unit").casefold()
        factor = _DURATION_UNITS_SECONDS.get(unit)
        if factor is None:
            return ParsedDuration(duration=None, raw=raw, error="unidade de duração inválida")
        total_seconds += amount * factor
        pos = match.end()
        found = True
    if not found or raw[pos:].strip() not in {"", ",", "+"}:
        return ParsedDuration(duration=None, raw=raw, error="sintaxe de duração inválida")
    seconds = int(total_seconds)
    if seconds <= 0:
        return ParsedDuration(duration=None, raw=raw, error="duração precisa ser positiva")
    return ParsedDuration(duration=timedelta(seconds=seconds), raw=raw)


@dataclass(frozen=True, slots=True)
class ParsedDdxFilterInput:
    filter_text: str
    duration: timedelta | None
    duration_raw: str | None = None
    error: str | None = None


def parse_ddx_filter_input(text: str) -> ParsedDdxFilterInput:
    """Lê entrada do painel DDX no formato ``texto | duração``.

    Exemplos aceitos: ``spam``; ``spam | 30m``; ``spam | 1h30m``;
    ``convite externo | 2d 4h``; ``golpe | permanente``;
    ``termo | até 2026-07-01T12:00:00Z``.
    """
    raw = str(text or "").strip()
    if not raw:
        return ParsedDdxFilterInput(filter_text="", duration=None, error="filtro vazio")
    filter_text = raw
    duration_raw: str | None = None
    duration: timedelta | None = None
    if "|" in raw:
        left, right = raw.rsplit("|", 1)
        filter_text = left.strip()
        duration_raw = right.strip()
        parsed_duration = parse_duration(duration_raw)
        if parsed_duration.error:
            return ParsedDdxFilterInput(filter_text=filter_text, duration=None, duration_raw=duration_raw, error=parsed_duration.error)
        duration = parsed_duration.duration
    if not filter_text:
        return ParsedDdxFilterInput(filter_text="", duration=None, duration_raw=duration_raw, error="filtro vazio")
    if len(filter_text) > 240:
        return ParsedDdxFilterInput(filter_text=filter_text, duration=duration, duration_raw=duration_raw, error="filtro muito longo")
    return ParsedDdxFilterInput(filter_text=filter_text, duration=duration, duration_raw=duration_raw)


@dataclass(frozen=True, slots=True)
class ParsedUserIds:
    valid: list[int]
    invalid: list[str]


def parse_user_ids(text: str) -> ParsedUserIds:
    seen: set[int] = set()
    valid: list[int] = []
    invalid: list[str] = []
    for token in [t for t in _SPLIT_RE.split((text or "").strip()) if t]:
        if not token.isdecimal():
            invalid.append(token)
            continue
        value = int(token)
        if value <= 0:
            invalid.append(token)
            continue
        if value not in seen:
            seen.add(value)
            valid.append(value)
    return ParsedUserIds(valid=valid, invalid=invalid)


def parse_x9_query(query: str) -> str | None:
    raw = query or ""
    clean = raw.strip()
    lowered = clean.casefold()
    if lowered == "x9":
        return ""
    if not lowered.startswith("x9 "):
        return None
    return clean[3:].strip()


@dataclass(frozen=True, slots=True)
class ParsedMessageRef:
    message_id: int | None
    chat_id_from_link: int | None = None
    raw: str = ""
    error: str | None = None


_TME_LINK_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?:c/)?(?P<path>[^?#]+)",
    re.IGNORECASE,
)


def _private_chat_id_from_internal(value: str) -> int | None:
    if not value.isdecimal():
        return None
    return int(f"-100{int(value)}")


def parse_message_ref(text: str, *, selected_chat_id: int | None = None) -> ParsedMessageRef:
    """Aceita message_id bruto ou link Telegram e retorna referência validada.

    Formatos aceitos:
    - ``12345``
    - ``https://t.me/c/<chat_interno>/<message_id>``
    - ``https://t.me/c/<chat_interno>/<topic_id>/<message_id>``
    - ``https://t.me/<username>/<message_id>``

    Quando o link privado ``/c/`` informa outro grupo, a função não inventa
    correção: retorna erro para impedir apagar mensagem do grupo errado.
    """
    raw = (text or "").strip()
    if not raw:
        return ParsedMessageRef(message_id=None, raw=raw, error="referência vazia")
    if raw.isdecimal():
        value = int(raw)
        if value > 0:
            return ParsedMessageRef(message_id=value, raw=raw)
        return ParsedMessageRef(message_id=None, raw=raw, error="message_id inválido")

    match = _TME_LINK_RE.match(raw)
    if not match:
        return ParsedMessageRef(message_id=None, raw=raw, error="envie um message_id ou link t.me válido")

    pieces = [piece for piece in match.group("path").strip("/").split("/") if piece]
    if len(pieces) < 2:
        return ParsedMessageRef(message_id=None, raw=raw, error="link Telegram sem message_id")

    chat_id_from_link: int | None = None
    if raw.casefold().startswith(("https://t.me/c/", "http://t.me/c/", "t.me/c/", "https://www.t.me/c/", "http://www.t.me/c/", "www.t.me/c/", "https://telegram.me/c/", "http://telegram.me/c/", "telegram.me/c/")):
        internal_chat = pieces[0]
        chat_id_from_link = _private_chat_id_from_internal(internal_chat)

    message_token = pieces[-1]
    if not message_token.isdecimal():
        return ParsedMessageRef(message_id=None, chat_id_from_link=chat_id_from_link, raw=raw, error="message_id ausente ou inválido no link")
    message_id = int(message_token)
    if message_id <= 0:
        return ParsedMessageRef(message_id=None, chat_id_from_link=chat_id_from_link, raw=raw, error="message_id inválido")

    if selected_chat_id is not None and chat_id_from_link is not None and int(selected_chat_id) != int(chat_id_from_link):
        return ParsedMessageRef(
            message_id=None,
            chat_id_from_link=chat_id_from_link,
            raw=raw,
            error="o link informado pertence a outro grupo selecionado",
        )
    return ParsedMessageRef(message_id=message_id, chat_id_from_link=chat_id_from_link, raw=raw)

@dataclass(frozen=True, slots=True)
class ParsedTimedUserAction:
    user_id: int | None
    duration: timedelta | None
    duration_raw: str | None = None
    error: str | None = None


def parse_timed_user_action(text: str) -> ParsedTimedUserAction:
    """Lê ``user_id | duração`` para ban/mute temporário customizado."""
    raw = str(text or "").strip()
    if not raw:
        return ParsedTimedUserAction(user_id=None, duration=None, error="entrada vazia")
    if "|" in raw:
        left, right = raw.rsplit("|", 1)
        user_raw = left.strip()
        duration_raw = right.strip()
    else:
        pieces = raw.split(maxsplit=1)
        user_raw = pieces[0].strip()
        duration_raw = pieces[1].strip() if len(pieces) > 1 else "permanente"
    if not user_raw.isdecimal() or int(user_raw) <= 0:
        return ParsedTimedUserAction(user_id=None, duration=None, duration_raw=duration_raw, error="ID de usuário inválido")
    parsed = parse_duration(duration_raw)
    if parsed.error:
        return ParsedTimedUserAction(user_id=int(user_raw), duration=None, duration_raw=duration_raw, error=parsed.error)
    return ParsedTimedUserAction(user_id=int(user_raw), duration=parsed.duration, duration_raw=duration_raw or "permanente")


@dataclass(frozen=True, slots=True)
class ParsedMessageIds:
    message_ids: list[int]
    invalid: list[str]
    error: str | None = None


def parse_message_ids(text: str, *, selected_chat_id: int | None = None, max_items: int = 100) -> ParsedMessageIds:
    """Lê lista ou intervalo de mensagens para deleteMessages.

    Aceita ``10-20``, ``10,11,12`` e links ``t.me`` separados por espaço,
    vírgula ou quebra de linha. O limite operacional é 100 IDs por chamada.
    """
    raw = str(text or "").strip()
    if not raw:
        return ParsedMessageIds(message_ids=[], invalid=[], error="lista vazia")
    normalized = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "-", raw)
    ids: list[int] = []
    invalid: list[str] = []
    for token in [t for t in re.split(r"[\s,]+", normalized) if t]:
        if re.fullmatch(r"\d+\s*-\s*\d+", token):
            start_raw, end_raw = re.split(r"\s*-\s*", token, maxsplit=1)
            start, end = int(start_raw), int(end_raw)
            if start <= 0 or end <= 0 or end < start:
                invalid.append(token)
                continue
            ids.extend(range(start, end + 1))
            continue
        parsed_ref = parse_message_ref(token, selected_chat_id=selected_chat_id)
        if parsed_ref.message_id is None:
            invalid.append(token)
            continue
        ids.append(parsed_ref.message_id)
    clean = sorted(set(ids))
    if len(clean) > max_items:
        return ParsedMessageIds(message_ids=clean[:max_items], invalid=invalid, error=f"limite de {max_items} mensagens excedido")
    return ParsedMessageIds(message_ids=clean, invalid=invalid)


@dataclass(frozen=True, slots=True)
class ParsedReactionTarget:
    message_id: int | None = None
    user_id: int | None = None
    actor_chat_id: int | None = None
    error: str | None = None


def parse_reaction_target(text: str, *, selected_chat_id: int | None = None, require_message: bool) -> ParsedReactionTarget:
    """Lê alvo de remoção de reação.

    Para reação específica: ``message_id | user_id`` ou ``link | user_id``.
    Para remoção ampla: ``user_id`` ou ``chat:<actor_chat_id>``.
    """
    raw = str(text or "").strip()
    if not raw:
        return ParsedReactionTarget(error="entrada vazia")
    if require_message:
        if "|" not in raw:
            return ParsedReactionTarget(error="use message_id/link | user_id ou message_id/link | chat:<id>")
        left, right = [p.strip() for p in raw.rsplit("|", 1)]
        ref = parse_message_ref(left, selected_chat_id=selected_chat_id)
        if ref.message_id is None:
            return ParsedReactionTarget(error=ref.error or "message_id inválido")
        raw_target = right
        if raw_target.casefold().startswith("chat:"):
            value = raw_target.split(":", 1)[1].strip()
            if not value.lstrip("-").isdecimal():
                return ParsedReactionTarget(error="actor_chat_id inválido")
            return ParsedReactionTarget(message_id=ref.message_id, actor_chat_id=int(value))
        if not raw_target.isdecimal() or int(raw_target) <= 0:
            return ParsedReactionTarget(error="user_id inválido")
        return ParsedReactionTarget(message_id=ref.message_id, user_id=int(raw_target))
    if raw.casefold().startswith("chat:"):
        value = raw.split(":", 1)[1].strip()
        if not value.lstrip("-").isdecimal():
            return ParsedReactionTarget(error="actor_chat_id inválido")
        return ParsedReactionTarget(actor_chat_id=int(value))
    if not raw.isdecimal() or int(raw) <= 0:
        return ParsedReactionTarget(error="user_id inválido")
    return ParsedReactionTarget(user_id=int(raw))


@dataclass(frozen=True, slots=True)
class ParsedAdminRoleAction:
    user_id: int | None
    role: str | None = None
    custom_flags: dict[str, bool] | None = None
    error: str | None = None

_ADMIN_ROLE_ALIASES = {
    "leve": "limited",
    "limitado": "limited",
    "mod": "moderator",
    "moderador": "moderator",
    "admin": "admin",
    "completo": "full",
    "total": "full",
    "full": "full",
}
_ADMIN_FLAG_ALIASES = {
    "gerenciar": "can_manage_chat",
    "manage": "can_manage_chat",
    "delete": "can_delete_messages",
    "apagar": "can_delete_messages",
    "video": "can_manage_video_chats",
    "voz": "can_manage_video_chats",
    "restringir": "can_restrict_members",
    "restrict": "can_restrict_members",
    "promover": "can_promote_members",
    "promote": "can_promote_members",
    "info": "can_change_info",
    "alterar": "can_change_info",
    "convite": "can_invite_users",
    "invite": "can_invite_users",
    "fixar": "can_pin_messages",
    "pin": "can_pin_messages",
    "topicos": "can_manage_topics",
    "tópicos": "can_manage_topics",
    "topics": "can_manage_topics",
    "tags": "can_manage_tags",
    "stories": "can_post_stories",
    "story": "can_post_stories",
    "poststories": "can_post_stories",
    "editstories": "can_edit_stories",
    "deletestories": "can_delete_stories",
    "postmessages": "can_post_messages",
    "channelpost": "can_post_messages",
    "editmessages": "can_edit_messages",
    "channeledit": "can_edit_messages",
    "direct": "can_manage_direct_messages",
    "dm": "can_manage_direct_messages",
}


def parse_admin_role_action(text: str) -> ParsedAdminRoleAction:
    """Lê promoção: ``user_id | perfil`` ou ``user_id | flag,flag``.

    Perfis: leve, moderador, admin, total. Também aceita flags separadas por
    vírgula/espaço: delete, restrict, invite, pin, info, topics, tags,
    promote, stories, postmessages, editmessages, direct.
    """
    raw = str(text or "").strip()
    if not raw:
        return ParsedAdminRoleAction(user_id=None, error="entrada vazia")
    if "|" in raw:
        left, right = raw.split("|", 1)
        user_raw = left.strip()
        role_raw = right.strip()
    else:
        pieces = raw.split(maxsplit=1)
        user_raw = pieces[0].strip()
        role_raw = pieces[1].strip() if len(pieces) > 1 else "moderador"
    if not user_raw.isdecimal() or int(user_raw) <= 0:
        return ParsedAdminRoleAction(user_id=None, error="ID de usuário inválido")
    role_key = role_raw.casefold().strip()
    if not role_key:
        role_key = "moderador"
    normalized_role = _ADMIN_ROLE_ALIASES.get(role_key)
    if normalized_role:
        return ParsedAdminRoleAction(user_id=int(user_raw), role=normalized_role)
    flags: dict[str, bool] = {value: False for value in set(_ADMIN_FLAG_ALIASES.values())}
    unknown: list[str] = []
    for token in [t for t in re.split(r"[\s,;/]+", role_key) if t]:
        if token in {"sem", "no", "false", "0"}:
            continue
        name = _ADMIN_FLAG_ALIASES.get(token)
        if name is None:
            unknown.append(token)
        else:
            flags[name] = True
    if unknown:
        return ParsedAdminRoleAction(user_id=int(user_raw), error="perfil/flag desconhecido: " + ", ".join(unknown))
    return ParsedAdminRoleAction(user_id=int(user_raw), role="custom", custom_flags=flags)


@dataclass(frozen=True, slots=True)
class ParsedAdminTitleAction:
    user_id: int | None
    title: str | None = None
    error: str | None = None


def _contains_emoji_or_control(value: str) -> bool:
    for ch in value:
        code = ord(ch)
        if code < 32:
            return True
        # Bloqueio prático para faixas emoji comuns; o Telegram também valida.
        if code >= 0x1F000:
            return True
    return False


def parse_admin_title_action(text: str) -> ParsedAdminTitleAction:
    raw = str(text or "").strip()
    if "|" not in raw:
        return ParsedAdminTitleAction(user_id=None, error="use user_id | título")
    left, right = raw.split("|", 1)
    user_raw = left.strip()
    title = right.strip()
    if not user_raw.isdecimal() or int(user_raw) <= 0:
        return ParsedAdminTitleAction(user_id=None, error="ID de usuário inválido")
    if not 0 <= len(title) <= 16:
        return ParsedAdminTitleAction(user_id=int(user_raw), title=title, error="título precisa ter 0 a 16 caracteres")
    if _contains_emoji_or_control(title):
        return ParsedAdminTitleAction(user_id=int(user_raw), title=title, error="título não pode conter emoji ou controle")
    return ParsedAdminTitleAction(user_id=int(user_raw), title=title)


@dataclass(frozen=True, slots=True)
class ParsedSenderChatAction:
    sender_chat_id: int | None
    error: str | None = None


def parse_sender_chat_action(text: str) -> ParsedSenderChatAction:
    raw = str(text or "").strip()
    if not raw or not raw.lstrip("-").isdecimal():
        return ParsedSenderChatAction(sender_chat_id=None, error="sender_chat_id inválido")
    value = int(raw)
    if value == 0:
        return ParsedSenderChatAction(sender_chat_id=None, error="sender_chat_id inválido")
    return ParsedSenderChatAction(sender_chat_id=value)


@dataclass(frozen=True, slots=True)
class ParsedInviteCreateAction:
    name: str | None
    duration: timedelta | None
    duration_raw: str | None
    member_limit: int | None
    creates_join_request: bool
    error: str | None = None


def _parse_join_request_bool(raw: str) -> tuple[bool, str | None]:
    value = raw.casefold().strip()
    if value in {"1", "sim", "s", "true", "yes", "y", "request", "solicitacao", "solicitação", "aprovar", "join"}:
        return True, None
    if value in {"0", "nao", "não", "n", "false", "no", "normal", "direto"}:
        return False, None
    return False, "valor de solicitação inválido"


def parse_invite_create_action(text: str) -> ParsedInviteCreateAction:
    """Lê criação de link: ``nome | expiração | limite | solicitação``.

    Campos podem ser vazios. ``solicitação`` aceita sim/não/request/normal.
    Quando ``creates_join_request`` é true, o ``member_limit`` é removido por
    limitação da Bot API.
    """
    raw = str(text or "").strip()
    if not raw:
        raw = "Tigrão | permanente | 0 | não"
    parts = [p.strip() for p in raw.split("|")]
    while len(parts) < 4:
        parts.append("")
    if len(parts) > 4:
        return ParsedInviteCreateAction(None, None, None, None, False, error="use no máximo 4 campos")
    name = parts[0] or None
    if name is not None and not 0 <= len(name) <= 32:
        return ParsedInviteCreateAction(name, None, None, None, False, error="nome do link precisa ter 0 a 32 caracteres")
    duration_raw = parts[1] or "permanente"
    parsed_duration = parse_duration(duration_raw)
    if parsed_duration.error:
        return ParsedInviteCreateAction(name, None, duration_raw, None, False, error=parsed_duration.error)
    limit_raw = parts[2] or "0"
    try:
        member_limit = int(limit_raw)
    except ValueError:
        return ParsedInviteCreateAction(name, parsed_duration.duration, duration_raw, None, False, error="limite de membros inválido")
    if member_limit <= 0:
        member_limit = None
    elif not 1 <= member_limit <= 99999:
        return ParsedInviteCreateAction(name, parsed_duration.duration, duration_raw, member_limit, False, error="limite precisa ser 1 a 99999")
    creates_join_request, err = _parse_join_request_bool(parts[3] or "não")
    if err:
        return ParsedInviteCreateAction(name, parsed_duration.duration, duration_raw, member_limit, creates_join_request, error=err)
    if creates_join_request:
        member_limit = None
    return ParsedInviteCreateAction(name, parsed_duration.duration, duration_raw, member_limit, creates_join_request)


@dataclass(frozen=True, slots=True)
class ParsedInviteEditAction:
    invite_link: str | None
    create: ParsedInviteCreateAction | None = None
    error: str | None = None


def _looks_like_invite_link(value: str) -> bool:
    low = value.casefold()
    return low.startswith(("https://t.me/+", "http://t.me/+", "t.me/+", "https://t.me/joinchat/", "http://t.me/joinchat/", "t.me/joinchat/"))


def parse_invite_edit_action(text: str) -> ParsedInviteEditAction:
    raw = str(text or "").strip()
    if "|" not in raw:
        return ParsedInviteEditAction(invite_link=None, error="use link | nome | expiração | limite | solicitação")
    link, rest = raw.split("|", 1)
    link = link.strip()
    if not _looks_like_invite_link(link):
        return ParsedInviteEditAction(invite_link=link, error="link de convite inválido")
    create = parse_invite_create_action(rest)
    if create.error:
        return ParsedInviteEditAction(invite_link=link, create=create, error=create.error)
    return ParsedInviteEditAction(invite_link=link, create=create)


@dataclass(frozen=True, slots=True)
class ParsedInviteLinkRef:
    invite_link: str | None
    error: str | None = None


def parse_invite_link_ref(text: str) -> ParsedInviteLinkRef:
    link = str(text or "").strip()
    if not _looks_like_invite_link(link):
        return ParsedInviteLinkRef(invite_link=None, error="link de convite inválido")
    return ParsedInviteLinkRef(invite_link=link)

@dataclass(frozen=True, slots=True)
class ParsedUserTextAction:
    user_id: int | None
    text: str | None = None
    error: str | None = None


def parse_user_text_action(text: str, *, max_text_len: int, allow_empty_text: bool = False, label: str = "texto") -> ParsedUserTextAction:
    raw = str(text or "").strip()
    if "|" not in raw:
        return ParsedUserTextAction(user_id=None, error=f"use user_id | {label}")
    left, right = raw.split("|", 1)
    user_raw = left.strip()
    value = right.strip()
    if not user_raw.isdecimal() or int(user_raw) <= 0:
        return ParsedUserTextAction(user_id=None, error="ID de usuário inválido")
    if not allow_empty_text and not value:
        return ParsedUserTextAction(user_id=int(user_raw), text=value, error=f"{label} vazio")
    if len(value) > max_text_len:
        return ParsedUserTextAction(user_id=int(user_raw), text=value, error=f"{label} precisa ter no máximo {max_text_len} caracteres")
    if _contains_emoji_or_control(value):
        return ParsedUserTextAction(user_id=int(user_raw), text=value, error=f"{label} não pode conter emoji ou controle")
    return ParsedUserTextAction(user_id=int(user_raw), text=value)


@dataclass(frozen=True, slots=True)
class ParsedTopicCreateAction:
    name: str | None
    icon_color: int | None = None
    error: str | None = None

_TOPIC_COLORS = {7322096, 16766590, 13338331, 9367192, 16749490, 16478047}


def _parse_topic_color(raw: str) -> tuple[int | None, str | None]:
    clean = raw.strip()
    if not clean:
        return None, None
    if clean.startswith("#"):
        try:
            value = int(clean[1:], 16)
        except ValueError:
            return None, "cor inválida"
    else:
        try:
            value = int(clean, 0)
        except ValueError:
            return None, "cor inválida"
    if value not in _TOPIC_COLORS:
        return None, "cor de tópico fora da lista permitida pela Bot API"
    return value, None


def parse_topic_create_action(text: str) -> ParsedTopicCreateAction:
    raw = str(text or "").strip()
    if not raw:
        return ParsedTopicCreateAction(name=None, error="nome vazio")
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) > 2:
        return ParsedTopicCreateAction(name=None, error="use nome | cor opcional")
    name = parts[0]
    if not 1 <= len(name) <= 128:
        return ParsedTopicCreateAction(name=name, error="nome precisa ter 1 a 128 caracteres")
    color, err = _parse_topic_color(parts[1] if len(parts) == 2 else "")
    if err:
        return ParsedTopicCreateAction(name=name, error=err)
    return ParsedTopicCreateAction(name=name, icon_color=color)


@dataclass(frozen=True, slots=True)
class ParsedTopicEditAction:
    message_thread_id: int | None
    name: str | None = None
    icon_color: int | None = None
    error: str | None = None


def parse_topic_edit_action(text: str) -> ParsedTopicEditAction:
    raw = str(text or "").strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 2 or len(parts) > 3:
        return ParsedTopicEditAction(message_thread_id=None, error="use thread_id | nome | cor opcional")
    if not parts[0].isdecimal() or int(parts[0]) <= 0:
        return ParsedTopicEditAction(message_thread_id=None, error="thread_id inválido")
    name = parts[1]
    if not 0 <= len(name) <= 128:
        return ParsedTopicEditAction(message_thread_id=int(parts[0]), name=name, error="nome precisa ter 0 a 128 caracteres")
    color, err = _parse_topic_color(parts[2] if len(parts) == 3 else "")
    if err:
        return ParsedTopicEditAction(message_thread_id=int(parts[0]), name=name, error=err)
    return ParsedTopicEditAction(message_thread_id=int(parts[0]), name=name, icon_color=color)


def parse_thread_id(text: str) -> tuple[int | None, str | None]:
    raw = str(text or "").strip()
    if not raw.isdecimal() or int(raw) <= 0:
        return None, "thread_id inválido"
    return int(raw), None


@dataclass(frozen=True, slots=True)
class ParsedProtectionSetting:
    enabled: bool
    config: dict[str, int | bool | str]
    error: str | None = None


def _onoff(raw: str) -> tuple[bool | None, str | None]:
    value = raw.casefold().strip()
    if value in {"on", "sim", "s", "1", "true", "ativar", "ativo"}:
        return True, None
    if value in {"off", "não", "nao", "n", "0", "false", "desativar", "inativo"}:
        return False, None
    return None, "primeiro campo precisa ser on/off"


def parse_antiflood_setting(text: str) -> ParsedProtectionSetting:
    parts = [p.strip() for p in str(text or "").split("|")]
    while len(parts) < 4:
        parts.append("")
    enabled, err = _onoff(parts[0] or "on")
    if err:
        return ParsedProtectionSetting(False, {}, err)
    try:
        limit = int(parts[1] or 5)
    except ValueError:
        return ParsedProtectionSetting(bool(enabled), {}, "limite inválido")
    window = parse_duration(parts[2] or "10s")
    mute = parse_duration(parts[3] or "10m")
    if window.error or window.duration is None:
        return ParsedProtectionSetting(bool(enabled), {}, window.error or "janela inválida")
    if mute.error or mute.duration is None:
        return ParsedProtectionSetting(bool(enabled), {}, mute.error or "mute inválido")
    if not 2 <= limit <= 100:
        return ParsedProtectionSetting(bool(enabled), {}, "limite precisa estar entre 2 e 100")
    return ParsedProtectionSetting(bool(enabled), {"limit": limit, "window_seconds": int(window.duration.total_seconds()), "mute_seconds": int(mute.duration.total_seconds()), "delete": True})


def parse_antiraid_setting(text: str) -> ParsedProtectionSetting:
    parts = [p.strip() for p in str(text or "").split("|")]
    while len(parts) < 4:
        parts.append("")
    enabled, err = _onoff(parts[0] or "on")
    if err:
        return ParsedProtectionSetting(False, {}, err)
    try:
        limit = int(parts[1] or 5)
    except ValueError:
        return ParsedProtectionSetting(bool(enabled), {}, "limite inválido")
    window = parse_duration(parts[2] or "1m")
    action = (parts[3] or "queue").casefold()
    if window.error or window.duration is None:
        return ParsedProtectionSetting(bool(enabled), {}, window.error or "janela inválida")
    if action not in {"queue", "decline", "lock"}:
        return ParsedProtectionSetting(bool(enabled), {}, "ação precisa ser queue, decline ou lock")
    return ParsedProtectionSetting(bool(enabled), {"limit": limit, "window_seconds": int(window.duration.total_seconds()), "action": action})


def parse_captcha_setting(text: str) -> ParsedProtectionSetting:
    parts = [p.strip() for p in str(text or "").split("|")]
    while len(parts) < 3:
        parts.append("")
    enabled, err = _onoff(parts[0] or "on")
    if err:
        return ParsedProtectionSetting(False, {}, err)
    ttl = parse_duration(parts[1] or "5m")
    if ttl.error or ttl.duration is None:
        return ParsedProtectionSetting(bool(enabled), {}, ttl.error or "ttl inválido")
    try:
        attempts = int(parts[2] or 3)
    except ValueError:
        return ParsedProtectionSetting(bool(enabled), {}, "tentativas inválidas")
    if not 1 <= attempts <= 10:
        return ParsedProtectionSetting(bool(enabled), {}, "tentativas precisam estar entre 1 e 10")
    return ParsedProtectionSetting(bool(enabled), {"ttl_seconds": int(ttl.duration.total_seconds()), "max_attempts": attempts})

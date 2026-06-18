from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]


def _env(name: str, default: str = "", *, legacy: Iterable[str] = ()) -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    for old_name in legacy:
        value = os.getenv(old_name)
        if value is not None:
            return value
    return default


def _bool_env(name: str, default: bool, *, legacy: Iterable[str] = ()) -> bool:
    raw = _env(name, "", legacy=legacy).strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on", "sim"}:
        return True
    if raw in {"0", "false", "no", "off", "nao", "não"}:
        return False
    logger.warning("CONFIG_VALUE_IGNORED name=%s expected=bool", name)
    return default


def _int_set_env(name: str, *, legacy: Iterable[str] = ()) -> frozenset[int]:
    values: set[int] = set()
    raw_values: list[str] = []
    primary = os.getenv(name)
    if primary is not None:
        raw_values.append(primary)
    for old_name in legacy:
        value = os.getenv(old_name)
        if value is not None:
            raw_values.append(value)
    for raw in raw_values:
        for part in str(raw).replace(";", ",").split(","):
            item = part.strip()
            if not item:
                continue
            try:
                values.add(int(item))
            except ValueError:
                logger.warning("CONFIG_VALUE_IGNORED name=%s expected=int_list", name)
    return frozenset(values)


def _normalize_public_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value}"


def _resolve_base_url() -> str:
    configured = _env("BASE_URL", legacy=("TR3_BASE_URL",))
    if configured.strip():
        return _normalize_public_url(configured)

    # Railway expõe o domínio público quando o serviço possui domínio gerado
    # ou custom domain. Aceitamos as duas formas mais comuns para reduzir a
    # configuração manual no primeiro deploy.
    for railway_name in ("RAILWAY_PUBLIC_DOMAIN", "RAILWAY_STATIC_URL"):
        value = os.getenv(railway_name, "")
        if value.strip():
            return _normalize_public_url(value)
    return ""


def _resolve_data_dir() -> Path:
    candidates: list[Path] = []
    for name in ("DATA_DIR", "RAILWAY_VOLUME_MOUNT_PATH"):
        raw = os.getenv(name, "").strip()
        if raw:
            candidates.append(Path(raw))
    candidates.extend([Path("/data"), BASE_DIR / ".data", Path.cwd() / ".data", Path.home() / ".tigrao-moderador-data"])
    seen: set[str] = set()
    last_error: str | None = None
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("DATA_DIR_UNAVAILABLE path=%s error=%s", candidate, last_error)
    raise RuntimeError(f"Nenhum DATA_DIR gravável foi encontrado. last_error={last_error}")


TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN", legacy=("TR3_TELEGRAM_BOT_TOKEN",))
BASE_URL = _resolve_base_url()
WEBHOOK_SECRET = _env("WEBHOOK_SECRET", legacy=("TR3_WEBHOOK_SECRET",)).strip()
WEBHOOK_PATH = _env("WEBHOOK_PATH", "/telegram/webhook").strip() or "/telegram/webhook"
RUN_POLLING = _bool_env("RUN_POLLING", False)
SET_WEBHOOK_ON_STARTUP = _bool_env("SET_WEBHOOK_ON_STARTUP", bool(BASE_URL and not RUN_POLLING))

DATA_DIR = _resolve_data_dir()
DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{DATA_DIR / 'moderador.sqlite3'}")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# Superfície do moderador: as funções reais do pacote ficam ativas por padrão.
# A única configuração de acesso ao painel é TIGRAO_BOT_ACCESS_USER_IDS.
# Variáveis antigas são aceitas como aliases para não quebrar deploys anteriores.
TIGRAO_BOT_ACCESS_USER_IDS = _int_set_env(
    "TIGRAO_BOT_ACCESS_USER_IDS",
    legacy=(
        "CODE_OWNER_IDS",
        "OWNER_IDS",
        "TR3_CODE_OWNER_IDS",
        "TIGRAO_FSM_MODERATOR_IDS",
        "MODERATOR_IDS",
        "TR3_TIGRAO_FSM_MODERATOR_IDS",
    ),
)

# Alias de compatibilidade para código/deploy antigo; a configuração nova é
# TIGRAO_BOT_ACCESS_USER_IDS.
CODE_OWNER_IDS = TIGRAO_BOT_ACCESS_USER_IDS

ALLOWED_UPDATES = [
    # Mensagens e edições em grupos/supergrupos.
    "message",
    "edited_message",
    # Canais ficam inscritos para futura expansão sem alterar deploy.
    "channel_post",
    "edited_channel_post",
    # Painel, inline X9 e fluxos de aprovação.
    "callback_query",
    "inline_query",
    "chosen_inline_result",
    "chat_join_request",
    "my_chat_member",
    "chat_member",
    # Reações exigem inscrição explícita na Bot API.
    "message_reaction",
    "message_reaction_count",
    # Auditoria útil de boosts quando o bot é administrador.
    "chat_boost",
    "removed_chat_boost",
]

def _resolve_join_request_webapp_url() -> str:
    configured = _env("TIGRAO_JOIN_REQUEST_WEBAPP_URL", "").strip()
    if configured:
        return _normalize_public_url(configured)
    if BASE_URL:
        return f"{BASE_URL}/join-request"
    return ""


# Mini App para Join Request Queries (Bot API 10.1).
# Se não for configurado manualmente, usa automaticamente BASE_URL + /join-request.
TIGRAO_JOIN_REQUEST_WEBAPP_URL = _resolve_join_request_webapp_url()

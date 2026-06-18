"""Validação de dados assinados de Telegram Mini Apps."""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qsl


class TelegramWebAppAuthError(ValueError):
    """Init data ausente, expirado ou com assinatura inválida."""


def validate_init_data(init_data: str, bot_token: str, *, max_age_seconds: int = 86400) -> dict[str, str]:
    """Valida Telegram.WebApp.initData usando o token do bot.

    Retorna os pares decodificados quando a assinatura confere. Não interpreta
    JSON interno; mantém strings para evitar aceitar campos parcialmente válidos.
    """
    raw = str(init_data or "").strip()
    token = str(bot_token or "").strip()
    if not raw:
        raise TelegramWebAppAuthError("initData ausente")
    if not token:
        raise TelegramWebAppAuthError("token ausente")
    pairs = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=False))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise TelegramWebAppAuthError("hash ausente")
    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramWebAppAuthError("assinatura inválida")
    auth_date_raw = pairs.get("auth_date")
    if auth_date_raw:
        try:
            auth_date = int(auth_date_raw)
        except ValueError as exc:
            raise TelegramWebAppAuthError("auth_date inválido") from exc
        if max_age_seconds > 0 and int(time.time()) - auth_date > max_age_seconds:
            raise TelegramWebAppAuthError("initData expirado")
    return pairs

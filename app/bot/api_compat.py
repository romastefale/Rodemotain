"""Compatibilidade direta com métodos novos da Telegram Bot API.

Mantém o projeto em aiogram 3.28 mesmo quando a biblioteca ainda não expõe
wrappers para métodos recém-adicionados na Bot API. Sempre prefere o método do
objeto Bot quando existir; caso contrário, chama a Bot API por HTTPS.
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any, Mapping


class TelegramBotApiCompatError(RuntimeError):
    """Erro sanitizado em chamada direta à Telegram Bot API."""


def _token_from_bot(bot: Any) -> str:
    token = getattr(bot, "token", None)
    if token:
        return str(token)
    try:
        from app.config.settings import TELEGRAM_BOT_TOKEN
    except Exception:  # pragma: no cover - fallback defensivo
        TELEGRAM_BOT_TOKEN = ""
    token = str(TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        raise TelegramBotApiCompatError("Token do bot ausente para chamada direta à Bot API.")
    return token


def _post_json_sync(token: str, method_name: str, payload: Mapping[str, Any], *, timeout: float = 10.0) -> Any:
    url = f"https://api.telegram.org/bot{token}/{method_name}"
    body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")[:500]
        raise TelegramBotApiCompatError(f"Bot API HTTP {exc.code}: {raw_error}") from exc
    except Exception as exc:
        raise TelegramBotApiCompatError(f"Falha em chamada HTTPS direta à Bot API: {type(exc).__name__}: {exc}") from exc
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise TelegramBotApiCompatError("Bot API retornou JSON inválido.") from exc
    if not data.get("ok"):
        description = str(data.get("description") or "erro sem descrição")[:500]
        error_code = data.get("error_code")
        raise TelegramBotApiCompatError(f"Bot API recusou {method_name}: {error_code} {description}")
    return data.get("result")


async def _call_bot_api_compat(bot: Any, *, aiogram_method_name: str, bot_api_method_name: str, payload: Mapping[str, Any]) -> Any:
    """Chama método novo pela camada do aiogram quando existir; senão usa HTTPS.

    Essa estratégia evita quebrar quando uma versão fixa do aiogram ainda não
    expõe um método recém-lançado pela Bot API.
    """
    method = getattr(bot, aiogram_method_name, None)
    if callable(method):
        return await method(**dict(payload))
    token = _token_from_bot(bot)
    return await asyncio.to_thread(_post_json_sync, token, bot_api_method_name, dict(payload))


async def send_chat_join_request_web_app_compat(bot: Any, *, chat_join_request_query_id: str, web_app_url: str) -> Any:
    return await _call_bot_api_compat(
        bot,
        aiogram_method_name="send_chat_join_request_web_app",
        bot_api_method_name="sendChatJoinRequestWebApp",
        payload={"chat_join_request_query_id": chat_join_request_query_id, "web_app_url": web_app_url},
    )


async def answer_chat_join_request_query_compat(bot: Any, *, chat_join_request_query_id: str, result: str) -> Any:
    return await _call_bot_api_compat(
        bot,
        aiogram_method_name="answer_chat_join_request_query",
        bot_api_method_name="answerChatJoinRequestQuery",
        payload={"chat_join_request_query_id": chat_join_request_query_id, "result": result},
    )

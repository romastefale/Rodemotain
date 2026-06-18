from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, Update

from app.bot.group_registry import remember_chat_from_update
from app.bot.api_compat import answer_chat_join_request_query_compat
from app.config.settings import (
    ALLOWED_UPDATES,
    BASE_URL,
    SET_WEBHOOK_ON_STARTUP,
    TELEGRAM_BOT_TOKEN,
    WEBHOOK_PATH,
    WEBHOOK_SECRET,
)
from app.plugins.tigrao_fsm import build_tigrao_fsm_plugin
from app.plugins.tigrao_fsm.storage import ensure_tables as ensure_tigrao_tables

logger = logging.getLogger(__name__)
app = FastAPI(title="Tigrão Moderador", version="1.0.0")

bot: Bot | None = None
dispatcher: Dispatcher | None = None
tigrao_plugin = None


def _extract_user_id(update: Update) -> int | None:
    for attr in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
        "chat_join_request",
        "my_chat_member",
        "chat_member",
        "message_reaction",
        "message_reaction_count",
        "chat_boost",
        "removed_chat_boost",
    ):
        obj = getattr(update, attr, None)
        if obj is None:
            continue
        user = getattr(obj, "from_user", None) or getattr(obj, "user", None)
        if user is not None and getattr(user, "id", None) is not None:
            return int(user.id)
    return None




async def _set_bot_commands_safe(bot_obj: Bot) -> None:
    """Registra comandos visíveis no menu do Telegram sem impedir startup."""
    commands = [
        BotCommand(command="start", description="tutorial rápido do moderador"),
        BotCommand(command="help", description="lista comandos e recursos"),
        BotCommand(command="tigrao", description="abrir painel de moderação"),
        BotCommand(command="captcha", description="responder captcha de entrada"),
    ]
    try:
        await bot_obj.set_my_commands(commands)
        logger.info("telegram_commands_set count=%s", len(commands))
    except Exception:
        logger.exception("telegram_commands_set_failed")

@app.get("/healthz", status_code=200)
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    return {
        "status": "ready" if bot is not None and dispatcher is not None else "starting",
        "bot_configured": bool(TELEGRAM_BOT_TOKEN),
        "moderator_active": True,
    }




@app.post("/telegram/join-request-query")
async def telegram_join_request_query(request: Request) -> Response:
    """Resolve Join Request Query enviado por Mini App externo.

    Segurança: exige WEBHOOK_SECRET no corpo quando WEBHOOK_SECRET estiver definido.
    Corpo esperado: {"secret": "...", "query_id": "...", "result": "approve|decline|queue"}.
    """
    if bot is None:
        return Response(status_code=503)
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=400)
    if WEBHOOK_SECRET and str(data.get("secret") or "") != WEBHOOK_SECRET:
        return Response(status_code=403)
    query_id = str(data.get("query_id") or data.get("chat_join_request_query_id") or "").strip()
    result = str(data.get("result") or "").strip().lower()
    if not query_id or result not in {"approve", "decline", "queue"}:
        return Response(status_code=400)
    await answer_chat_join_request_query_compat(bot, chat_join_request_query_id=query_id, result=result)
    return Response(status_code=200)


@app.on_event("startup")
async def on_startup() -> None:
    global bot, dispatcher, tigrao_plugin
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN ausente; /healthz permanece ativo, mas o bot não processará updates.")
        return
    ensure_tigrao_tables()
    bot = Bot(TELEGRAM_BOT_TOKEN)
    dispatcher = Dispatcher()
    tigrao_plugin = build_tigrao_fsm_plugin(dispatcher=dispatcher)
    await _set_bot_commands_safe(bot)
    if SET_WEBHOOK_ON_STARTUP and BASE_URL:
        webhook_url = f"{BASE_URL}{WEBHOOK_PATH}"
        await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET or None, allowed_updates=ALLOWED_UPDATES)
        logger.info("telegram_webhook_set url=%s", webhook_url)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if bot is not None:
        await bot.session.close()


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> Response:
    if WEBHOOK_SECRET:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header != WEBHOOK_SECRET:
            return Response(status_code=403)
    if bot is None or dispatcher is None:
        return Response(status_code=503)
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    remember_chat_from_update(update)
    consumed = False
    if tigrao_plugin is not None:
        try:
            tigrao_plugin.set_current_user(_extract_user_id(update))
            consumed = await tigrao_plugin.before_dispatch(bot, update)
        except Exception:
            logger.exception("tigrao_before_dispatch_failed")
    if not consumed:
        await dispatcher.feed_update(bot, update)
    return Response(status_code=200)


async def start_polling() -> None:
    if bot is None or dispatcher is None:
        raise RuntimeError("Bot não configurado. Defina TELEGRAM_BOT_TOKEN.")
    await bot.delete_webhook(drop_pending_updates=False)
    await dispatcher.start_polling(bot, allowed_updates=ALLOWED_UPDATES)

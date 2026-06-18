from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, Update

from app.bot.group_registry import list_groups, remember_chat_from_update
from app.bot.api_compat import answer_chat_join_request_query_compat
from app.bot.bot_profile_icon import (
    fallback_bot_icon_svg,
    get_or_refresh_bot_profile_icon,
    media_type_for_icon,
)
from app.bot.telegram_webapp import TelegramWebAppAuthError, validate_init_data
from app.config.settings import (
    ALLOWED_UPDATES,
    BASE_DIR,
    BASE_URL,
    DATA_DIR,
    SET_WEBHOOK_ON_STARTUP,
    TELEGRAM_BOT_TOKEN,
    WEBHOOK_PATH,
    WEBHOOK_SECRET,
)
from app.plugins.tigrao_fsm import build_tigrao_fsm_plugin
from app.plugins.tigrao_fsm import storage as tigrao_storage
from app.plugins.tigrao_fsm.storage import ensure_tables as ensure_tigrao_tables

logger = logging.getLogger(__name__)
app = FastAPI(title="Rodemotain", version="1.0.0")
STATIC_DIR = BASE_DIR / "app" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
        "inline_query",
        "chosen_inline_result",
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






@app.get("/telegram/bot-icon")
async def telegram_bot_icon() -> Response:
    """Serve a foto de perfil pública do bot para o Mini App.

    A rota usa cache local para não consultar a Bot API a cada abertura. Se o
    token estiver ausente, o bot ainda não estiver configurado ou o Telegram não
    retornar foto de perfil, a interface recebe um SVG simples com a inicial R.
    """
    if TELEGRAM_BOT_TOKEN:
        icon_path = await asyncio.to_thread(get_or_refresh_bot_profile_icon, TELEGRAM_BOT_TOKEN, DATA_DIR)
        if icon_path is not None and icon_path.exists():
            return FileResponse(icon_path, media_type=media_type_for_icon(icon_path))
    return Response(content=fallback_bot_icon_svg(), media_type="image/svg+xml")


@app.get("/join-request")
def join_request_app() -> FileResponse:
    """Tela Telegram Mini App para solicitação de entrada com seleção de grupo."""
    return FileResponse(STATIC_DIR / "join-request.html", media_type="text/html; charset=utf-8")


def _has_valid_join_request_auth(data: dict[str, Any]) -> tuple[bool, str | None]:
    """Aceita secret interno ou initData assinado pelo Telegram Mini App."""
    if WEBHOOK_SECRET and str(data.get("secret") or "") == WEBHOOK_SECRET:
        return True, "secret"
    init_data = str(data.get("init_data") or data.get("initData") or "").strip()
    if init_data:
        try:
            validate_init_data(init_data, TELEGRAM_BOT_TOKEN)
            return True, "telegram_init_data"
        except TelegramWebAppAuthError as exc:
            return False, f"initData inválido: {exc}"
    if WEBHOOK_SECRET:
        return False, "secret ou initData obrigatório"
    return True, "dev_no_secret"


@app.post("/telegram/join-request/groups")
async def telegram_join_request_groups(request: Request) -> JSONResponse:
    """Lista grupos conhecidos para a tela de entrada.

    A lista só é entregue para chamada interna com WEBHOOK_SECRET ou para Mini
    App com initData válido. Isso evita expor grupos privados por endpoint cru.
    """
    try:
        data = await request.json()
    except Exception:
        data = {}
    ok, reason = _has_valid_join_request_auth(data)
    if not ok:
        return JSONResponse({"ok": False, "error": reason}, status_code=403)
    groups = []
    for item in list_groups(limit=100):
        title = str(item.get("title") or item.get("username") or item.get("chat_id"))
        username = item.get("username")
        link = f"https://t.me/{username}" if username else None
        groups.append({
            "chat_id": int(item["chat_id"]),
            "title": title,
            "username": username,
            "chat_type": item.get("chat_type"),
            "last_seen": item.get("last_seen"),
            "public_link": link,
        })
    return JSONResponse({"ok": True, "groups": groups})

@app.post("/telegram/join-request-query")
async def telegram_join_request_query(request: Request) -> Response:
    """Resolve Join Request Query enviado por Mini App externo.

    Segurança: exige WEBHOOK_SECRET no corpo quando WEBHOOK_SECRET estiver definido.
    Corpo esperado: {"secret": "...", "query_id": "...", "result": "approve|decline|queue"}.
    """
    if bot is None:
        return JSONResponse({"ok": False, "error": "bot indisponível"}, status_code=503)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "JSON inválido"}, status_code=400)
    ok, reason = _has_valid_join_request_auth(data)
    if not ok:
        return JSONResponse({"ok": False, "error": reason}, status_code=403)
    query_id = str(data.get("query_id") or data.get("chat_join_request_query_id") or "").strip()
    result = str(data.get("result") or "").strip().lower()
    selected_chat_id_raw = data.get("selected_chat_id") or data.get("chat_id")
    selected_chat_id: int | None = None
    if selected_chat_id_raw not in (None, ""):
        try:
            selected_chat_id = int(selected_chat_id_raw)
        except Exception:
            return JSONResponse({"ok": False, "error": "selected_chat_id inválido"}, status_code=400)
    if not query_id or result not in {"approve", "decline", "queue"}:
        return JSONResponse({"ok": False, "error": "query_id e result=approve|decline|queue são obrigatórios"}, status_code=400)
    record = tigrao_storage.find_pending_join_request_by_query_id(query_id=query_id)
    if record is not None and selected_chat_id is not None and int(record.chat_id) != int(selected_chat_id):
        tigrao_storage.log_event(
            action="join_request_webapp_group_mismatch",
            result="bloqueado",
            detection="mini_app",
            surface="join_request_webapp",
            chat_id=record.chat_id,
            chat_title=record.chat_title,
            target_user_id=record.user_id,
            target_username=record.username,
            target_full_name=record.full_name,
            details="Mini App tentou resolver solicitação com grupo diferente do query_id.",
            metadata={"query_id": query_id, "selected_chat_id": selected_chat_id, "auth": reason},
        )
        return JSONResponse({"ok": False, "error": "Grupo selecionado não corresponde à solicitação de entrada."}, status_code=409)
    await answer_chat_join_request_query_compat(bot, chat_join_request_query_id=query_id, result=result)
    if record is not None and result in {"approve", "decline"}:
        record.status = tigrao_storage.APPROVED if result == "approve" else tigrao_storage.DECLINED
        record.processed_at = tigrao_storage.utcnow()
        record.result_detail = f"Resolvido pelo Mini App: {result}."
        tigrao_storage.update_join_request_status(record)
    if record is not None:
        tigrao_storage.log_event(
            action="join_request_webapp_resolved",
            result=result,
            detection="mini_app",
            surface="join_request_webapp",
            chat_id=record.chat_id,
            chat_title=record.chat_title,
            target_user_id=record.user_id,
            target_username=record.username,
            target_full_name=record.full_name,
            details=f"Solicitação resolvida pelo Mini App com resultado {result}.",
            metadata={"query_id": query_id, "selected_chat_id": selected_chat_id, "auth": reason},
        )
    return JSONResponse({"ok": True, "result": result})


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

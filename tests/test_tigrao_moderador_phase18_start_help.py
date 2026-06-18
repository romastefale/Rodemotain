from __future__ import annotations

from types import SimpleNamespace

import pytest


OWNER_ID = 111
OTHER_ID = 222


def _install_aiogram_stub(monkeypatch):
    import sys
    import types

    class FakeFilter:
        pass

    class FakeRouter:
        def __init__(self, *args, **kwargs):
            pass

        def message(self, *args, **kwargs):
            return lambda fn: fn

        def chat_join_request(self, *args, **kwargs):
            return lambda fn: fn

        def callback_query(self, *args, **kwargs):
            return lambda fn: fn

    class FakeFNode:
        def __getattr__(self, name):
            return self

        def startswith(self, *args, **kwargs):
            return self

    class FakeBot:
        pass

    class FakeDispatcher:
        pass

    class FakeBotCommand:
        def __init__(self, command: str, description: str):
            self.command = command
            self.description = description

    aiogram_mod = types.ModuleType("aiogram")
    aiogram_mod.F = FakeFNode()
    aiogram_mod.Router = FakeRouter
    aiogram_mod.Bot = FakeBot
    aiogram_mod.Dispatcher = FakeDispatcher
    filters_mod = types.ModuleType("aiogram.filters")
    filters_mod.Command = lambda *args, **kwargs: object()
    filters_mod.Filter = FakeFilter
    types_mod = types.ModuleType("aiogram.types")
    types_mod.BotCommand = FakeBotCommand
    types_mod.BufferedInputFile = object
    types_mod.CallbackQuery = object
    types_mod.Message = object
    types_mod.Update = object

    monkeypatch.setitem(sys.modules, "aiogram", aiogram_mod)
    monkeypatch.setitem(sys.modules, "aiogram.filters", filters_mod)
    monkeypatch.setitem(sys.modules, "aiogram.types", types_mod)


def import_panel(monkeypatch):
    import importlib
    import sys

    _install_aiogram_stub(monkeypatch)
    sys.modules.pop("app.plugins.tigrao_fsm.routers.panel", None)
    return importlib.import_module("app.plugins.tigrao_fsm.routers.panel")


class FakeMessage:
    def __init__(self, user_id: int, text: str = "/start") -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(type="private")
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_start_replies_authorized_user(monkeypatch):
    panel = import_panel(monkeypatch)
    monkeypatch.setattr(panel, "TIGRAO_BOT_ACCESS_USER_IDS", frozenset({OWNER_ID}))
    msg = FakeMessage(OWNER_ID, "/start")

    await panel.tigrao_start(msg)

    assert len(msg.answers) == 1
    assert "Bot online" in msg.answers[0][0]
    assert "/tigrao" in msg.answers[0][0]
    assert "Ações sensíveis exigem Confirmar" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_start_replies_unauthorized_user_without_panel_access(monkeypatch):
    panel = import_panel(monkeypatch)
    monkeypatch.setattr(panel, "TIGRAO_BOT_ACCESS_USER_IDS", frozenset({OWNER_ID}))
    msg = FakeMessage(OTHER_ID, "/start")

    await panel.tigrao_start(msg)

    assert len(msg.answers) == 1
    assert "bot é privado" in msg.answers[0][0]
    assert "TIGRAO_BOT_ACCESS_USER_IDS" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_help_lists_available_commands_for_authorized_user(monkeypatch):
    panel = import_panel(monkeypatch)
    monkeypatch.setattr(panel, "TIGRAO_BOT_ACCESS_USER_IDS", frozenset({OWNER_ID}))
    msg = FakeMessage(OWNER_ID, "/help")

    await panel.tigrao_help(msg)

    body = msg.answers[0][0]
    assert "/start" in body
    assert "/help" in body
    assert "/tigrao" in body
    assert "/captcha código" in body
    assert "promover/rebaixar administradores" in body
    assert "anti-raid" in body
    assert "logs" in body


@pytest.mark.asyncio
async def test_start_help_commands_are_registered_in_telegram_menu(monkeypatch):
    import importlib
    import sys

    _install_aiogram_stub(monkeypatch)
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")

    class FakeCommandBot:
        def __init__(self):
            self.commands = None

        async def set_my_commands(self, commands):
            self.commands = commands

    bot = FakeCommandBot()
    await main._set_bot_commands_safe(bot)

    commands = [cmd.command for cmd in bot.commands]
    assert commands == ["start", "help", "tigrao", "captcha"]

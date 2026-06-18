from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.plugins.tigrao_fsm.keyboards import confirm_cancel_keyboard, post_action_keyboard

OWNER_ID = 111
CHAT_ID = -1001234567890


def import_panel(monkeypatch):
    import importlib
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

    aiogram_mod = types.ModuleType("aiogram")
    aiogram_mod.F = FakeFNode()
    aiogram_mod.Router = FakeRouter
    filters_mod = types.ModuleType("aiogram.filters")
    filters_mod.Command = lambda *args, **kwargs: object()
    filters_mod.Filter = FakeFilter
    types_mod = types.ModuleType("aiogram.types")
    types_mod.CallbackQuery = object
    types_mod.Message = object
    types_mod.BufferedInputFile = object

    monkeypatch.setitem(sys.modules, "aiogram", aiogram_mod)
    monkeypatch.setitem(sys.modules, "aiogram.filters", filters_mod)
    monkeypatch.setitem(sys.modules, "aiogram.types", types_mod)
    sys.modules.pop("app.plugins.tigrao_fsm.routers.panel", None)
    return importlib.import_module("app.plugins.tigrao_fsm.routers.panel")


class FakeCallbackMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=555)
        self.message_id = 777
        self.edits: list[tuple[str, object]] = []

    async def edit_text(self, text, reply_markup=None):
        self.edits.append((text, reply_markup))


class FakeCallback:
    def __init__(self, session_id: str, action: str) -> None:
        self.data = f"tgf:{session_id}:{action}"
        self.from_user = SimpleNamespace(id=OWNER_ID)
        self.message = FakeCallbackMessage()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class FakeDmMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=OWNER_ID)
        self.chat = SimpleNamespace(id=999, type="private")
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))
        return SimpleNamespace(chat=self.chat, message_id=1234)


class FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.calls: list[tuple[str, dict]] = []

    async def delete_message(self, chat_id: int, message_id: int):
        self.deleted.append((chat_id, message_id))

    async def get_me(self):
        return SimpleNamespace(id=999)

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status="administrator" if user_id == 999 else "member", can_restrict_members=True, can_delete_messages=True, can_change_info=True, can_invite_users=True, can_pin_messages=True, can_manage_topics=True, can_promote_members=True)

    async def restrict_chat_member(self, **kwargs):
        self.calls.append(("restrict_chat_member", kwargs))


@pytest.fixture()
def selected_session():
    from app.plugins.tigrao_fsm.state import close_session, create_session

    session = create_session(owner_user_id=OWNER_ID, moderator_user_id=OWNER_ID)
    session.selected_chat_id = CHAT_ID
    session.selected_group_title = "Grupo Teste"
    try:
        yield session
    finally:
        close_session(session.session_id)


def test_confirm_keyboard_offers_panel_and_close():
    labels = [btn.text for row in confirm_cancel_keyboard("abc123") for btn in row]
    assert "✅ Confirmar" in labels
    assert "↩️ Cancelar" in labels
    assert "⬅️ Painel principal" in labels
    assert "✖️ Fechar" in labels


def test_post_action_keyboard_has_only_panel_or_close():
    labels = [btn.text for row in post_action_keyboard("abc123") for btn in row]
    assert labels == ["⬅️ Painel principal", "✖️ Fechar"]


@pytest.mark.asyncio
async def test_text_flow_deletes_previous_prompt_and_sends_new_confirmation(monkeypatch, selected_session):
    panel = import_panel(monkeypatch)
    bot = FakeBot()
    selected_session.selected_action = "mutetime"
    selected_session.waiting_for = "advanced_text"
    selected_session.payload["flow_prompt_chat_id"] = 555
    selected_session.payload["flow_prompt_message_id"] = 777

    msg = FakeDmMessage("222 | 30m")
    await panel._handle_advanced_text(msg, bot, selected_session, msg.text)

    assert bot.deleted == [(555, 777)]
    assert selected_session.payload["pending_advanced_action"]["action"] == "mutetime"
    assert "Confirmar ação" in msg.answers[-1][0]
    assert selected_session.payload.get("flow_prompt_message_id") is None


@pytest.mark.asyncio
async def test_panel_button_after_confirmation_edits_current_message(monkeypatch, selected_session):
    panel = import_panel(monkeypatch)
    bot = FakeBot()
    monkeypatch.setattr(panel, "TIGRAO_BOT_ACCESS_USER_IDS", frozenset({OWNER_ID}))
    cb = FakeCallback(selected_session.session_id, "panel")

    await panel.tigrao_callback(cb, bot)

    assert cb.message.edits
    assert "Grupo selecionado" in cb.message.edits[-1][0]

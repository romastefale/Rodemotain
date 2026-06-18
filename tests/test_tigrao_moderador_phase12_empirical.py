from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine


OWNER_ID = 111
CHAT_ID = -1001234567890
GROUP_TITLE = "Grupo Teste"


def import_panel_with_aiogram_stub(monkeypatch):
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

    monkeypatch.setitem(sys.modules, "aiogram", aiogram_mod)
    monkeypatch.setitem(sys.modules, "aiogram.filters", filters_mod)
    monkeypatch.setitem(sys.modules, "aiogram.types", types_mod)
    sys.modules.pop("app.plugins.tigrao_fsm.routers.panel", None)
    return importlib.import_module("app.plugins.tigrao_fsm.routers.panel")


class FakePanelMessage:
    def __init__(self, *, fail_edit: bool = False) -> None:
        self.fail_edit = fail_edit
        self.edits: list[tuple[str, object]] = []
        self.deleted = False

    async def edit_text(self, text: str, reply_markup=None):
        if self.fail_edit:
            raise RuntimeError("message to edit not found")
        self.edits.append((text, reply_markup))

    async def delete(self):
        self.deleted = True


class FakeCallback:
    def __init__(self, session_id: str, action: str, *, fail_edit: bool = False, user_id: int = OWNER_ID) -> None:
        self.data = f"tgf:{session_id}:{action}"
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakePanelMessage(fail_edit=fail_edit)
        self.answers: list[object] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class FakeDmMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=OWNER_ID)
        self.chat = SimpleNamespace(type="private")
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def get_me(self):
        return SimpleNamespace(id=999)

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(
            status="administrator" if user_id == 999 else "member",
            can_delete_messages=True,
            can_restrict_members=True,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_manage_topics=True,
            can_promote_members=True,
            can_manage_direct_messages=True,
            can_manage_tags=True,
        )

    async def restrict_chat_member(self, **kwargs):
        self.calls.append(("restrict_chat_member", kwargs))

    async def ban_chat_member(self, **kwargs):
        self.calls.append(("ban_chat_member", kwargs))

    async def delete_messages(self, **kwargs):
        self.calls.append(("delete_messages", kwargs))

    async def set_chat_permissions(self, **kwargs):
        self.calls.append(("set_chat_permissions", kwargs))

    async def pin_chat_message(self, **kwargs):
        self.calls.append(("pin_chat_message", kwargs))

    async def unpin_all_chat_messages(self, **kwargs):
        self.calls.append(("unpin_all_chat_messages", kwargs))

    async def set_chat_title(self, **kwargs):
        self.calls.append(("set_chat_title", kwargs))

    async def set_chat_description(self, **kwargs):
        self.calls.append(("set_chat_description", kwargs))

    async def delete_message_reaction(self, **kwargs):
        self.calls.append(("delete_message_reaction", kwargs))

    async def delete_all_message_reactions(self, **kwargs):
        self.calls.append(("delete_all_message_reactions", kwargs))

    async def get_chat_administrators(self, **kwargs):
        self.calls.append(("get_chat_administrators", kwargs))
        return [
            SimpleNamespace(user=SimpleNamespace(id=999, is_bot=True, username="bot", full_name="Bot"), status="administrator"),
            SimpleNamespace(user=SimpleNamespace(id=OWNER_ID, is_bot=False, username="owner", full_name="Owner"), status="creator"),
        ]


@pytest.fixture()
def isolated_storage(monkeypatch, tmp_path):
    from app.plugins.tigrao_fsm import storage

    engine = create_engine(f"sqlite:///{tmp_path / 'phase12.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(storage, "engine", engine)
    storage.ensure_tables()
    return storage


@pytest.fixture()
def selected_session():
    from app.plugins.tigrao_fsm.state import close_session, create_session

    session = create_session(owner_user_id=OWNER_ID, moderator_user_id=OWNER_ID)
    session.selected_chat_id = CHAT_ID
    session.selected_group_title = GROUP_TITLE
    try:
        yield session
    finally:
        close_session(session.session_id)


@pytest.mark.asyncio
async def test_empirical_text_advanced_flow_prepares_confirmation_but_does_not_call_bot(selected_session, isolated_storage, monkeypatch):
    panel = import_panel_with_aiogram_stub(monkeypatch)

    bot = FakeBot()
    selected_session.selected_action = "mutetime"
    selected_session.waiting_for = "advanced_text"

    msg = FakeDmMessage("222 | 1h30m")
    await panel._handle_advanced_text(msg, bot, selected_session, msg.text)

    assert selected_session.waiting_for is None
    assert selected_session.payload["pending_advanced_action"]["action"] == "mutetime"
    assert selected_session.payload["pending_advanced_action"]["user_id"] == 222
    assert selected_session.payload["pending_advanced_action"]["duration_seconds"] == 5400
    assert bot.calls == []
    assert "Confirmar ação" in msg.answers[-1][0]


@pytest.mark.asyncio
async def test_empirical_confirm_button_executes_prepared_mute_and_clears_pending(selected_session, isolated_storage, monkeypatch):
    panel = import_panel_with_aiogram_stub(monkeypatch)

    bot = FakeBot()
    selected_session.payload["pending_advanced_action"] = {
        "action": "mutetime",
        "user_id": 222,
        "duration_seconds": 1800,
        "duration_label": "30m",
    }
    callback = FakeCallback(selected_session.session_id, "confirm")

    await panel._confirm_pending_action(callback, bot, selected_session)

    assert selected_session.payload.get("pending_advanced_action") is None
    assert selected_session.selected_action is None
    assert selected_session.waiting_for is None
    assert bot.calls and bot.calls[0][0] == "restrict_chat_member"
    assert bot.calls[0][1]["chat_id"] == CHAT_ID
    assert bot.calls[0][1]["user_id"] == 222
    assert "Resultado: concluido" in callback.message.edits[-1][0]


@pytest.mark.asyncio
async def test_empirical_lockdown_requires_confirm_before_set_chat_permissions(selected_session, isolated_storage, monkeypatch):
    panel = import_panel_with_aiogram_stub(monkeypatch)

    bot = FakeBot()
    prepare_cb = FakeCallback(selected_session.session_id, "lock")
    await panel._prepare_advanced_confirmation(prepare_cb, bot, selected_session, "lock")

    assert selected_session.payload["pending_advanced_action"] == {"action": "lock"}
    assert bot.calls == []
    assert "Confirmar ação" in prepare_cb.message.edits[-1][0]

    confirm_cb = FakeCallback(selected_session.session_id, "confirm")
    await panel._confirm_pending_action(confirm_cb, bot, selected_session)

    assert bot.calls and bot.calls[0][0] == "set_chat_permissions"
    assert selected_session.payload.get("pending_advanced_action") is None


@pytest.mark.asyncio
async def test_empirical_back_navigation_clears_pending_and_returns_to_actions(selected_session, isolated_storage, monkeypatch):
    panel = import_panel_with_aiogram_stub(monkeypatch)

    bot = FakeBot()
    selected_session.payload["pending_advanced_action"] = {"action": "purge", "message_ids": [10]}
    selected_session.payload["pending_destructive_action"] = {"action": "delmsg", "message_id": 9}
    selected_session.payload["nav_back"] = "act"
    selected_session.waiting_for = "advanced_text"
    selected_session.selected_action = "purge"
    callback = FakeCallback(selected_session.session_id, "back")

    await panel._go_back(callback, bot, selected_session)

    assert "pending_advanced_action" not in selected_session.payload
    assert "pending_destructive_action" not in selected_session.payload
    assert selected_session.waiting_for is None
    assert selected_session.selected_action is None
    assert "Ações do grupo" in callback.message.edits[-1][0]


@pytest.mark.asyncio
async def test_empirical_safe_edit_falls_back_to_answer_when_panel_message_cannot_be_edited(selected_session, monkeypatch):
    panel = import_panel_with_aiogram_stub(monkeypatch)

    callback = FakeCallback(selected_session.session_id, "home", fail_edit=True)
    await panel._safe_edit(callback, "texto", None)

    assert callback.message.edits == []
    assert callback.answers


@pytest.mark.asyncio
async def test_empirical_admin_audit_uses_return_bots_true(selected_session, isolated_storage, monkeypatch):
    panel = import_panel_with_aiogram_stub(monkeypatch)

    bot = FakeBot()
    callback = FakeCallback(selected_session.session_id, "admins")
    await panel._execute_advanced_no_text(callback, bot, selected_session, "admins")

    assert bot.calls and bot.calls[0][0] == "get_chat_administrators"
    assert bot.calls[0][1].get("return_bots") is True
    assert "administradores/bots" in callback.message.edits[-1][0]

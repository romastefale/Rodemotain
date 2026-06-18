from __future__ import annotations

from types import SimpleNamespace

import pytest


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str, object | None]] = []
        self.edits: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))
        return SimpleNamespace(message_id=777)

    async def edit_text(self, text: str, reply_markup=None):
        self.edits.append((text, reply_markup))
        return None


class FakeCallback:
    def __init__(self) -> None:
        self.message = FakeMessage()
        self.answered = False

    async def answer(self, *args, **kwargs):
        self.answered = True


class FakeInvite:
    invite_link = "https://t.me/+direct123"


class FakeBot:
    def __init__(self) -> None:
        self.create_kwargs = None

    async def create_chat_invite_link(self, **kwargs):
        self.create_kwargs = kwargs
        return FakeInvite()


@pytest.mark.asyncio
async def test_join_menu_can_create_direct_invite_link_and_sends_persistent_message(monkeypatch):
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions
    from app.plugins.tigrao_fsm.routers import panel

    async def fake_permissions(bot, chat_id):
        return TigraoBotPermissions(is_admin=True, can_invite_users=True)

    monkeypatch.setattr(panel, "get_bot_permissions", fake_permissions)
    monkeypatch.setattr(panel.storage, "log_event", lambda **kwargs: None)

    callback = FakeCallback()
    bot = FakeBot()
    session = SimpleNamespace(
        session_id="abc123",
        selected_chat_id=-1001,
        selected_group_title="Grupo",
        moderator_user_id=111,
        owner_user_id=111,
        payload={},
    )

    await panel._create_join_link(callback, bot, session, creates_join_request=False)

    assert bot.create_kwargs == {"chat_id": -1001, "name": "Rodemotain direto", "creates_join_request": False}
    assert callback.message.answers
    assert "Link direto de entrada" in callback.message.answers[-1][0]
    assert "https://t.me/+direct123" in callback.message.answers[-1][0]
    assert "Link direto de entrada criado e enviado em mensagem individual" in callback.message.edits[-1][0]
    assert "last_invite_link" not in session.payload


def test_phase28_join_keyboard_exposes_direct_entry_link():
    from app.plugins.tigrao_fsm.keyboards import join_requests_keyboard

    labels = [button.text for row in join_requests_keyboard("abc123") for button in row]
    assert "🔗 Criar link com solicitação" in labels
    assert "🔗 Criar link direto" in labels


def test_phase28_invite_parser_accepts_direct_link_alias():
    from app.plugins.tigrao_fsm.parsers import parse_invite_create_action

    parsed = parse_invite_create_action("Entrada direta | permanente | 0 | direto")
    assert parsed.error is None
    assert parsed.creates_join_request is False
    assert parsed.member_limit is None


def test_phase28_link_results_are_extracted_for_persistent_message():
    from app.plugins.tigrao_fsm.routers.panel import _extract_invite_link

    assert _extract_invite_link("Link criado:\nhttps://t.me/+abc123") == "https://t.me/+abc123"

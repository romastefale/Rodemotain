from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine


OWNER_ID = 111
CHAT_ID = -100123
CHAT_TITLE = "Grupo"
USER_ID = 222


@pytest.fixture()
def isolated_storage(monkeypatch, tmp_path):
    from app.plugins.tigrao_fsm import storage

    engine = create_engine(f"sqlite:///{tmp_path / 'phase15.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(storage, "engine", engine)
    storage.ensure_tables()
    return storage


@pytest.fixture()
def selected_session():
    from app.plugins.tigrao_fsm.state import close_session, create_session

    session = create_session(owner_user_id=OWNER_ID, moderator_user_id=OWNER_ID)
    session.selected_chat_id = CHAT_ID
    session.selected_group_title = CHAT_TITLE
    try:
        yield session
    finally:
        close_session(session.session_id)


class FakeDmPhotoMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=OWNER_ID)
        self.chat = SimpleNamespace(type="private")
        self.photo = [SimpleNamespace(file_id="small", width=64, height=64, file_size=100), SimpleNamespace(file_id="big-file-id", width=512, height=512, file_size=2048)]
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


class FakeCallbackMessage:
    def __init__(self) -> None:
        self.edits: list[tuple[str, object]] = []

    async def edit_text(self, text: str, reply_markup=None):
        self.edits.append((text, reply_markup))


class FakeCallback:
    def __init__(self, session_id: str) -> None:
        self.data = f"tgf:{session_id}:confirm"
        self.from_user = SimpleNamespace(id=OWNER_ID)
        self.message = FakeCallbackMessage()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class FakePhotoBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def get_me(self):
        return SimpleNamespace(id=999)

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status="administrator", can_change_info=True)

    async def download(self, file_id, destination: BytesIO):
        self.calls.append(("download", {"file_id": file_id}))
        destination.write(b"jpg-bytes")

    async def set_chat_photo(self, **kwargs):
        self.calls.append(("set_chat_photo", kwargs))
        return True


@pytest.mark.asyncio
async def test_phase15_setphoto_photo_upload_only_prepares_confirmation(monkeypatch, selected_session, isolated_storage) -> None:
    from app.plugins.tigrao_fsm.routers import panel

    monkeypatch.setattr(panel, "_authorized", lambda user_id: True)
    monkeypatch.setattr(panel, "BufferedInputFile", lambda payload, filename: {"payload": payload, "filename": filename})
    selected_session.waiting_for = "setphoto_upload"
    selected_session.selected_action = "setphoto"
    bot = FakePhotoBot()
    msg = FakeDmPhotoMessage()

    await panel.tigrao_waiting_photo(msg, bot)

    assert selected_session.waiting_for is None
    assert selected_session.payload["pending_advanced_action"]["action"] == "setphoto"
    assert selected_session.payload["pending_advanced_action"]["file_id"] == "big-file-id"
    assert bot.calls == []
    assert "Confirmar" in msg.answers[-1][0]


@pytest.mark.asyncio
async def test_phase15_setphoto_confirm_downloads_and_changes_photo(monkeypatch, selected_session, isolated_storage) -> None:
    from app.plugins.tigrao_fsm.routers import panel

    monkeypatch.setattr(panel, "BufferedInputFile", lambda payload, filename: {"payload": payload, "filename": filename})
    selected_session.payload["pending_advanced_action"] = {"action": "setphoto", "file_id": "big-file-id"}
    bot = FakePhotoBot()
    cb = FakeCallback(selected_session.session_id)

    await panel._confirm_pending_action(cb, bot, selected_session)

    assert [name for name, _ in bot.calls] == ["download", "set_chat_photo"]
    assert bot.calls[-1][1]["chat_id"] == CHAT_ID
    assert bot.calls[-1][1]["photo"]["payload"] == b"jpg-bytes"
    assert selected_session.payload.get("pending_advanced_action") is None
    assert "✅ Concluído" in cb.message.edits[-1][0]


def test_phase15_captcha_challenge_stores_and_uses_configured_max_attempts(isolated_storage) -> None:
    storage = isolated_storage

    storage.create_captcha_challenge(chat_id=CHAT_ID, chat_title=CHAT_TITLE, user_id=USER_ID, user_chat_id=USER_ID, code="1234", ttl_seconds=60, max_attempts=2)

    assert storage.verify_captcha_challenge(user_id=USER_ID, code="0000")["status"] == "pendente"
    second = storage.verify_captcha_challenge(user_id=USER_ID, code="0000")
    assert second["status"] == "falhou"


@pytest.mark.asyncio
async def test_phase15_anti_raid_queue_consumes_update_and_prevents_auto_flow(isolated_storage) -> None:
    from app.plugins.tigrao_fsm import storage
    from app.plugins.tigrao_fsm.models import TigraoJoinRequest
    from app.plugins.tigrao_fsm.runtime import join_request_runtime

    storage.set_protection_setting(chat_id=CHAT_ID, name="anti_raid", enabled=True, config={"limit": 1, "window_seconds": 60, "action": "queue"}, updated_by=OWNER_ID)
    request = TigraoJoinRequest.create(chat_id=CHAT_ID, chat_title=CHAT_TITLE, user_id=USER_ID, username=None, full_name="User", user_chat_id=USER_ID, bio=None, invite_link=None, request_date=datetime.now(timezone.utc))
    storage.save_join_request(request)
    bot = SimpleNamespace()

    assert await join_request_runtime._anti_raid_gate(bot, request) is True


@pytest.mark.asyncio
async def test_phase15_anti_raid_lock_consumes_update_after_locking(isolated_storage) -> None:
    from app.plugins.tigrao_fsm import storage
    from app.plugins.tigrao_fsm.models import TigraoJoinRequest
    from app.plugins.tigrao_fsm.runtime import join_request_runtime

    class Bot:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        async def set_chat_permissions(self, **kwargs):
            self.calls.append(("set_chat_permissions", kwargs))

    storage.set_protection_setting(chat_id=CHAT_ID, name="anti_raid", enabled=True, config={"limit": 1, "window_seconds": 60, "action": "lock"}, updated_by=OWNER_ID)
    request = TigraoJoinRequest.create(chat_id=CHAT_ID, chat_title=CHAT_TITLE, user_id=USER_ID, username=None, full_name="User", user_chat_id=USER_ID, bio=None, invite_link=None, request_date=datetime.now(timezone.utc))
    storage.save_join_request(request)
    bot = Bot()

    assert await join_request_runtime._anti_raid_gate(bot, request) is True
    assert bot.calls and bot.calls[-1][0] == "set_chat_permissions"

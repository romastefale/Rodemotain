from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_parse_message_ref_accepts_raw_id_and_links() -> None:
    from app.plugins.tigrao_fsm.parsers import parse_message_ref

    assert parse_message_ref("12345").message_id == 12345

    private_link = parse_message_ref("https://t.me/c/1234567890/55", selected_chat_id=-1001234567890)
    assert private_link.message_id == 55
    assert private_link.chat_id_from_link == -1001234567890

    topic_link = parse_message_ref("https://t.me/c/1234567890/44/66", selected_chat_id=-1001234567890)
    assert topic_link.message_id == 66
    assert topic_link.chat_id_from_link == -1001234567890

    public_link = parse_message_ref("https://t.me/grupo_publico/77")
    assert public_link.message_id == 77
    assert public_link.chat_id_from_link is None


def test_parse_message_ref_rejects_wrong_group_link() -> None:
    from app.plugins.tigrao_fsm.parsers import parse_message_ref

    parsed = parse_message_ref("https://t.me/c/1234567890/55", selected_chat_id=-1009999999999)
    assert parsed.message_id is None
    assert parsed.chat_id_from_link == -1001234567890
    assert "outro grupo" in (parsed.error or "")


def test_delete_message_prompt_accepts_telegram_link_static() -> None:
    panel = read("app/plugins/tigrao_fsm/routers/panel.py")
    assert "parse_message_ref(text, selected_chat_id=chat_id)" in panel
    assert "message_id numérico ou o link t.me" in panel
    assert "chat_id_from_link" in panel


def test_polling_surfaces_have_runtime_handlers_static() -> None:
    panel = read("app/plugins/tigrao_fsm/routers/panel.py")
    assert "@router.chat_join_request()" in panel
    assert "tigrao_join_request_polling" in panel
    assert "join_request_handle(bot, SimpleNamespace(chat_join_request=join_request))" in panel
    assert "tigrao_group_runtime_probe" in panel
    assert "ddx_handle(bot, SimpleNamespace(message=message))" in panel


def test_group_registry_normalizes_aiogram_chat_type(monkeypatch, tmp_path) -> None:
    from app.bot import group_registry

    engine = create_engine(f"sqlite:///{tmp_path / 'groups.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(group_registry, "engine", engine)
    chat_type = SimpleNamespace(value="supergroup")

    group_registry.remember_group(chat_id=-1001, title="Grupo", username="grupo", chat_type=chat_type)

    with engine.begin() as conn:
        row = conn.execute(text("SELECT chat_id, title, username, chat_type FROM tigrao_groups")).mappings().one()
    assert row["chat_id"] == -1001
    assert row["title"] == "Grupo"
    assert row["username"] == "grupo"
    assert row["chat_type"] == "supergroup"


@pytest.fixture()
def isolated_storage(monkeypatch, tmp_path):
    from app.plugins.tigrao_fsm import storage

    engine = create_engine(f"sqlite:///{tmp_path / 'tigrao_phase6.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(storage, "engine", engine)
    storage.ensure_tables()
    return storage


class FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))


@pytest.mark.asyncio
async def test_ddx_polling_runtime_probe_deletes_when_filter_matches(isolated_storage, monkeypatch) -> None:
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions
    from app.plugins.tigrao_fsm.runtime import ddx_runtime

    isolated_storage.create_ddx_filter(chat_id=-1001, filter_text="proibida", created_by=999, enabled=True)
    bot = FakeBot()
    message = SimpleNamespace(
        chat=SimpleNamespace(id=-1001, title="Grupo", type="supergroup"),
        from_user=SimpleNamespace(id=123, username="u", full_name="User", first_name="User"),
        message_id=9,
        text="palavra proibida",
        caption=None,
    )

    consumed = await ddx_runtime.handle(bot, SimpleNamespace(message=message), permissions=TigraoBotPermissions(is_admin=True, can_delete_messages=True))

    assert consumed is True
    assert bot.deleted == [(-1001, 9)]
    assert isolated_storage.list_logs(chat_id=-1001)[0]["action"] == "ddx_delete"

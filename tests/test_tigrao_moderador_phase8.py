from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_requirements_pin_aiogram_328_for_bot_api_101_surface() -> None:
    requirements = read("requirements.txt")
    assert "aiogram>=3.28,<3.29" in requirements


def test_ddx_filter_input_accepts_custom_durations() -> None:
    from app.plugins.tigrao_fsm.parsers import parse_ddx_filter_input

    parsed = parse_ddx_filter_input("spam | 30m")
    assert parsed.filter_text == "spam"
    assert parsed.duration == timedelta(minutes=30)
    assert parsed.duration_raw == "30m"

    parsed = parse_ddx_filter_input("golpe | 2 horas")
    assert parsed.filter_text == "golpe"
    assert parsed.duration == timedelta(hours=2)

    parsed = parse_ddx_filter_input("palavra permanente")
    assert parsed.filter_text == "palavra permanente"
    assert parsed.duration is None
    assert parsed.error is None


def test_ddx_storage_ignores_expired_filters(monkeypatch, tmp_path) -> None:
    from app.plugins.tigrao_fsm import storage

    engine = create_engine(f"sqlite:///{tmp_path / 'tigrao_phase8.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(storage, "engine", engine)
    storage.ensure_tables()

    now = storage.utcnow()
    storage.create_ddx_filter(chat_id=-1001, filter_text="ativo", created_by=1, duration=timedelta(hours=1), created_at=now)
    storage.create_ddx_filter(chat_id=-1001, filter_text="expirado", created_by=1, duration=timedelta(seconds=1), created_at=now - timedelta(hours=1))

    assert storage.get_enabled_ddx_filters(chat_id=-1001) == ["ativo"]


@pytest.mark.asyncio
async def test_ddx_runtime_deletes_with_temporary_active_filter(monkeypatch, tmp_path) -> None:
    from app.plugins.tigrao_fsm import storage
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions
    from app.plugins.tigrao_fsm.runtime import ddx_runtime

    engine = create_engine(f"sqlite:///{tmp_path / 'tigrao_phase8_runtime.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(storage, "engine", engine)
    storage.ensure_tables()
    storage.create_ddx_filter(chat_id=-1001, filter_text="temporario", created_by=1, duration=timedelta(minutes=5))

    class FakeBot:
        def __init__(self) -> None:
            self.deleted: list[tuple[int, int]] = []

        async def delete_message(self, chat_id: int, message_id: int) -> None:
            self.deleted.append((chat_id, message_id))

    bot = FakeBot()
    message = SimpleNamespace(
        chat=SimpleNamespace(id=-1001, title="Grupo", type="supergroup"),
        from_user=SimpleNamespace(id=123, username="u", full_name="User", first_name="User"),
        message_id=12,
        text="texto temporario aqui",
        caption=None,
    )

    consumed = await ddx_runtime.handle(
        bot,
        SimpleNamespace(message=message),
        permissions=TigraoBotPermissions(is_admin=True, can_delete_messages=True),
    )

    assert consumed is True
    assert bot.deleted == [(-1001, 12)]

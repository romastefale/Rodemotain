from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine


CHAT_ID = -100123
CHAT_TITLE = "Grupo"
OWNER_ID = 111
USER_ID = 222


@pytest.fixture()
def isolated_storage(monkeypatch, tmp_path):
    from app.plugins.tigrao_fsm import storage

    engine = create_engine(f"sqlite:///{tmp_path / 'phase14.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(storage, "engine", engine)
    storage.ensure_tables()
    return storage


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def set_chat_member_tag(self, **kwargs):
        self.calls.append(("set_chat_member_tag", kwargs))
        return True

    async def delete_chat_photo(self, **kwargs):
        self.calls.append(("delete_chat_photo", kwargs))
        return True

    async def set_chat_photo(self, **kwargs):
        self.calls.append(("set_chat_photo", kwargs))
        return True

    async def create_forum_topic(self, **kwargs):
        self.calls.append(("create_forum_topic", kwargs))
        return SimpleNamespace(message_thread_id=77)

    async def edit_forum_topic(self, **kwargs):
        self.calls.append(("edit_forum_topic", kwargs))
        return True

    async def close_forum_topic(self, **kwargs):
        self.calls.append(("close_forum_topic", kwargs))
        return True

    async def delete_forum_topic(self, **kwargs):
        self.calls.append(("delete_forum_topic", kwargs))
        return True

    async def unpin_all_forum_topic_messages(self, **kwargs):
        self.calls.append(("unpin_all_forum_topic_messages", kwargs))
        return True

    async def edit_general_forum_topic(self, **kwargs):
        self.calls.append(("edit_general_forum_topic", kwargs))
        return True

    async def unpin_all_general_forum_topic_messages(self, **kwargs):
        self.calls.append(("unpin_all_general_forum_topic_messages", kwargs))
        return True

    async def send_chat_join_request_web_app(self, **kwargs):
        self.calls.append(("send_chat_join_request_web_app", kwargs))
        return True


@pytest.mark.asyncio
async def test_etapa02_advanced_actions_call_bot_api_methods(isolated_storage) -> None:
    from app.plugins.tigrao_fsm.advanced_actions import (
        create_forum_topic_action,
        delete_group_photo,
        edit_forum_topic_action,
        manage_forum_topic_action,
        manage_general_forum_topic_action,
        set_group_photo_file,
        set_member_tag_action,
    )
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions

    perms = TigraoBotPermissions(
        is_admin=True,
        can_change_info=True,
        can_manage_topics=True,
        can_manage_tags=True,
        can_delete_messages=True,
        can_pin_messages=True,
    )
    bot = FakeBot()

    await set_member_tag_action(bot, chat_id=CHAT_ID, chat_title=CHAT_TITLE, actor_user_id=OWNER_ID, user_id=USER_ID, tag="vip", permissions=perms)
    assert bot.calls[-1] == ("set_chat_member_tag", {"chat_id": CHAT_ID, "user_id": USER_ID, "tag": "vip"})

    await delete_group_photo(bot, chat_id=CHAT_ID, chat_title=CHAT_TITLE, actor_user_id=OWNER_ID, permissions=perms)
    assert bot.calls[-1][0] == "delete_chat_photo"

    await set_group_photo_file(bot, chat_id=CHAT_ID, chat_title=CHAT_TITLE, actor_user_id=OWNER_ID, photo=b"x", permissions=perms)
    assert bot.calls[-1][0] == "set_chat_photo"

    await create_forum_topic_action(bot, chat_id=CHAT_ID, chat_title=CHAT_TITLE, actor_user_id=OWNER_ID, name="Avisos", icon_color=7322096, permissions=perms)
    assert bot.calls[-1][0] == "create_forum_topic"
    assert bot.calls[-1][1]["icon_color"] == 7322096

    await edit_forum_topic_action(bot, chat_id=CHAT_ID, chat_title=CHAT_TITLE, actor_user_id=OWNER_ID, message_thread_id=77, name="Regras", icon_color=None, permissions=perms)
    assert bot.calls[-1][0] == "edit_forum_topic"

    await manage_forum_topic_action(bot, chat_id=CHAT_ID, chat_title=CHAT_TITLE, actor_user_id=OWNER_ID, action="topicdelete", message_thread_id=77, permissions=perms)
    assert bot.calls[-1][0] == "delete_forum_topic"

    await manage_forum_topic_action(bot, chat_id=CHAT_ID, chat_title=CHAT_TITLE, actor_user_id=OWNER_ID, action="topicunpin", message_thread_id=77, permissions=perms)
    assert bot.calls[-1][0] == "unpin_all_forum_topic_messages"

    await manage_general_forum_topic_action(bot, chat_id=CHAT_ID, chat_title=CHAT_TITLE, actor_user_id=OWNER_ID, action="topicgedit", name="Geral", permissions=perms)
    assert bot.calls[-1][0] == "edit_general_forum_topic"

    await manage_general_forum_topic_action(bot, chat_id=CHAT_ID, chat_title=CHAT_TITLE, actor_user_id=OWNER_ID, action="topicgunpin", permissions=perms)
    assert bot.calls[-1][0] == "unpin_all_general_forum_topic_messages"


def test_etapa02_parsers_and_buttons() -> None:
    from app.plugins.tigrao_fsm.keyboards import CALLBACK_ACTIONS
    from app.plugins.tigrao_fsm.parsers import (
        parse_antiflood_setting,
        parse_antiraid_setting,
        parse_captcha_setting,
        parse_topic_create_action,
        parse_topic_edit_action,
        parse_user_text_action,
    )

    assert parse_topic_create_action("Avisos | 7322096").icon_color == 7322096
    assert parse_topic_edit_action("77 | Regras | #6FB9F0").icon_color == 7322096
    assert parse_user_text_action("222 | vip", max_text_len=16, allow_empty_text=True).text == "vip"
    assert parse_antiflood_setting("on | 5 | 10s | 10m").config["mute_seconds"] == 600
    assert parse_antiraid_setting("on | 4 | 1m | lock").config["action"] == "lock"
    assert parse_captcha_setting("on | 5m | 3").config["max_attempts"] == 3

    for action in (
        "setphoto", "delphoto", "settag", "warnadd", "warnlist", "warnclear",
        "protstatus", "antiflood", "antiraid", "captcha",
    ):
        assert action in CALLBACK_ACTIONS
    for removed_action in (
        "topiccreate", "topicedit", "topicclose", "topicreopen", "topicdelete", "topicunpin",
        "topicgedit", "topicgclose", "topicgreopen", "topicghide", "topicgunhide", "topicgunpin",
    ):
        assert removed_action not in CALLBACK_ACTIONS


def test_etapa02_storage_warnings_protection_and_captcha(isolated_storage) -> None:
    storage = isolated_storage

    wid = storage.add_warning(chat_id=CHAT_ID, chat_title=CHAT_TITLE, user_id=USER_ID, reason="spam", created_by=OWNER_ID)
    assert wid > 0
    assert storage.count_warnings(chat_id=CHAT_ID, user_id=USER_ID) == 1
    assert "spam" in storage.list_warnings(chat_id=CHAT_ID, user_id=USER_ID)[0]["reason"]

    storage.set_protection_setting(chat_id=CHAT_ID, name="anti_raid", enabled=True, config={"limit": 3, "window_seconds": 60, "action": "decline"}, updated_by=OWNER_ID)
    setting = storage.get_protection_setting(chat_id=CHAT_ID, name="anti_raid")
    assert setting["enabled"] is True
    assert setting["config"]["action"] == "decline"

    storage.create_captcha_challenge(chat_id=CHAT_ID, chat_title=CHAT_TITLE, user_id=USER_ID, user_chat_id=USER_ID, code="1234", ttl_seconds=60)
    assert storage.verify_captcha_challenge(user_id=USER_ID, code="0000", max_attempts=3)["status"] == "pendente"
    assert storage.verify_captcha_challenge(user_id=USER_ID, code="1234", max_attempts=3)["status"] == "aprovado"


@pytest.mark.asyncio
async def test_join_request_mini_app_dispatch(monkeypatch, isolated_storage) -> None:
    from app.plugins.tigrao_fsm.models import TigraoJoinRequest
    from app.plugins.tigrao_fsm.runtime import join_request_runtime

    monkeypatch.setattr(join_request_runtime, "TIGRAO_JOIN_REQUEST_WEBAPP_URL", "https://example.com/join")
    request = TigraoJoinRequest.create(chat_id=CHAT_ID, chat_title=CHAT_TITLE, user_id=USER_ID, username=None, full_name="User", user_chat_id=USER_ID, bio=None, invite_link=None, request_date=datetime.now(timezone.utc))
    join_request = SimpleNamespace(query_id="query-1")
    bot = FakeBot()

    assert await join_request_runtime._send_join_request_webapp_if_available(bot, join_request, request) is True
    assert bot.calls[-1] == ("send_chat_join_request_web_app", {"chat_join_request_query_id": "query-1", "web_app_url": "https://example.com/join"})


@pytest.mark.asyncio
async def test_anti_flood_runtime_uses_config_and_restricts(monkeypatch, isolated_storage) -> None:
    from app.plugins.tigrao_fsm import storage
    from app.plugins.tigrao_fsm.runtime import anti_flood_runtime
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions

    class FloodBot:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []
        async def delete_message(self, **kwargs):
            self.calls.append(("delete_message", kwargs))
        async def restrict_chat_member(self, **kwargs):
            self.calls.append(("restrict_chat_member", kwargs))

    async def fake_perms(bot, chat_id):
        return TigraoBotPermissions(is_admin=True, can_delete_messages=True, can_restrict_members=True)

    monkeypatch.setattr(anti_flood_runtime, "get_bot_permissions", fake_perms)
    storage.set_protection_setting(chat_id=CHAT_ID, name="anti_flood", enabled=True, config={"limit": 2, "window_seconds": 60, "mute_seconds": 30, "delete": True}, updated_by=OWNER_ID)
    bot = FloodBot()

    for i in range(3):
        update = SimpleNamespace(message=SimpleNamespace(chat=SimpleNamespace(id=CHAT_ID, type="supergroup", title=CHAT_TITLE), from_user=SimpleNamespace(id=USER_ID, is_bot=False), message_id=100 + i))
        await anti_flood_runtime.handle(bot, update)

    assert any(name == "delete_message" for name, _ in bot.calls)
    assert any(name == "restrict_chat_member" for name, _ in bot.calls)


def test_join_request_query_endpoint_is_present() -> None:
    source = __import__("pathlib").Path("app/main.py").read_text(encoding="utf-8")
    assert "/telegram/join-request-query" in source
    assert "answer_chat_join_request_query" in source
    assert "approve" in source and "decline" in source and "queue" in source

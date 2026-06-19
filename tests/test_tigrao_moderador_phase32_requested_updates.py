from types import SimpleNamespace

import pytest


def _texts(rows):
    return [button.text for row in rows for button in row]


def test_phase32_join_menu_is_split_into_subcategories() -> None:
    from app.plugins.tigrao_fsm.keyboards import join_auto_keyboard, join_links_keyboard, join_pending_keyboard, join_requests_keyboard

    main = _texts(join_requests_keyboard("s"))
    assert "🕒 Pedidos pendentes" in main
    assert "🔗 Criação de links" in main
    assert "⚙️ Autorização automática" in main
    assert "📥 Aceitar ID pendente" not in main

    pending = _texts(join_pending_keyboard("s"))
    assert "📥 Aceitar ID pendente" in pending
    assert "📤 Recusar ID pendente" in pending

    links = _texts(join_links_keyboard("s"))
    assert "🔗 Criar link com solicitação" in links
    assert "✅ Criar link direto" in links

    auto = _texts(join_auto_keyboard("s"))
    assert "📝 Informar IDs autorizados" in auto


def test_phase32_reactions_live_under_messages_category() -> None:
    from app.plugins.tigrao_fsm.keyboards import CALLBACK_ACTIONS, action_category_keyboard, destructive_actions_keyboard

    main = _texts(destructive_actions_keyboard("s"))
    assert "⚛️ Reações" not in main
    assert "cat_react" not in CALLBACK_ACTIONS

    msg = _texts(action_category_keyboard("s", "cat_msg"))
    assert "⚛️ Reações" in msg

    react = _texts(action_category_keyboard("s", "sub_react_delete"))
    assert "⚛️ Remover reação" in react
    assert "🧹 Remover reações recentes" in react


def test_phase32_ddx_parser_accepts_newline_format() -> None:
    from app.plugins.tigrao_fsm.parsers import parse_ddx_filter_input

    parsed = parse_ddx_filter_input("link proibido\n1h30m")
    assert parsed.error is None
    assert parsed.filter_text == "link proibido"
    assert parsed.duration_raw == "1h30m"
    assert parsed.duration is not None

    permanent = parse_ddx_filter_input("golpe")
    assert permanent.error is None
    assert permanent.duration is None


@pytest.mark.asyncio
async def test_phase32_admin_audit_is_human_readable() -> None:
    from app.plugins.tigrao_fsm.advanced_actions import format_admin_audit

    class Bot:
        async def get_chat_administrators(self, **kwargs):
            user = SimpleNamespace(id=8816420837, is_bot=True, full_name="rodemotain", username="rodemotainbot")
            member = SimpleNamespace(
                user=user,
                status="administrator",
                can_be_edited=True,
                can_delete_messages=True,
                can_restrict_members=True,
                can_promote_members=True,
                can_change_info=True,
                can_invite_users=True,
                can_pin_messages=True,
            )
            return [member]

    text = await format_admin_audit(Bot(), chat_id=-1001)
    assert "apagar mensagens" in text
    assert "restringir, mutar e banir membros" in text
    assert "delete_messages" not in text
    assert "status: administrator" not in text


@pytest.mark.asyncio
async def test_phase32_promote_clamps_rights_and_blocks_non_member() -> None:
    from app.plugins.tigrao_fsm.advanced_actions import promote_user_admin
    from app.plugins.tigrao_fsm.permissions import TigraoBotPermissions

    class Bot:
        def __init__(self, status="member"):
            self.status = status
            self.calls = []

        async def get_chat_member(self, **kwargs):
            return SimpleNamespace(status=self.status, can_be_edited=True)

        async def promote_chat_member(self, **kwargs):
            self.calls.append(kwargs)
            return True

    perms = TigraoBotPermissions(is_admin=True, can_promote_members=True, can_invite_users=True)
    bot = Bot(status="member")
    result = await promote_user_admin(bot, chat_id=-1001, chat_title="G", actor_user_id=1, user_id=2, permissions=perms, role="full")
    assert result.ok is True
    assert bot.calls[-1]["can_promote_members"] is True
    assert bot.calls[-1]["can_delete_messages"] is False
    assert bot.calls[-1]["can_invite_users"] is True

    outside = Bot(status="left")
    blocked = await promote_user_admin(outside, chat_id=-1001, chat_title="G", actor_user_id=1, user_id=3, permissions=perms, role="full")
    assert blocked.ok is False
    assert "não está como membro ativo" in blocked.detail
    assert outside.calls == []

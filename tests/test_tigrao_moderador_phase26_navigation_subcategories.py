from app.plugins.tigrao_fsm.keyboards import action_category_keyboard, action_category_parent, destructive_actions_keyboard, parse_callback


def _texts(rows):
    return [button.text for row in rows for button in row]


def _callbacks(rows):
    return [button.callback_data for row in rows for button in row if button.callback_data]


def test_phase26_category_menu_groups_success_before_danger_blocks() -> None:
    texts = _texts(destructive_actions_keyboard("abc123"))
    assert texts.index("👤 Usuários") < texts.index("💬 Mensagens")
    assert texts.index("🔗 Links") < texts.index("👑 Admins")
    assert "🧩 Tópicos" not in texts
    assert texts.index("🔗 Links") < texts.index("👑 Admins")


def test_phase26_user_category_is_split_into_subcategories() -> None:
    texts = _texts(action_category_keyboard("abc123", "cat_user"))
    assert "🔓 Liberar/restaurar" in texts
    assert "🔒 Restringir usuário" in texts
    assert "⚠️ Warnings e tags" in texts
    assert "🔨 Banir" not in texts


def test_phase26_subcategory_exposes_final_actions_and_parent_navigation() -> None:
    rows = action_category_keyboard("abc123", "sub_user_restrict")
    texts = _texts(rows)
    assert "🔨 Banir" in texts
    assert "⏱️ Mute livre" in texts
    assert "⬅️ Subcategorias" in texts
    assert action_category_parent("sub_user_restrict") == "cat_user"
    assert all(parse_callback(data) is not None for data in _callbacks(rows))

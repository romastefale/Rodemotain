from app.plugins.tigrao_fsm.keyboards import action_category_keyboard, destructive_actions_keyboard, group_admin_keyboard, parse_callback


def _texts(rows):
    return [button.text for row in rows for button in row]


def _callbacks(rows):
    return [button.callback_data for row in rows for button in row if button.callback_data]


def test_panel_navigation_is_grouped_by_emoji_categories() -> None:
    rows = group_admin_keyboard("abc123", destructive_actions_enabled=True, ddx_enabled=True)
    texts = _texts(rows)

    assert "👤 Usuários" in texts
    assert "💬 Mensagens" in texts
    assert "👑 Admins" in texts
    assert "🔗 Links" in texts
    assert "🧩 Tópicos" not in texts
    assert "🎛️ Grupo" in texts
    assert "🛡️ Proteções" in texts
    assert "🧾 Auditoria" in texts
    assert "🧨 DDX hard" in texts


def test_action_category_callbacks_are_valid_and_not_a_long_sequence() -> None:
    rows = destructive_actions_keyboard("abc123")
    texts = _texts(rows)
    callbacks = _callbacks(rows)

    assert len(rows) <= 6
    assert "⏱️ Ban por tempo" not in texts
    assert all(parse_callback(data) is not None for data in callbacks)


def test_action_categories_expose_expected_functions() -> None:
    users = _texts(action_category_keyboard("abc123", "cat_user"))
    messages = _texts(action_category_keyboard("abc123", "cat_msg"))
    protections = _texts(action_category_keyboard("abc123", "cat_prot"))

    assert "🔒 Restringir usuário" in users
    assert "🔓 Liberar/restaurar" in users
    assert "🗑️ Apagar/limpar" in messages
    assert "📌 Fixar/organizar" in messages
    assert "🚨 Anti-spam/entrada" in protections
    assert "🧨 DDX hard" in protections

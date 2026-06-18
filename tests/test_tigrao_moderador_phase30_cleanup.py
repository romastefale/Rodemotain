from app.plugins.tigrao_fsm.keyboards import (
    CALLBACK_ACTIONS,
    action_category_keyboard,
    destructive_actions_keyboard,
    group_admin_keyboard,
)


def _texts(rows):
    return [button.text for row in rows for button in row]


def test_phase30_topics_are_removed_from_panel_navigation() -> None:
    group_texts = _texts(group_admin_keyboard("abc123", destructive_actions_enabled=True, ddx_enabled=True))
    action_texts = _texts(destructive_actions_keyboard("abc123"))

    assert "🧩 Tópicos" not in group_texts
    assert "🧩 Tópicos" not in action_texts
    assert "cat_topics" not in CALLBACK_ACTIONS
    assert "topiccreate" not in CALLBACK_ACTIONS
    assert "topicgunpin" not in CALLBACK_ACTIONS


def test_phase30_links_use_clearer_export_language() -> None:
    texts = _texts(action_category_keyboard("abc123", "sub_links_manage"))
    assert "🔑 Gerar novo link principal" in texts
    assert "➕ Criar link adicional" in texts
    assert all("Exportar" not in item for item in texts)

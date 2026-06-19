from pathlib import Path

PANEL = Path("app/plugins/tigrao_fsm/routers/panel.py").read_text(encoding="utf-8")


def test_phase38_total_diagnostic_requires_target_user_id() -> None:
    assert "diagnostico_total exige target_user_id para ser total" in PANEL
    assert "Diagnóstico total real exige target_user_id" in PANEL
    assert "Sem alvo não é diagnóstico total" in PANEL
    assert "/diagnostico_total -1001234567890 CONFIRMO_TOTAL" not in PANEL


def test_phase38_total_diagnostic_covers_more_action_families() -> None:
    for expected in [
        "format_admin_audit",
        "purge_messages",
        "destructive_delmsg",
        "edit_invite_link_full",
        "set_member_tag_action",
        "format_warning_list",
        'DestructiveActionRequest(action="mute1h"',
        'DestructiveActionRequest(action="mute24h"',
        'DestructiveActionRequest(action="muteforever"',
        "ban_user_custom",
        "promote_user_admin",
        "set_admin_custom_title",
        "demote_user_admin",
    ]:
        assert expected in PANEL

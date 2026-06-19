from pathlib import Path


def test_phase35_total_diagnostic_command_exists_and_is_hidden_from_menu() -> None:
    panel = Path("app/plugins/tigrao_fsm/routers/panel.py").read_text(encoding="utf-8")
    main = Path("app/main.py").read_text(encoding="utf-8")
    assert 'Command("diagnostico_total")' in panel
    assert "CONFIRMO_TOTAL" in panel
    assert "rodemotain_diagnostico_total_" in panel
    assert "diagnostic_total_start" in panel
    assert "diagnostic_total_finished" in panel
    assert 'BotCommand(command="diagnostico_total"' not in main


def test_phase35_total_diagnostic_covers_real_action_families() -> None:
    panel = Path("app/plugins/tigrao_fsm/routers/panel.py").read_text(encoding="utf-8")
    for expected in [
        "export_primary_invite_link",
        "create_invite_link_full",
        "revoke_invite_link_full",
        "set_group_title",
        "set_group_description",
        "set_group_lockdown",
        "pin_message",
        "unpin_message",
        "mute_user_custom",
        "ban_user_custom",
        "promote_user_admin",
        "demote_user_admin",
        "set_admin_custom_title",
        "storage.create_ddx_filter",
        "set_protection_action",
    ]:
        assert expected in panel

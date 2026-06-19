from pathlib import Path


def test_phase34_diagnostic_command_is_present_and_hidden_from_menu() -> None:
    panel = Path("app/plugins/tigrao_fsm/routers/panel.py").read_text(encoding="utf-8")
    main = Path("app/main.py").read_text(encoding="utf-8")
    assert 'Command("diagnostico")' in panel
    assert 'rodemotain_diagnostico_' in panel
    assert 'send_document' in panel
    assert 'BufferedInputFile' in panel
    assert 'diagnostic_group_check' in panel
    assert 'diagnostic_finished' in panel
    assert 'BotCommand(command="diagnostico"' not in main


def test_phase34_diagnostic_report_contains_real_audit_sections() -> None:
    panel = Path("app/plugins/tigrao_fsm/routers/panel.py").read_text(encoding="utf-8")
    for expected in [
        "RODEMOTAIN — DIAGNÓSTICO REAL",
        "1. Configuração",
        "2. Bot API",
        "3. Banco e logs",
        "4. Grupos conhecidos e permissões",
        "5. Logs recentes do Rodemotain",
        "getWebhookInfo",
        "getChatAdministrators",
        "DATA_DIR gravável",
    ]:
        assert expected in panel

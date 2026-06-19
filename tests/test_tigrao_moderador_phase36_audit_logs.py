from pathlib import Path

PANEL = Path('app/plugins/tigrao_fsm/routers/panel.py').read_text(encoding='utf-8')


def test_phase36_has_separated_audit_sections_and_raw_error_data():
    assert 'REGISTRO DE EVENTOS' in PANEL
    assert 'REGISTRO DE ERROS' in PANEL
    assert 'RAW DATA DE ERROS' in PANEL
    assert 'RAW DATA DE EVENTOS' in PANEL
    assert 'LOGS DO PROCESSO DURANTE O TESTE' in PANEL
    assert 'traceback.format_exception' in PANEL
    assert 'diagnostic_total_error' in PANEL
    assert 'audit_kind' in PANEL


def test_phase36_reports_are_scheduled_for_deletion_after_one_hour():
    assert 'AUDIT_REPORT_TTL_SECONDS = 3600' in PANEL
    assert 'async def _delete_file_later' in PANEL
    assert '_schedule_delete_file(path, delay_seconds=AUDIT_REPORT_TTL_SECONDS)' in PANEL
    assert 'Será apagado da DM e do servidor em 1h' in PANEL
    assert '_schedule_delete_message(bot, chat_id=int(user_id), message_id=getattr(sent_report, "message_id", None), delay_seconds=AUDIT_REPORT_TTL_SECONDS)' in PANEL

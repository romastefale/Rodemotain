from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_visible_branding_uses_rodemotain() -> None:
    panel = read("app/plugins/tigrao_fsm/routers/panel.py")
    html = read("app/static/join-request.html")
    main = read("app/main.py")
    texts = read("app/plugins/tigrao_fsm/texts.py")

    assert 'HOME_TEXT = "Rodemotain"' in panel
    assert "🐯 Rodemotain" in panel
    assert "Logs do Rodemotain" in panel
    assert "usar o Rodemotain aqui" in panel
    assert "Rodemotain · Solicitação de entrada" in html
    assert "<h1>Rodemotain</h1>" in html
    assert 'FastAPI(title="Rodemotain"' in main
    assert 'PANEL_TITLE = "Rodemotain"' in texts


def test_technical_command_and_env_names_are_preserved() -> None:
    panel = read("app/plugins/tigrao_fsm/routers/panel.py")
    settings = read("app/config/settings.py")
    assert "/tigrao" in panel
    assert "TIGRAO_BOT_ACCESS_USER_IDS" in settings

from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_access_variable_is_single_public_authorization_variable(monkeypatch):
    monkeypatch.setenv("TIGRAO_BOT_ACCESS_USER_IDS", "111,222")
    monkeypatch.delenv("CODE_OWNER_IDS", raising=False)
    monkeypatch.delenv("TIGRAO_FSM_MODERATOR_IDS", raising=False)

    import app.config.settings as settings

    settings = importlib.reload(settings)
    assert settings.TIGRAO_BOT_ACCESS_USER_IDS == frozenset({111, 222})
    assert settings.CODE_OWNER_IDS == frozenset({111, 222})


def test_moderator_features_are_not_env_toggles():
    env_example = read(".env.example")
    assert "TIGRAO_FSM_ENABLED" not in env_example
    assert "TIGRAO_FSM_DESTRUCTIVE_ACTIONS_ENABLED" not in env_example
    assert "TIGRAO_FSM_DDX_HARD_ENABLED" not in env_example
    assert "TIGRAO_FSM_REACTIONS_ENABLED" not in env_example

    settings = read("app/config/settings.py")
    assert 'TIGRAO_BOT_ACCESS_USER_IDS = _int_set_env(' in settings
    assert '_bool_env("TIGRAO_FSM_DESTRUCTIVE_ACTIONS_ENABLED"' not in settings
    assert '_bool_env("TIGRAO_FSM_DDX_HARD_ENABLED"' not in settings


def test_panel_exposes_real_features_without_feature_flag_guards():
    panel = read("app/plugins/tigrao_fsm/routers/panel.py")
    assert "Ações destrutivas indisponíveis" not in panel
    assert "DDX hard indisponível" not in panel
    assert "destructive_actions_enabled=True" in panel
    assert "ddx_enabled=True" in panel

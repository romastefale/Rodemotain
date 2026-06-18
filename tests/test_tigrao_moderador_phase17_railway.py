from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_settings_with_env(extra_env: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "BASE_URL",
        "TR3_BASE_URL",
        "DATA_DIR",
        "DATABASE_URL",
        "RAILWAY_PUBLIC_DOMAIN",
        "RAILWAY_STATIC_URL",
        "RAILWAY_VOLUME_MOUNT_PATH",
        "RUN_POLLING",
        "SET_WEBHOOK_ON_STARTUP",
    ):
        env.pop(name, None)
    env.update(extra_env)
    code = """
import json
from app.config import settings
print(json.dumps({
    "BASE_URL": settings.BASE_URL,
    "DATA_DIR": str(settings.DATA_DIR),
    "DATABASE_URL": settings.DATABASE_URL,
    "SET_WEBHOOK_ON_STARTUP": settings.SET_WEBHOOK_ON_STARTUP,
}, sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        check=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def test_railway_public_domain_becomes_base_url(tmp_path):
    data = _read_settings_with_env(
        {
            "RAILWAY_PUBLIC_DOMAIN": "moderador-production.up.railway.app",
            "RAILWAY_VOLUME_MOUNT_PATH": str(tmp_path / "railway-data"),
        }
    )
    assert data["BASE_URL"] == "https://moderador-production.up.railway.app"
    assert data["SET_WEBHOOK_ON_STARTUP"] is True


def test_base_url_has_priority_over_railway_domain(tmp_path):
    data = _read_settings_with_env(
        {
            "BASE_URL": "https://manual.example.com/",
            "RAILWAY_PUBLIC_DOMAIN": "wrong.up.railway.app",
            "RAILWAY_VOLUME_MOUNT_PATH": str(tmp_path / "railway-data"),
        }
    )
    assert data["BASE_URL"] == "https://manual.example.com"


def test_railway_volume_mount_path_becomes_data_dir(tmp_path):
    mount = tmp_path / "mounted-volume"
    data = _read_settings_with_env(
        {
            "RAILWAY_PUBLIC_DOMAIN": "moderador-production.up.railway.app",
            "RAILWAY_VOLUME_MOUNT_PATH": str(mount),
        }
    )
    assert data["DATA_DIR"] == str(mount)
    assert data["DATABASE_URL"] == f"sqlite:///{mount / 'moderador.sqlite3'}"

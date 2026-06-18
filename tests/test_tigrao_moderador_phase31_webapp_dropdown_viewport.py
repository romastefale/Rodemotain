from __future__ import annotations

from pathlib import Path


def test_phase31_join_webapp_uses_dropdown_group_picker_not_long_sequence() -> None:
    html = Path("app/static/join-request.html").read_text(encoding="utf-8")
    css = Path("app/static/join-request.css").read_text(encoding="utf-8")
    js = Path("app/static/join-request.js").read_text(encoding="utf-8")

    assert 'id="groupPickerButton"' in html
    assert 'role="combobox"' in html
    assert 'aria-expanded="false"' in html
    assert 'id="groupMenu"' in html
    assert 'role="listbox"' in html
    assert 'toggleGroupMenu' in js
    assert 'openGroupMenu' in js
    assert 'closeGroupMenu' in js
    assert '.group-menu' in css
    assert 'max-height: min(280px, calc(var(--app-height) * .42))' in css


def test_phase31_join_webapp_disables_zoom_and_tracks_telegram_viewport() -> None:
    html = Path("app/static/join-request.html").read_text(encoding="utf-8")
    css = Path("app/static/join-request.css").read_text(encoding="utf-8")
    js = Path("app/static/join-request.js").read_text(encoding="utf-8")

    assert 'maximum-scale=1' in html
    assert 'user-scalable=no' in html
    assert 'viewport-fit=cover' in html
    assert '--app-height' in css
    assert 'height: var(--app-height)' in css
    assert 'font-size: 16px' in css
    assert 'updateViewportHeight' in js
    assert 'tg.viewportHeight' in js
    assert 'viewportChanged' in js
    assert 'disableVerticalSwipes' in js

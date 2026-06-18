from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

FORBIDDEN_PATH_TOKENS = {
    "lastfm", "spotify", "canvas", "lyrics", "radiofm", "tnow", "tly",
    "songcharts", "monthfm", "weekfm", "web_music", "music_inline", "music_groups",
}

FORBIDDEN_IMPORT_FRAGMENTS = {
    "owner_manual_register",
    "app.bot.music_groups",
    "app.bot.music_inline",
    "app.bot.radiofm",
    "app.bot.tnow",
    "app.bot.tly",
    "app.services.lastfm",
    "app.services.spotify",
    "app.web_music",
}


def test_no_musical_files_or_imports_in_app():
    for path in APP.rglob("*"):
        rel = path.relative_to(ROOT).as_posix().lower()
        if path.is_file():
            for token in FORBIDDEN_PATH_TOKENS:
                assert token not in rel
        if path.suffix == ".py":
            text = path.read_text(encoding="utf-8", errors="ignore")
            lowered = text.lower()
            for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
                assert fragment not in lowered

from pathlib import Path


def test_healthz_route_is_static_ok():
    text = Path(__file__).resolve().parents[1].joinpath("app/main.py").read_text(encoding="utf-8")
    assert '@app.get("/healthz", status_code=200)' in text
    assert 'return {"status": "ok"}' in text

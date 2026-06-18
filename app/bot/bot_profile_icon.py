from __future__ import annotations

import json
import logging
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_MAX_AGE_SECONDS = 6 * 60 * 60
_SUPPORTED_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def _post_json(url: str, payload: dict[str, Any], *, timeout: int = 12) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_bytes(url: str, *, timeout: int = 20, max_bytes: int = 5_000_000) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise RuntimeError("bot profile photo exceeds maximum allowed size")
    return data


def _api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _file_url(token: str, file_path: str) -> str:
    return f"https://api.telegram.org/file/bot{token}/{urllib.parse.quote(file_path, safe='/')}"


def _cache_candidates(cache_dir: Path) -> list[Path]:
    return [cache_dir / f"bot-profile-icon{suffix}" for suffix in _SUPPORTED_SUFFIXES]


def cached_bot_profile_icon_path(cache_dir: Path) -> Path | None:
    for candidate in _cache_candidates(cache_dir):
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return None


def _is_fresh(path: Path, *, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    try:
        return (now - path.stat().st_mtime) <= CACHE_MAX_AGE_SECONDS and path.stat().st_size > 0
    except FileNotFoundError:
        return False


def _extract_largest_photo_file_id(response: dict[str, Any]) -> str | None:
    if not response.get("ok"):
        return None
    result = response.get("result") or {}
    photos = result.get("photos") or []
    if not photos:
        return None
    sizes = photos[0] or []
    if not sizes:
        return None
    largest = max(
        sizes,
        key=lambda item: int(item.get("file_size") or 0) or int(item.get("width") or 0) * int(item.get("height") or 0),
    )
    file_id = largest.get("file_id")
    return str(file_id) if file_id else None


def get_or_refresh_bot_profile_icon(token: str, cache_dir: Path) -> Path | None:
    """Baixa e guarda em cache a foto de perfil pública do bot no Telegram.

    Usa a Bot API HTTP diretamente para não depender de métodos específicos do
    wrapper aiogram. Isso mantém compatibilidade com aiogram 3.28 e permite que
    o Web App use a mesma foto pública configurada no perfil do bot.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cached_bot_profile_icon_path(cache_dir)
    if cached is not None and _is_fresh(cached):
        return cached

    try:
        me_response = _post_json(_api_url(token, "getMe"), {})
        if not me_response.get("ok"):
            raise RuntimeError(str(me_response.get("description") or "getMe failed"))
        bot_id = int((me_response.get("result") or {}).get("id"))

        photos_response = _post_json(
            _api_url(token, "getUserProfilePhotos"),
            {"user_id": bot_id, "limit": 1},
        )
        file_id = _extract_largest_photo_file_id(photos_response)
        if not file_id:
            logger.info("bot_profile_icon_not_found")
            return cached

        file_response = _post_json(_api_url(token, "getFile"), {"file_id": file_id})
        if not file_response.get("ok"):
            raise RuntimeError(str(file_response.get("description") or "getFile failed"))
        file_path = str((file_response.get("result") or {}).get("file_path") or "")
        if not file_path:
            raise RuntimeError("getFile did not return file_path")

        suffix = Path(file_path).suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            suffix = ".jpg"
        content = _download_bytes(_file_url(token, file_path))
        target = cache_dir / f"bot-profile-icon{suffix}"
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(content)
        tmp.replace(target)

        for old in _cache_candidates(cache_dir):
            if old != target:
                old.unlink(missing_ok=True)
        return target
    except Exception as exc:
        logger.warning("bot_profile_icon_refresh_failed error=%s", exc)
        return cached


def media_type_for_icon(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "image/jpeg"


def fallback_bot_icon_svg() -> bytes:
    return b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#fb923c"/>
      <stop offset="0.55" stop-color="#06b6d4"/>
      <stop offset="1" stop-color="#a855f7"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="30" fill="#0b1020"/>
  <circle cx="64" cy="64" r="52" fill="none" stroke="url(#g)" stroke-width="8"/>
  <text x="64" y="78" text-anchor="middle" font-family="Arial, sans-serif" font-size="52" font-weight="800" fill="#fff">R</text>
</svg>'''

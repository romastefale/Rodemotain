from __future__ import annotations

import asyncio
import os

import uvicorn

from app.config.settings import RUN_POLLING


def main() -> None:
    if RUN_POLLING:
        from app.main import on_startup, on_shutdown, start_polling

        async def runner() -> None:
            await on_startup()
            try:
                await start_polling()
            finally:
                await on_shutdown()

        asyncio.run(runner())
        return

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()

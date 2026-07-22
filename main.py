from __future__ import annotations

import asyncio
import logging

import uvicorn

from bot.client import create_bot
from config import get_settings
from database.connection import close_db, init_db
from web.app import create_app


async def run() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    await init_db()
    bot = create_bot(settings)
    app = create_app(settings, bot)

    server = uvicorn.Server(
        uvicorn.Config(
            app=app,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
    )

    web_task = asyncio.create_task(server.serve(), name="navi-web")
    bot_task = asyncio.create_task(
        bot.start(settings.discord_token.get_secret_value()), name="navi-discord"
    )

    try:
        done, pending = await asyncio.wait(
            {web_task, bot_task}, return_when=asyncio.FIRST_COMPLETED
        )

        for task in done:
            error = task.exception()
            if error is not None:
                raise error

        server.should_exit = True
        if not bot.is_closed():
            await bot.close()

        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    finally:
        server.should_exit = True
        if not bot.is_closed():
            await bot.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(run())

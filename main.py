from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

import uvicorn

from bot.client import create_bot
from config import get_settings
from database.connection import close_db, init_db
from web.app import create_app

BANNER = r"""
 _   _    _    __     _____
| \ | |  / \   \ \   / /_ _|
|  \| | / _ \   \ \ / / | |
| |\  |/ ___ \   \ V /  | |
|_| \_/_/   \_\   \_/  |___|
"""


async def run() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    print(BANNER)

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

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    shutdown_requests = 0

    def _on_shutdown_signal() -> None:
        nonlocal shutdown_requests
        shutdown_requests += 1
        if shutdown_requests == 1:
            print("\nCerrando NAVI de forma segura... (Ctrl+C otra vez para forzar)")
            stop_event.set()
        else:
            print("\nCierre forzado.")
            for task in (web_task, bot_task):
                task.cancel()

    installed_signals: list[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_shutdown_signal)
            installed_signals.append(sig)
        except NotImplementedError:
            pass  # Signal handlers aren't available on this platform (e.g. Windows).

    stop_task = asyncio.create_task(stop_event.wait(), name="navi-stop")

    try:
        done, _pending = await asyncio.wait(
            {web_task, bot_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )

        for task in done:
            if task is stop_task:
                continue
            error = task.exception()
            if error is not None:
                raise error
    finally:
        for sig in installed_signals:
            loop.remove_signal_handler(sig)

        server.should_exit = True
        if not bot.is_closed():
            await bot.close()

        if not stop_task.done():
            stop_task.cancel()

        # Let uvicorn/discord.py wind down on their own now that should_exit
        # and bot.close() have been signalled; only cancel if one hangs.
        for task in (web_task, bot_task):
            if task.done():
                continue
            try:
                await asyncio.wait_for(task, timeout=10)
            except Exception:
                pass

        await asyncio.gather(web_task, bot_task, stop_task, return_exceptions=True)

        await close_db()
        print("NAVI se ha detenido correctamente.")


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())
    sys.exit(0)


if __name__ == "__main__":
    main()

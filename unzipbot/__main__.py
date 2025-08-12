# In unzipbot/__main__.py

import asyncio
import os
import signal
import time

from pyrogram import idle

from config import Config

from . import LOGGER, unzipbot_client
from .helpers.database import get_lang
from .helpers.start import (
    check_logs,
    remove_expired_tasks,
    set_boot_time,
    start_cron_jobs,
)
from .i18n.messages import Messages
from .helpers.downloader import check_downloads

messages = Messages(lang_fetcher=get_lang)


async def async_shutdown_bot():
    stoptime = time.strftime("%Y/%m/%d - %H:%M:%S")
    LOGGER.info(msg=messages.get(file="main", key="STOP_TXT", extra_args=stoptime))

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]

    try:
        # This will now safely handle the cancellation of the gather() task itself
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        LOGGER.info("Asyncio tasks cancelled successfully.")

    try:
        # Check if client is running before trying to send messages
        if unzipbot_client.is_connected:
            await unzipbot_client.send_message(
                chat_id=Config.LOGS_CHANNEL,
                message_thread_id=Config.LOG_TOPIC_GENERAL,
                text=messages.get(file="main", key="STOP_TXT", extra_args=stoptime),
            )

            with open(file="unzip-bot.log", mode="rb") as doc_f:
                try:
                    await unzipbot_client.send_document(
                        chat_id=Config.LOGS_CHANNEL,
                        document=doc_f,
                        file_name=doc_f.name,
                        message_thread_id=Config.LOG_TOPIC_GENERAL
                    )
                except:
                    pass
    except Exception as e:
        LOGGER.error(
            msg=messages.get(file="main", key="ERROR_SHUTDOWN_MSG", extra_args=e)
        )
    finally:
        # --- FIX: Only stop the client if it is actually connected ---
        if unzipbot_client.is_connected:
            await unzipbot_client.stop()
        LOGGER.info(msg=messages.get(file="main", key="BOT_STOPPED"))


def handle_stop_signals(signum, frame):
    LOGGER.info(
        msg=messages.get(
            file="main",
            key="RECEIVED_STOP_SIGNAL",
            extra_args=[signal.Signals(signum).name, signum, frame],
        )
    )
    # Using asyncio.create_task is safer for event loops
    asyncio.create_task(async_shutdown_bot())


def setup_signal_handlers():
    loop = asyncio.get_event_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda s=sig: handle_stop_signals(signum=s, frame=None)
        )


async def main():
    try:
        os.makedirs(name=Config.DOWNLOAD_LOCATION, exist_ok=True)

        if os.path.exists(Config.LOCKFILE):
            os.remove(path=Config.LOCKFILE)

        with open(file=Config.LOCKFILE, mode="w"):
            pass

        LOGGER.info(msg=messages.get(file="main", key="STARTING_BOT"))
        await unzipbot_client.start()
        starttime = time.strftime("%Y/%m/%d - %H:%M:%S")

        # Added a check here as well for robustness
        if unzipbot_client.is_connected:
            await unzipbot_client.send_message(
                chat_id=Config.LOGS_CHANNEL,
                message_thread_id=Config.LOG_TOPIC_GENERAL,
                text=messages.get(file="main", key="START_TXT", extra_args=starttime),
            )
        
        await set_boot_time()
        LOGGER.info(msg=messages.get(file="main", key="CHECK_LOG"))

        if await check_logs():
            LOGGER.info(msg=messages.get(file="main", key="LOG_CHECKED"))
            setup_signal_handlers()
            await remove_expired_tasks(True)
            await start_cron_jobs()
            asyncio.create_task(check_downloads())
            if os.path.exists(Config.LOCKFILE):
                os.remove(path=Config.LOCKFILE)
            LOGGER.info(msg=messages.get(file="main", key="BOT_RUNNING"))
            await idle()
        else:
            try:
                # Added check for robustness
                if unzipbot_client.is_connected:
                    await unzipbot_client.send_message(
                        chat_id=Config.BOT_OWNER,
                        text=messages.get(
                            file="main", key="WRONG_LOG", extra_args=Config.LOGS_CHANNEL
                        ),
                    )
            except:
                pass

    except Exception as e:
        LOGGER.error(msg=messages.get(file="main", key="ERROR_MAIN_LOOP", extra_args=e))
    finally:
        if os.path.exists(Config.LOCKFILE):
            os.remove(path=Config.LOCKFILE)
        # The main shutdown call remains, but the function itself is now safe
        await async_shutdown_bot()


if __name__ == "__main__":
    unzipbot_client.run(main())
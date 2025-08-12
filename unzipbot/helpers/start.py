import asyncio
import os
import shutil
from datetime import datetime
from time import time

import aiohttp
import aiofiles
import aiocron
from pyrogram import enums
from pyrogram.errors import FloodWait
try:
    from pyrogram.errors import FloodPremiumWait  # type: ignore
except Exception:
    FloodPremiumWait = FloodWait
from config import Config
from unzipbot import LOGGER, boottime, unzipbot_client
from unzipbot.i18n.messages import Messages

from .database import (
    clear_cancel_tasks,
    clear_merge_tasks,
    clear_ongoing_tasks,
    count_ongoing_tasks,
    del_ongoing_task,
    get_boot,
    get_lang,
    get_old_boot,
    get_ongoing_tasks,
    is_boot_different,
    set_boot,
    set_old_boot,
)

async def download_url(url: str, path: str):
    """A simple async downloader for thumbnails"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    async with aiofiles.open(path, mode="wb") as f:
                        await f.write(await resp.read())
                    return True
    except Exception as e:
        LOGGER.error(f"Failed to download thumb from URL {url}: {e}")
    return False

def get_size(doc_f):
    try:
        fsize = os.stat(path=doc_f).st_size
        return fsize
    except:
        return -1


messages = Messages(lang_fetcher=get_lang)


async def check_logs():
    try:
        if Config.LOGS_CHANNEL:
            c_info = await unzipbot_client.get_chat(chat_id=Config.LOGS_CHANNEL)

            if c_info.type in (enums.ChatType.PRIVATE, enums.ChatType.BOT):
                LOGGER.error(msg=messages.get(file="start", key="PRIVATE_CHAT"))

                return False

            return True

        LOGGER.error(msg=messages.get(file="start", key="NO_LOG_ID"))

        return False
    except:
        LOGGER.error(msg=messages.get(file="start", key="ERROR_LOG_CHECK"))

        return False

async def set_boot_time():
    boot = await get_boot()
    await set_old_boot(boot)
    await set_boot(boottime)
    boot = await get_boot()
    old_boot = await get_old_boot()
    different = await is_boot_different()

    if different:
        try:
            await unzipbot_client.send_message(
                chat_id=Config.BOT_OWNER,
                text=messages.get(
                    file="start",
                    key="BOT_RESTARTED",
                    user_id=Config.BOT_OWNER,
                    extra_args=[
                        datetime.fromtimestamp(timestamp=old_boot).strftime(
                            r"%d/%m/%Y - %H:%M:%S"
                        ),
                        datetime.fromtimestamp(timestamp=boot).strftime(
                            r"%d/%m/%Y - %H:%M:%S"
                        ),
                    ],
                ),
            )
        except:
            pass  # first start obviously

        await warn_users()


async def warn_users():
    await clear_cancel_tasks()
    await clear_merge_tasks()

    if await count_ongoing_tasks() > 0:
        tasks = await get_ongoing_tasks()

        for task in tasks:
            try:
                await unzipbot_client.send_message(
                    chat_id=task.get("user_id"),
                    text=messages.get(
                        file="start", key="RESEND_TASK", user_id=task.get("user_id")
                    ),
                )
            except (FloodWait, FloodPremiumWait) as f:
                await asyncio.sleep(f.value)
                await unzipbot_client.send_message(
                    chat_id=task.get("user_id"),
                    text=messages.get(
                        file="start", key="RESEND_TASK", user_id=task.get("user_id")
                    ),
                )
            except:
                pass  # user deleted chat

        await clear_ongoing_tasks()


async def remove_expired_tasks(firststart=False):
    ongoing_tasks = await get_ongoing_tasks()
    await clear_cancel_tasks()

    if firststart:
        await clear_ongoing_tasks()

        try:
            shutil.rmtree(Config.DOWNLOAD_LOCATION)
        except:
            pass

        os.makedirs(name=Config.DOWNLOAD_LOCATION, exist_ok=True)
    else:
        for task in ongoing_tasks:
            user_id = task.get("user_id")

            if user_id != Config.BOT_OWNER:
                current_time = time()
                start_time = task.get("start_time")
                task_type = task.get("type")
                time_gap = current_time - start_time

                if task_type == "extract":
                    if time_gap > Config.MAX_TASK_DURATION_EXTRACT:
                        try:
                            await del_ongoing_task(user_id)
                            shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{user_id}")
                        except:
                            pass
                        await unzipbot_client.send_message(
                            chat_id=user_id,
                            text=messages.get(
                                file="start",
                                key="TASK_EXPIRED",
                                user_id=user_id,
                                extra_args=Config.MAX_TASK_DURATION_EXTRACT // 60,
                            ),
                        )
                elif task_type == "merge":
                    if time_gap > Config.MAX_TASK_DURATION_MERGE:
                        try:
                            await del_ongoing_task(user_id)
                            shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{user_id}")
                        except:
                            pass
                        await unzipbot_client.send_message(
                            chat_id=user_id,
                            text=messages.get(
                                file="start",
                                key="TASK_EXPIRED",
                                user_id=user_id,
                                extra_args=Config.MAX_TASK_DURATION_MERGE // 60,
                            ),
                        )


@aiocron.crontab("*/5 * * * *")
async def scheduled_remove_expired_tasks():
    await remove_expired_tasks()


async def start_cron_jobs():
    scheduled_remove_expired_tasks.start()

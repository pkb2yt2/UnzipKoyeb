import ast
import io
import os
import re
import shutil
import time
from datetime import datetime
from asyncio import create_subprocess_shell, sleep, subprocess
from contextlib import redirect_stderr, redirect_stdout
from sys import executable
from unzipbot.helpers import aria2_helper
from unzipbot.helpers.database import add_cc_to_dump, get_all_cc_dump_lines_as_set
from unzipbot.helpers.database import add_approved_user, del_approved_user, get_approved_users_list
from ..helpers.database import (
    add_cancel_task,
    del_ongoing_task,
    get_ongoing_tasks,
    del_merge_task,
    get_merge_task,
)

from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import git
import psutil
from pyrogram import enums, filters
from pyrogram.errors import FloodWait, RPCError
try:
    from pyrogram.errors import FloodPremiumWait  # type: ignore
except Exception:
    FloodPremiumWait = FloodWait  # type: ignore
from pyrogram.types import Message

from config import Config
from unzipbot import LOGGER, boottime, unzipbot_client
from unzipbot.helpers.database import (
    add_banned_user,
    add_merge_task,
    add_user,
    check_user,
    count_banned_users,
    count_ongoing_tasks,
    count_users,
    del_banned_user,
    del_ongoing_task,
    del_user,
    get_lang,
    get_maintenance,
    get_merge_task,
    get_ongoing_tasks,
    get_upload_mode,
    get_uploaded,
    get_users_list,
    set_maintenance,
)
from unzipbot.helpers.unzip_help import (
    calculate_memory_limit,
    humanbytes,
    timeformat_sec,
)
from unzipbot.i18n.buttons import Buttons
from unzipbot.i18n.messages import Messages
from unzipbot.modules.ext_script.ext_helper import get_files

# Regex for urls
https_url_regex = r"((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*"  # noqa: E501

messages = Messages(lang_fetcher=get_lang)


def sufficient_disk_space(required_space):
    disk_usage = psutil.disk_usage("/")
    free_space = disk_usage.free
    total_space = disk_usage.total
    five_percent_total = total_space * 0.05

    if free_space >= required_space and free_space >= five_percent_total:
        return True

    return False


@unzipbot_client.on_message(filters=filters.private)
async def _(_, message: Message):
    await check_user(message)
    uid = message.from_user.id

    if uid != Config.BOT_OWNER and await get_maintenance():
        await message.reply(
            text=messages.get(file="commands", key="MAINTENANCE_ON", user_id=uid)
        )

        return

    if uid == Config.BOT_OWNER:
        return

    if await count_ongoing_tasks() >= Config.MAX_CONCURRENT_TASKS:
        ogtasks = await get_ongoing_tasks()

        if not any(uid == task.get("user_id") for task in ogtasks):
            try:
                await message.reply(
                    text=messages.get(
                        file="commands",
                        key="MAX_TASKS",
                        user_id=uid,
                        extra_args=Config.MAX_CONCURRENT_TASKS,
                    )
                )
            except:
                await unzipbot_client.send_message(
                    chat_id=uid,
                    text=messages.get(
                        file="commands",
                        key="MAX_TASKS",
                        user_id=uid,
                        extra_args=Config.MAX_CONCURRENT_TASKS,
                    ),
                )

            return


@unzipbot_client.on_message(filters=filters.command(commands="start"))
async def start_bot(_, message: Message):
    try:
        await message.reply_text(
            text=messages.get(
                file="commands",
                key="START_TEXT",
                user_id=message.from_user.id,
                extra_args=message.from_user.mention,
            ),
            reply_markup=Buttons.START_BUTTON,
            disable_web_page_preview=True,
        )
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await start_bot(_=_, message=message)

@unzipbot_client.on_message(filters.command(commands="link"))
async def link_bots_command(_, message: Message):
    uid = message.from_user.id
    response_text = messages.get(file="commands", key="link_bots_intro", user_id=uid)

    if Config.LINK_BOTS:
        for name, url in Config.LINK_BOTS.items():
            response_text += messages.get(
                file="commands",
                key="link_bots_list_format",
                user_id=uid,
                extra_args=[name, url],
            )
    
    # Reply to the user
    await message.reply_text(
        text=response_text,
        disable_web_page_preview=True
    )

@unzipbot_client.on_message(filters=filters.private & filters.command(commands="clean"))
async def clean_my_files(_, message: Message):
    try:
        await message.reply_text(
            text=messages.get(
                file="commands", key="CLEAN_TXT", user_id=message.from_user.id
            ),
            reply_markup=Buttons.CLN_BTNS,
        )
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await clean_my_files(_=_, message=message)


@unzipbot_client.on_message(filters=filters.command(commands="help"))
async def help_me(_, message: Message):
    try:
        await message.reply_text(
            text=messages.get(
                file="commands", key="HELP_TXT", user_id=message.from_user.id
            ),
            reply_markup=Buttons.ME_GOIN_HOME,
        )
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await help_me(_=_, message=message)


@unzipbot_client.on_message(filters=filters.command(commands="about"))
async def about_me(_, message: Message):
    try:
        await message.reply_text(
            text=messages.get(
                file="commands",
                key="ABOUT_TXT",
                user_id=message.from_user.id,
                extra_args=Config.VERSION,
            ),
            reply_markup=Buttons.ME_GOIN_HOME,
            disable_web_page_preview=True,
        )
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await about_me(_=_, message=message)


@unzipbot_client.on_message(filters=filters.command(commands="privacy"))
async def privacy_text(_, message: Message):
    try:
        await message.reply_text(
            text=messages.get(
                file="commands", key="PRIVACY", user_id=message.from_user.id
            )
        )
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await privacy_text(_=_, message=message)


@unzipbot_client.on_message(
    filters=filters.incoming
    & filters.private
    & (filters.document | filters.regex(pattern=https_url_regex))
    & ~filters.command(commands=["eval", "exec"])
)
async def extract_archive(_, message: Message):
    try:
        if message.chat.type != enums.ChatType.PRIVATE:
            return

        user_id = message.from_user.id

        if await get_merge_task(user_id):
            return

        if os.path.exists(Config.LOCKFILE):
            await message.reply(
                text=messages.get(
                    file="commands", key="STILL_STARTING", user_id=user_id
                )
            )

            return

        download_path = f"{Config.DOWNLOAD_LOCATION}/{user_id}"

        if os.path.isdir(download_path):
            await message.reply(
                text=messages.get(
                    file="commands", key="PROCESS_RUNNING", user_id=user_id
                )
            )

            return

        unzip_msg = await message.reply(
            text=messages.get(file="commands", key="PROCESSING2", user_id=user_id),
            reply_to_message_id=message.id,
        )

        if (message.document and sufficient_disk_space(message.document.file_size)) or \
        (message.text and re.match(pattern=https_url_regex, string=message.text)):
            await unzip_msg.edit(
            text="Select an option:", # You can customize this text
            reply_markup=Buttons.HOME_CHOICE_BTNS # <-- Uses the correct "Home" menu
            )
        elif message.document and not sufficient_disk_space(message.document.file_size):
            await unzip_msg.edit(
                text=messages.get(file="commands", key="NO_SPACE", user_id=user_id)
            )
        else:
            await unzip_msg.edit(
                text=messages.get(file="commands", key="INVALID", user_id=user_id)
            )

    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await extract_archive(_=_, message=message)


@unzipbot_client.on_message(
    filters=filters.private & filters.command(commands="cancel")
)
async def cancel_task_by_user(_, message):
    idtodel = message.id - 1

    try:
        await unzipbot_client.delete_messages(
            chat_id=message.from_user.id, message_ids=idtodel
        )
    except:
        pass

    await message.reply(
        messages.get(file="commands", key="CANCELLED", user_id=message.from_user.id)
    )


@unzipbot_client.on_message(filters=filters.private & filters.command(commands="merge"))
async def merging(_, message: Message):
    try:
        merge_msg = await message.reply(
            text=messages.get(
                file="commands", key="MERGE", user_id=message.from_user.id
            )
        )
        await add_merge_task(user_id=message.from_user.id, message_id=merge_msg.id)
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await merging(_=_, message=message)

@unzipbot_client.on_message(filters.command("uploaddump") & filters.user(Config.BOT_OWNER))
async def upload_dump_to_db(_, message: Message):
    """
    One-time command for the bot owner to upload an existing dump.txt
    to the MongoDB collection.
    """
    dump_file_path = "dump.txt" # Assumes dump.txt is in the root folder
    
    # 1. Check if the file exists
    if not os.path.exists(dump_file_path):
        await message.reply_text("❌ `dump.txt` not found in the root directory. Please upload it and try again.")
        return

    # 2. Inform the user and start processing
    reply_msg = await message.reply_text("Found `dump.txt`. Starting one-time upload to the database. This may take a while...")
    
    line_count = 0
    new_entries = 0
    
    try:
        # 3. Read the file and process each line
        with open(dump_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_count += 1
                clean_line = line.strip()
                if clean_line:
                    # The add_cc_to_dump function already checks for duplicates
                    # We will call it for every line.
                    await add_cc_to_dump(clean_line)
                
                # Report progress every 1000 lines
                if line_count % 1000 == 0:
                    await reply_msg.edit_text(f"⏳ Processed {line_count} lines...")

        # 4. Final Report
        final_dump_size = len(await get_all_cc_dump_lines_as_set())
        await reply_msg.edit_text(
            f"✅ **Dump Upload Complete**\n\n"
            f"Processed **{line_count}** lines from `dump.txt`.\n"
            f"The total number of unique entries in the database is now **{final_dump_size}**."
        )

    except Exception as e:
        await reply_msg.edit_text(f"❌ An error occurred: {e}")

@unzipbot_client.on_message(filters=filters.private & filters.command(commands="done"))
async def done_merge(_, message: Message):
    try:
        await message.reply(
            text=messages.get(
                file="commands", key="DONE", user_id=message.from_user.id
            ),
            reply_markup=Buttons.MERGE_THEM_ALL,
        )
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await done_merge(_=_, message=message)


@unzipbot_client.on_message(filters=filters.private & filters.command(commands="mode"))
async def set_mode_for_user(_, message: Message):
    try:
        upload_mode = await get_upload_mode(message.from_user.id)
        await message.reply(
            text=messages.get(
                file="commands",
                key="SELECT_UPLOAD_MODE_TXT",
                user_id=message.from_user.id,
                extra_args=upload_mode,
            ),
            reply_markup=Buttons.SET_UPLOAD_MODE_BUTTONS,
        )
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await set_mode_for_user(_=_, message=message)



async def get_stats(id):
    total, used, free = shutil.disk_usage(".")
    total = humanbytes(total)
    used = humanbytes(used)
    free = humanbytes(free)
    sent = humanbytes(psutil.net_io_counters().bytes_sent)
    recv = humanbytes(psutil.net_io_counters().bytes_recv)
    cpu_usage = psutil.cpu_percent(interval=0.2)
    ram_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage("/").percent
    uptime = timeformat_sec(time.time() - boottime)
    total_users = await count_users()
    total_banned_users = await count_banned_users()
    ongoing_tasks = await count_ongoing_tasks()

    if id == Config.BOT_OWNER:
        stats_string = messages.get(
            file="commands",
            key="STATS_OWNER",
            user_id=id,
            extra_args=[
                total_users,
                total_banned_users,
                total,
                used,
                disk_usage,
                free,
                ongoing_tasks,
                sent,
                recv,
                cpu_usage,
                ram_usage,
                uptime,
            ],
        )
    else:
        stats_string = messages.get(
            file="commands",
            key="STATS",
            user_id=id,
            extra_args=[
                total,
                used,
                disk_usage,
                free,
                ongoing_tasks,
                cpu_usage,
                ram_usage,
                uptime,
            ],
        )

    return stats_string


@unzipbot_client.on_message(filters=filters.command(commands="stats"))
async def send_stats(_, message: Message):
    try:
        stats_msg = await message.reply(
            text=messages.get(
                file="commands", key="PROCESSING2", user_id=message.from_user.id
            )
        )
        stats_txt = await get_stats(message.from_user.id)
        await stats_msg.edit(text=stats_txt, reply_markup=Buttons.REFRESH_BUTTON)
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await send_stats(_=_, message=message)


async def __do_broadcast(message, user):
    try:
        await message.copy(chat_id=int(user))

        return 200
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)

        return __do_broadcast(message=message, user=user)
    except Exception:
        await del_user(user)

        return 400


@unzipbot_client.on_message(
    filters=filters.command(commands="broadcast") & filters.user(Config.BOT_OWNER)
)
async def broadcast_this(_, message: Message):
    uid = message.from_user.id
    bc_msg = await message.reply(
        text=messages.get(file="commands", key="PROCESSING2", user_id=uid)
    )
    r_msg = message.reply_to_message

    if not r_msg:
        await bc_msg.edit(messages.get(file="commands", key="BC_REPLY", user_id=uid))

        return

    users_list = await get_users_list()
    success_no = 0
    failed_no = 0
    done_no = 0
    total_users = await count_users()
    await bc_msg.edit(
        text=messages.get(
            file="commands",
            key="BC_START",
            user_id=uid,
            extra_args=[done_no, total_users],
        )
    )

    for user in users_list:
        b_cast = await __do_broadcast(message=r_msg, user=user.get("user_id"))

        if b_cast == 200:
            success_no += 1
        else:
            failed_no += 1

        done_no += 1

        if done_no % 10 == 0 or done_no == total_users:
            try:
                await bc_msg.edit(
                    text=messages.get(
                        file="commands",
                        key="BC_START",
                        user_id=uid,
                        extra_args=[done_no, total_users],
                    )
                )
            except (FloodWait, FloodPremiumWait):
                pass
    try:
        await bc_msg.edit(
            text=messages.get(
                file="commands",
                key="BC_DONE",
                user_id=uid,
                extra_args=[total_users, success_no, failed_no],
            )
        )
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value)
        await bc_msg.edit(
            text=messages.get(
                file="commands",
                key="BC_DONE",
                user_id=uid,
                extra_args=[total_users, success_no, failed_no],
            )
        )


@unzipbot_client.on_message(
    filters=filters.command(commands="sendto") & filters.user(Config.BOT_OWNER)
)
async def send_this(_, message: Message):
    uid = message.from_user.id
    sd_msg = await message.reply(
        text=messages.get(file="commands", key="PROCESSING2", user_id=uid)
    )
    r_msg = message.reply_to_message

    if not r_msg:
        await sd_msg.edit(
            text=messages.get(file="commands", key="SEND_REPLY", user_id=uid)
        )

        return

    try:
        user_id = message.text.split(sep=None, maxsplit=1)[1]
    except:
        await sd_msg.edit(
            text=messages.get(file="commands", key="PROVIDE_UID", user_id=uid)
        )

        return

    await sd_msg.edit(text=messages.get(file="commands", key="SENDING", user_id=uid))
    send = await __do_broadcast(message=r_msg, user=user_id)

    if send == 200:
        await sd_msg.edit(
            text=messages.get(
                file="commands", key="SEND_SUCCESS", user_id=uid, extra_args=user_id
            )
        )
    else:
        await sd_msg.edit(
            text=messages.get(
                file="commands", key="SEND_FAILED", user_id=uid, extra_args=user_id
            )
        )


@unzipbot_client.on_message(filters=filters.command(commands="report"))
async def report_this(_, message: Message):
    uid = message.from_user.id
    sd_msg = await message.reply(
        text=messages.get(file="commands", key="PROCESSING2", user_id=uid)
    )
    r_msg = message.reply_to_message

    if not r_msg:
        await sd_msg.edit(
            text=messages.get(file="commands", key="REPORT_REPLY", user_id=uid)
        )

        return

    await sd_msg.edit(text=messages.get(file="commands", key="SENDING", user_id=uid))
    await unzipbot_client.send_message(
        chat_id=Config.LOGS_CHANNEL,
        message_thread_id=Config.LOG_TOPIC_GENERAL,
        text=messages.get(
            file="commands",
            key="REPORT_TEXT",
            user_id=uid,
            extra_args=[uid, r_msg.text.markdown],
        ),
    )
    await sd_msg.edit(
        text=messages.get(file="commands", key="REPORT_DONE", user_id=uid)
    )


@unzipbot_client.on_message(
    filters=filters.command(commands="ban") & filters.user(Config.BOT_OWNER)
)
async def ban_user(_, message: Message):
    uid = message.from_user.id
    ban_msg = await message.reply(
        text=messages.get(file="commands", key="PROCESSING2", user_id=uid)
    )

    try:
        user_id = message.text.split(sep=None, maxsplit=1)[1]
    except:
        await ban_msg.edit(
            text=messages.get(file="commands", key="BAN_ID", user_id=uid)
        )

        return

    bdb = await add_banned_user(user_id)
    db = await del_user(user_id)
    text = ""

    if bdb == -1:
        text += messages.get(
            file="commands", key="ALREADY_BANNED", user_id=uid, extra_args=user_id
        )

    if db == -1:
        text += messages.get(
            file="commands", key="ALREADY_REMOVED", user_id=uid, extra_args=user_id
        )

    if text != "":
        await ban_msg.edit(text=text)
    else:
        await ban_msg.edit(
            messages.get(
                file="commands", key="USER_BANNED", user_id=uid, extra_args=user_id
            )
        )


@unzipbot_client.on_message(
    filters=filters.command(commands="unban") & filters.user(Config.BOT_OWNER)
)
async def unban_user(_, message: Message):
    uid = message.from_user.id
    unban_msg = await message.reply(
        text=messages.get(file="commands", key="PROCESSING2", user_id=uid)
    )

    try:
        user_id = message.text.split(sep=None, maxsplit=1)[1]
    except:
        await unban_msg.edit(
            text=messages.get(file="commands", key="UNBAN_ID", user_id=uid)
        )

        return

    db = await add_user(user_id)
    bdb = await del_banned_user(user_id)
    text = ""

    if db == -1:
        text += messages.get(
            file="commands", key="ALREADY_ADDED", user_id=uid, extra_args=user_id
        )

    if bdb == -1:
        text += messages.get(
            file="commands", key="ALREADY_UNBANNED", user_id=uid, extra_args=user_id
        )

    if text != "":
        await unban_msg.edit(text=text)
    else:
        await unban_msg.edit(
            text=messages.get(
                file="commands", key="UNBANNED", user_id=uid, extra_args=user_id
            )
        )


@unzipbot_client.on_message(filters=filters.command(commands="info"))
async def me_stats(_, message: Message):
    me_info = await unzipbot_client.ask(
        chat_id=message.chat.id,
        text=messages.get(file="commands", key="INFO", user_id=message.from_user.id),
    )
    await unzipbot_client.send_message(chat_id=message.chat.id, text=f"`{me_info}`")


@unzipbot_client.on_message(
    filters=filters.command(commands="user") & filters.user(Config.BOT_OWNER)
)
async def info_user(_, message: Message):
    uid = message.from_user.id
    await message.reply(text=messages.get(file="commands", key="USER", user_id=uid))
    info_user_msg = await message.reply(
        text=messages.get(file="commands", key="PROCESSING2", user_id=uid)
    )

    try:
        user_id = message.text.split(sep=None, maxsplit=1)[1]
    except:
        await info_user_msg.edit(
            text=messages.get(file="commands", key="PROVIDE_UID", user_id=uid)
        )

        return

    up_count = get_uploaded(user_id)

    if up_count == "":
        up_count = messages.get(file="commands", key="UNABLE_FETCH", user_id=uid)

    await info_user_msg.edit(
        text=messages.get(
            file="commands",
            key="USER_INFO",
            user_id=uid,
            extra_args=[user_id, up_count],
        )
    )


@unzipbot_client.on_message(
    filters=filters.command(commands="user2") & filters.user(Config.BOT_OWNER)
)
async def info_user2(_, message: Message):
    uid = message.from_user.id
    user2_msg = await message.reply(
        text=messages.get(file="commands", key="PROCESSING2", user_id=uid)
    )

    try:
        user_id = message.text.split(sep=None, maxsplit=1)[1]
    except:
        await user2_msg.edit(
            text=messages.get(file="commands", key="PROVIDE_UID2", user_id=uid)
        )

        return

    try:
        infos = await unzipbot_client.get_users(user_id)
    except:
        await user2_msg.edit(
            text=messages.get(file="commands", key="UID_UNAME_INVALID", user_id=uid)
        )

        return

    if not isinstance(user_id, int):
        try:
            user_id = infos.id
        except:
            pass

    await user2_msg.edit(
        text=messages.get(
            file="commands", key="USER2_INFO", user_id=uid, extra_args=[infos, user_id]
        )
    )


@unzipbot_client.on_message(
    filters=filters.command(commands="self") & filters.user(Config.BOT_OWNER)
)
async def info_self(_, message: Message):
    self_infos = await unzipbot_client.get_me()
    await message.reply(text=f"`{self_infos}`")


@unzipbot_client.on_message(
    filters=filters.command(commands="getthumbs") & filters.user(Config.BOT_OWNER)
)
async def get_all_thumbs(_, message: Message):
    uid = message.from_user.id
    paths = await get_files(path=Config.THUMB_LOCATION)

    if not paths:
        await message.reply(
            text=messages.get(file="commands", key="NO_THUMBS", user_id=uid)
        )

    for doc_f in paths:
        try:
            await unzipbot_client.send_document(
                chat_id=message.chat.id,
                document=doc_f,
                file_name=doc_f.split("/")[-1],
                reply_to_message_id=message.id,
                caption=messages.get(
                    file="commands", key="EXT_CAPTION", user_id=uid, extra_args=doc_f
                ),
            )
        except (FloodWait, FloodPremiumWait) as f:
            await sleep(f.value)
            await unzipbot_client.send_document(
                chat_id=message.chat.id,
                document=doc_f,
                file_name=doc_f.split("/")[-1],
                reply_to_message_id=message.id,
                caption=messages.get(
                    file="commands", key="EXT_CAPTION", user_id=uid, extra_args=doc_f
                ),
            )
        except RPCError as e:
            LOGGER.error(msg=e)


@unzipbot_client.on_message(
    filters=filters.command(commands="redbutton") & filters.user(Config.BOT_OWNER)
)
async def red_alert(_, message: Message):
    # restart the whole bot, maybe using execl
    # but also need to stop currently ongoing processes…
    await message.reply(text="🚧 WIP 🚧")


@unzipbot_client.on_message(
    filters=filters.command(commands="maintenance") & filters.user(Config.BOT_OWNER)
)
async def maintenance_mode(_, message: Message):
    mstatus = await get_maintenance()
    uid = message.from_user.id
    text = (
        messages.get(
            file="commands", key="MAINTENANCE", user_id=uid, extra_args=mstatus
        )
        + "\n\n"
        + messages.get(file="commands", key="MAINTENANCE_ASK", user_id=uid)
    )
    mess = await message.reply(text=text)

    try:
        newstate = message.text.split(sep=None, maxsplit=1)[1]
    except:
        await mess.edit(
            text=messages.get(file="commands", key="MAINTENANCE_FAIL", user_id=uid)
        )

        return

    if newstate not in ["True", "False"]:
        await mess.edit(
            text=messages.get(file="commands", key="MAINTENANCE_FAIL", user_id=uid)
        )

        return

    await set_maintenance(newstate == "True")
    await message.reply(
        text=messages.get(
            file="commands", key="MAINTENANCE_DONE", user_id=uid, extra_args=newstate
        )
    )

@unzipbot_client.on_message(
    filters=filters.command(commands="cleanall") & filters.user(Config.BOT_OWNER)
)
async def del_everything(_, message: Message):
    uid = message.from_user.id
    cleaner = await message.reply(
        text=messages.get(file="commands", key="ERASE_ALL", user_id=uid)
    )

    try:
        shutil.rmtree(Config.DOWNLOAD_LOCATION)
        await cleaner.edit(
            text=messages.get(file="commands", key="CLEANED", user_id=uid)
        )
        os.mkdir(path=Config.DOWNLOAD_LOCATION)
    except:
        await cleaner.edit(
            text=messages.get(file="commands", key="NOT_CLEANED", user_id=uid)
        )


@unzipbot_client.on_message(
    filters=filters.command(commands="cleantasks") & filters.user(Config.BOT_OWNER)
)
async def del_tasks(_, message: Message):
    ongoing_tasks = await get_ongoing_tasks()
    number = len(ongoing_tasks)
    uid = message.from_user.id
    cleaner = await message.reply(
        text=messages.get(
            file="commands", key="ERASE_TASKS", user_id=uid, extra_args=number
        )
    )

    for task in ongoing_tasks:
        user_id = task.get("user_id")
        await del_ongoing_task(user_id)

        try:
            shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{user_id}")
        except:
            pass

    await cleaner.edit(
        messages.get(
            file="commands", key="ERASE_TASKS_SUCCESS", user_id=uid, extra_args=number
        )
    )


async def send_logs(user_id):
    with open(file="unzip-bot.log", mode="rb") as doc_f:
        message = None

        try:
            message = await unzipbot_client.send_document(
                chat_id=user_id, document=doc_f, file_name=doc_f.name
            )
            LOGGER.info(
                msg=messages.get(file="commands", key="LOG_SENT", extra_args=user_id)
            )
        except (FloodWait, FloodPremiumWait) as f:
            await sleep(f.value)
            message = await unzipbot_client.send_document(
                chat_id=user_id, document=doc_f, file_name=doc_f.name
            )
        except RPCError as e:
            await unzipbot_client.send_message(chat_id=user_id, text=e)
        finally:
            doc_f.close()

            return message


def clear_logs():
    with open(file="file.txt", mode="w") as f:
        f.close()


@unzipbot_client.on_message(
    filters=filters.command(commands="logs") & filters.user(Config.BOT_OWNER)
)
async def logz(_, message: Message):
    await send_logs(message.from_user.id)


@unzipbot_client.on_message(
    filters=filters.command(commands="restart") & filters.user(Config.BOT_OWNER)
)
async def restart(_, message: Message):
    try:
        folder_to_del = os.path.dirname(os.path.abspath(Config.DOWNLOAD_LOCATION))
        shutil.rmtree(Config.DOWNLOAD_LOCATION)
        LOGGER.info(
            msg=messages.get(
                file="commands", key="DELETED_FOLDER", extra_args=folder_to_del
            )
        )
    except:
        pass

    restarttime = time.strftime("%Y/%m/%d - %H:%M:%S")
    await message.reply_text(
        text=messages.get(
            file="commands",
            key="RESTARTED_AT",
            user_id=message.from_user.id,
            extra_args=restarttime,
        ),
        quote=True,
    )
    log_message = await send_logs(message.from_user.id)

    if log_message:
        await log_message.forward(
            chat_id=Config.LOGS_CHANNEL,
            message_thread_id=Config.LOG_TOPIC_GENERAL
        )

    LOGGER.info(
        msg=messages.get(
            file="commands", key="RESTARTING", extra_args=message.from_user.id
        )
    )
    clear_logs()
    os.execl(executable, executable, "-m", "unzipbot")


@unzipbot_client.on_message(
    filters=filters.command(commands="gitpull") & filters.user(Config.BOT_OWNER)
)
async def pull_updates(_, message: Message):
    uid = message.from_user.id
    git_reply = await message.reply(
        text=messages.get(file="commands", key="PULLING", user_id=uid)
    )
    repo = git.Repo(path="/app")
    current = repo.head.commit
    repo.remotes.origin.pull()

    if current != repo.head.commit:
        await git_reply.edit(
            text=messages.get(file="commands", key="PULLED", user_id=uid)
        )
        await restart(_=_, message=message)
    else:
        await git_reply.edit(
            text=messages.get(file="commands", key="NO_PULL", user_id=uid)
        )


@unzipbot_client.on_message(filters=filters.command(commands="donate"))
async def donate_help(_, message: Message):
    await message.reply(
        text=messages.get(
            file="commands", key="DONATE_TEXT", user_id=message.from_user.id
        )
    )


@unzipbot_client.on_message(filters=filters.command(commands="vip"))
async def vip_help(_, message: Message):
    await message.reply(
        text=messages.get(file="commands", key="VIP_INFO", user_id=message.from_user.id)
    )


@unzipbot_client.on_message(
    filters=filters.command(commands="dbexport") & filters.user(Config.BOT_OWNER)
)
async def export_db(_, message):
    # Will use https://www.mongodb.com/docs/database-tools/mongoexport/ on command
    # to export as CSV
    await message.reply("🚧 WIP 🚧")


@unzipbot_client.on_message(filters=filters.command(commands="commands"))
async def getall_cmds(_, message):
    await message.reply(
        messages.get(
            file="commands", key="COMMANDS_LIST", user_id=message.from_user.id
        ),
        disable_web_page_preview=True,
    )


@unzipbot_client.on_message(
    filters=filters.command(commands="admincmd") & filters.user(Config.BOT_OWNER)
)
async def getadmin_cmds(_, message):
    await message.reply(
        messages.get(file="commands", key="ADMINCMD", user_id=message.from_user.id),
        disable_web_page_preview=True,
    )


async def aexec(code, client, message):
    stdout = io.StringIO()
    stderr = io.StringIO()
    result = None

    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            try:
                result = ast.literal_eval(code)
            except SyntaxError:
                exec(
                    "async def __aexec(client, message): "
                    + "".join(f"\n {line}" for line in code.split("\n"))
                )
                await locals()["__aexec"](client, message)
            except ValueError as e:
                stderr.write(f"ValueError : {str(e)}\n")
            except TypeError as e:
                stderr.write(f"TypeError : {str(e)}\n")
            except MemoryError as e:
                stderr.write(f"MemoryError : {str(e)}\n")
            except RecursionError as e:
                stderr.write(f"RecursionError : {str(e)}\n")
        except Exception as e:
            stderr.write(f"{type(e).__name__}: {str(e)}\n")

    return stdout.getvalue(), stderr.getvalue(), result


@unzipbot_client.on_message(
    filters=filters.command(commands="eval") & filters.user(Config.BOT_OWNER)
)
async def eval_command(_, message):
    status_message = await message.reply_text("Processing ...")
    cmd = message.text.split(" ", maxsplit=1)[1]

    stdout, stderr, result = await aexec(code=cmd, client=_, message=message)
    LOGGER.info(msg="stdout: " + stdout)
    LOGGER.info(msg="stderr: " + stderr)

    if result is not None:
        evaluation = str(result)
    elif stderr.strip():
        evaluation = stderr.strip()
    elif stdout.strip():
        evaluation = stdout.strip()
    else:
        evaluation = "Success"

    final_output = (
        f"<b>EVAL</b> : <code>{cmd}</code>\n\n"
        f"<b>OUTPUT</b> :\n<code>{evaluation}</code> \n"
    )

    if len(final_output) > Config.MAX_MESSAGE_LENGTH:
        trimmed_output = f"EVAL : {cmd}\n\nOUTPUT :\n{evaluation}"

        with open(file="eval.txt", mode="w+", encoding="utf8") as out_file:
            out_file.write(str(trimmed_output))

        await message.reply_document(
            document="eval.txt", caption=cmd, reply_to_message_id=message.id
        )
        await status_message.delete()
        os.remove(path="eval.txt")
    else:
        await status_message.edit(final_output)


@unzipbot_client.on_message(
    filters=filters.command(commands="exec") & filters.user(Config.BOT_OWNER)
)
async def exec_command(_, message):
    cmd = message.text.split(" ", maxsplit=1)[1]
    memlimit = calculate_memory_limit()
    cpulimit = Config.MAX_CPU_CORES_COUNT * Config.MAX_CPU_USAGE
    ulimit_cmd = [
        "ulimit",
        "-v",
        str(memlimit),
        "&&",
        "cpulimit",
        "-l",
        str(cpulimit),
        "--",
        cmd,
    ]
    ulimit_command = " ".join(ulimit_cmd)
    process = await create_subprocess_shell(
        cmd=ulimit_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        executable="/bin/bash",
    )
    stdout, stderr = await process.communicate()
    e = stderr.decode(encoding="utf-8", errors="replace")
    o = stdout.decode(encoding="utf-8", errors="replace")

    e = e or "No error"
    o = o or "No output"
    OUTPUT = f"**COMMAND :**\n`{cmd}`\n\n**OUTPUT :**\n`{o}`\n\n**ERROR :**\n`{e}`"

    if len(OUTPUT) > Config.MAX_MESSAGE_LENGTH:
        T_OUTPUT = f"COMMAND :\n{cmd}\n\nOUTPUT :\n{o}\n\nERROR :\n{e}"

        with io.BytesIO(str.encode(self=T_OUTPUT)) as out_file:
            out_file.name = "exec.txt"
            await message.reply_document(
                document=out_file, caption=f"`{cmd}`", reply_to_message_id=message.id
            )
    else:
        await message.reply_text(OUTPUT)

@unzipbot_client.on_message(filters.command("getdump") & filters.user(Config.BOT_OWNER))
async def get_full_dump(_, message: Message):
    """
    Owner-only command to fetch all entries from the cc_dump collection,
    create a dump.txt file, and send it.
    """
    reply_msg = await message.reply_text("`Fetching all dump entries from the database...`")
    
    # Fetch all dump lines from the database
    dump_lines = await get_all_cc_dump_lines_as_set() #
    
    if not dump_lines:
        await reply_msg.edit_text("⚠️ The database dump is currently empty.")
        return
        
    # Write to a temporary file
    temp_dump_path = "full_dump.txt"
    with open(temp_dump_path, 'w', encoding='utf-8') as f:
        for line in sorted(list(dump_lines)): # Sorting for a consistent order
            f.write(f"{line}\n")
            
    # Send the file
    caption = f"✅ Full CC dump generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\nContains {len(dump_lines)} unique entries."
    await message.reply_document(
        document=temp_dump_path,
        caption=caption
    )
    
    # Clean up
    await reply_msg.delete()
    os.remove(temp_dump_path)

@unzipbot_client.on_message(filters.command("approve") & filters.user(Config.BOT_OWNER))
async def approve_user_command(_, message: Message):
    try:
        user_id_to_approve = int(message.text.split(None, 1)[1])
        result = await add_approved_user(user_id_to_approve)
        if result == -1:
            await message.reply_text(f"User `{user_id_to_approve}` is already approved.")
        else:
            await message.reply_text(f"✅ User `{user_id_to_approve}` has been approved to use the bot.")
    except (ValueError, IndexError):
        await message.reply_text("Please use the format: `/approve USER_ID`")

@unzipbot_client.on_message(filters.command("disapprove") & filters.user(Config.BOT_OWNER))
async def disapprove_user_command(_, message: Message):
    try:
        user_id_to_disapprove = int(message.text.split(None, 1)[1])
        result = await del_approved_user(user_id_to_disapprove)
        if result == -1:
            await message.reply_text(f"User `{user_id_to_disapprove}` was not found in the approved list.")
        else:
            await message.reply_text(f"❌ User `{user_id_to_disapprove}` has been disapproved.")
    except (ValueError, IndexError):
        await message.reply_text("Please use the format: `/disapprove USER_ID`")

@unzipbot_client.on_message(filters.command("listapproved") & filters.user(Config.BOT_OWNER))
async def list_approved_command(_, message: Message):
    approved_list = await get_approved_users_list()
    if not approved_list:
        await message.reply_text("The approved users list is currently empty.")
        return
        
    msg = "👤 **Approved Users:**\n"
    for user_doc in approved_list:
        msg += f"- `{user_doc['approved_user_id']}`\n"
    await message.reply_text(msg)

@unzipbot_client.on_message(filters.private & filters.regex(r"/cancel_"))
async def cancel_aria_download(_, message: Message):
    """
    Handler to cancel an ongoing aria2c download.
    """
    user_id = message.from_user.id
    # Extract GID from the command, e.g., /cancel_4e8b24f125a21707
    gid = message.text.split("_")[-1]

    try:
        # Get the download from aria2c
        download = aria2_helper.aria2.get_download(gid)

        if not download:
            await message.reply_text("Download not found in active queue (already completed or cancelled).")
            return

        # Stop and remove the download from aria2c
        aria2_helper.aria2.remove([download], force=True, files=True)
        
        # Clean up the bot's internal tracking
        if gid in aria2_helper.tracking:
            del aria2_helper.tracking[gid]
        
        await del_ongoing_task(user_id)
        
        # Clean up the download directory
        try:
            shutil.rmtree(download.dir)
        except FileNotFoundError:
            pass # Directory already gone, which is fine

        await message.reply_text(f"✅ Download successfully cancelled: `{download.name}`")

    except Exception as e:
        LOGGER.error(f"Error while cancelling download {gid}: {e}")
        await message.reply_text(f"An error occurred while trying to cancel the download.\n\n`{e}`\n\nYou may need to use `/clean` as a fallback.")

@unzipbot_client.on_message(filters=filters.private & filters.command("cancel"))
async def universal_cancel_command(_, message: Message):
    """
    A universal command to cancel all ongoing tasks for a user.
    This includes Aria2c downloads, Pyrogram downloads, and database entries.
    """
    user_id = message.from_user.id
    was_cancelled = False
    response_msg = []

    # 1. Cancel active Aria2c downloads
    gid_to_cancel = None
    # Iterate through a copy of the tracking dictionary
    for gid, task_info in list(aria2_helper.tracking.items()):
        # Ensure the task_info is for the user who sent /cancel
        if task_info.get('message') and task_info['message'].from_user.id == user_id:
            gid_to_cancel = gid
            break
    
    if gid_to_cancel:
        try:
            download = aria2_helper.aria2.get_download(gid_to_cancel)
            # Only cancel if it's actually active
            if not download.is_complete and not download.has_failed:
                aria2_helper.aria2.remove([download], force=True, files=True)
                response_msg.append(f"Stopped active download: `{download.name}`.")
                # The downloader poller will automatically handle cleanup of the tracking dict
                was_cancelled = True
        except Exception as e:
            LOGGER.error(f"Error during Aria2c cancellation for GID {gid_to_cancel}: {e}")
            response_msg.append("Could not stop the active download, it may have just completed or failed.")

    # 2. Set cancel flag for active Pyrogram downloads/uploads
    # This will be picked up by the progress function on its next update
    await add_cancel_task(user_id)

    # 3. Force-delete any tasks from the database
    if await get_ongoing_tasks(user_id):
        await del_ongoing_task(user_id)
        response_msg.append("Cleared ongoing task entry from database.")
        was_cancelled = True

    if await get_merge_task(user_id):
        await del_merge_task(user_id)
        response_msg.append("Cleared active merge task from database.")
        was_cancelled = True
        
    # 4. Clean up the user's entire download directory as a final measure
    user_folder = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))
    if os.path.exists(user_folder):
        shutil.rmtree(user_folder, ignore_errors=True)
        response_msg.append("Wiped temporary files from the server.")
        
    # 5. Reply to the user
    if was_cancelled:
        final_message = "✅ **Cancellation Complete**\n\n" + "\n".join(f"• {msg}" for msg in response_msg)
        await message.reply_text(final_message)
    else:
        await message.reply_text("🤔 No active tasks were found to cancel.")



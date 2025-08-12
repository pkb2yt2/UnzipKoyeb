import os
import shutil
import requests
from asyncio import create_subprocess_shell, subprocess
from shlex import quote

from pykeyboard import InlineKeyboard
from pyrogram.types import InlineKeyboardButton

from config import Config
from unzipbot import LOGGER
from unzipbot.helpers.database import get_lang
from unzipbot.helpers.unzip_help import calculate_memory_limit, tarball_extensions
from unzipbot.i18n.messages import Messages

messages = Messages(lang_fetcher=get_lang)

import requests

async def download_from_direct_link(url, user_id, download_folder):
    headers = {
        "User-Agent": "Mozilla/5.0 (TelegramBot/1.0)",
        # Add any headers needed by target sites
    }
    try:
        r = requests.get(url, headers=headers, stream=True, timeout=30)
        r.raise_for_status()
        # Try to get filename from headers
        if 'content-disposition' in r.headers:
            import re
            fname = re.findall("filename=(.+)", r.headers['content-disposition'])
            filename = fname[0].strip('"') if fname else url.split("/")[-1]
        else:
            filename = url.split("/")[-1].split("?")[0]
            if not filename:
                filename = f"file_{user_id}"
        # Save file
        local_path = os.path.join(download_folder, filename)
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        # Return file path and filename
        return local_path, filename, None
    except requests.exceptions.RequestException as e:
        return None, None, str(e)
    except Exception as e:
        return None, None, str(e)

# Get files in directory as a list
async def get_files(path):
    path_list = [
        val
        for sublist in [
            [os.path.join(i[0], j) for j in i[2]] for i in os.walk(top=path)
        ]
        for val in sublist
    ]

    return sorted(path_list)


async def cleanup_macos_artifacts(extraction_path):
    for root, dirs, files in os.walk(top=extraction_path):
        for name in files:
            if name == ".DS_Store":
                os.remove(path=os.path.join(root, name))
        for name in dirs:
            if name == "__MACOSX":
                shutil.rmtree(os.path.join(root, name))


async def run_shell_cmds(command):
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
        command,
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
    LOGGER.info(msg=f"command : {command}")
    LOGGER.info(msg=f"stdout : {o}")
    LOGGER.info(msg=f"stderr : {e}")

    return o + "\n" + e


# Extract with 7z
async def __extract_with_7z_helper(path, archive_path, password=None):
    LOGGER.info(f"7z : {archive_path} : {path}")
    
    # Base command
    cmd = [
        "7z",
        "x",
        # 1. ADDED: The memory limit switch for 1000 MB
        "-mmem=1000m",
        f"-o{quote(path)}",
    ]

    # 2. CORRECTED: Only add the password switch if a password is provided
    if password:
        cmd.append(f"-p{quote(password)}")

    # 3. CORRECTED: Add the archive path and -y switch only once
    cmd.extend([quote(archive_path), "-y"])

    result = await run_shell_cmds(" ".join(cmd))
    return result

async def test_with_7z_helper(archive_path):
    # skipcq: PTC-W1006, SCT-A000
    password = "dont care + didnt ask + cry about it + stay mad + get real + L"
    cmd = ["7z", "t", f"-p{quote(password)}", quote(archive_path), "-y"]
    result = await run_shell_cmds(" ".join(cmd))

    return "Everything is Ok" in result


async def __extract_with_unrar_helper(path, archive_path, password=None):
    LOGGER.info(f"unrar : {archive_path} : {path}")

    if password:
        cmd = [
            "unrar",
            "x",
            quote(archive_path),
            quote(path),
            f"-p{quote(password)}",
            "-y",
        ]
    else:
        cmd = ["unrar", "x", quote(archive_path), quote(path), "-y"]

    result = await run_shell_cmds(" ".join(cmd))

    return result


async def test_with_unrar_helper(archive_path):
    # skipcq: PTC-W1006, SCT-A000
    password = "dont care + didnt ask + cry about it + stay mad + get real + L"
    cmd = ["unrar", "t", quote(archive_path), f"-p{quote(password)}", "-y"]
    result = await run_shell_cmds(" ".join(cmd))

    return "All OK" in result


# Extract with zstd (for .tar.zst files)
async def __extract_with_zstd(path, archive_path):
    cmd = ["zstd", "-f", "--output-dir-flat", quote(path), "-d", quote(archive_path)]
    result = await run_shell_cmds(" ".join(cmd))

    return result


# Main function to extract files
async def extr_files(path, archive_path, password=None):
    os.makedirs(name=path, exist_ok=True)

    if str(archive_path).endswith(tarball_extensions):
        LOGGER.info(msg="tar")
        temp_path = path.rsplit("/", 1)[0] + "/tar_temp"
        os.makedirs(name=temp_path, exist_ok=True)
        result = await __extract_with_7z_helper(
            path=temp_path, archive_path=archive_path
        )
        filename = await get_files(temp_path)
        filename = filename[0]
        cmd = ["tar", "-xvf", quote(filename), "-C", quote(path)]
        result2 = await run_shell_cmds(" ".join(cmd))
        result += result2
        shutil.rmtree(temp_path)
    elif str(archive_path).endswith((".tar.zst", ".zst", ".tzst")):
        LOGGER.info(msg="zstd")
        os.mkdir(path=path)
        result = await __extract_with_zstd(path=path, archive_path=archive_path)
    elif str(archive_path).endswith(".rar"):
        LOGGER.info(msg="rar")

        if password:
            result = await __extract_with_unrar_helper(
                path=path, archive_path=archive_path, password=password
            )
        else:
            result = await __extract_with_unrar_helper(
                path=path, archive_path=archive_path
            )
    else:
        LOGGER.info(msg="normal archive")
        result = await __extract_with_7z_helper(
            path=path, archive_path=archive_path, password=password
        )

    LOGGER.info(msg=await get_files(path))
    await cleanup_macos_artifacts(path)

    return result


# Split files
async def split_files(iinput, ooutput, size):
    temp_location = iinput + "_temp"
    shutil.move(src=iinput, dst=temp_location)
    cmd = [
        "7z",
        "a",
        "-tzip",
        "-mx=0",
        quote(ooutput),
        quote(temp_location),
        f"-v{size}b",
    ]
    await run_shell_cmds(" ".join(cmd))
    spdir = ooutput.replace("/" + ooutput.split("/")[-1], "")
    files = await get_files(spdir)

    return files


# Merge files
async def merge_files(iinput, ooutput, file_type, password=None):
    if file_type == "volume":
        result = await __extract_with_7z_helper(
            path=ooutput, archive_path=iinput, password=password
        )
    elif file_type == "rar":
        result = await __extract_with_unrar_helper(
            path=ooutput, archive_path=iinput, password=password
        )

    return result


# Make keyboard
async def make_keyboard(paths, user_id, chat_id, log_msg_id, unziphttp, rzfile=None):
    num = 0
    i_kbd = InlineKeyboard(row_width=1)
    data = []

    data.append(
        InlineKeyboardButton(
            text=messages.get(file="buttons", key="get_combo_logs"),
            callback_data=f"get_combo_from_logs|{user_id}"
        )
    )

    if unziphttp:
        data.append(
            InlineKeyboardButton(
                text=messages.get(file="ext_helper", key="UP_ALL", user_id=user_id),
                callback_data=f"ext_a|{user_id}|{chat_id}|{unziphttp}|{rzfile}",
            )
        )
    else:
        data.append(
            InlineKeyboardButton(
                text=messages.get(file="ext_helper", key="UP_ALL", user_id=user_id),
                callback_data=f"ext_a|{user_id}|{chat_id}|{log_msg_id}|{unziphttp}",
            )
        )

    data.append(
        InlineKeyboardButton(
            text=messages.get(file="ext_helper", key="CANCEL_IT", user_id=user_id),
            callback_data="cancel_dis",
        )
    )

    for file in paths:
        if num > 10:
            break

        if unziphttp:
            data.append(
                InlineKeyboardButton(
                    text=f"{num} - {os.path.basename(file)}".encode(
                        encoding="utf-8", errors="surrogateescape"
                    ).decode(encoding="utf-8", errors="surrogateescape"),
                    callback_data=f"ext_f|{user_id}|{chat_id}|{num}|{unziphttp}|{rzfile}",
                )
            )
        else:
            data.append(
                InlineKeyboardButton(
                    text=f"{num} - {os.path.basename(file)}".encode(
                        encoding="utf-8", errors="surrogateescape"
                    ).decode(encoding="utf-8", errors="surrogateescape"),
                    callback_data=f"ext_f|{user_id}|{chat_id}|{num}|{log_msg_id}|{unziphttp}",
                )
            )

        num += 1

    i_kbd.add(*data)

    return i_kbd

async def make_keyboard_empty(user_id, chat_id, log_msg_id, unziphttp, rzfile=None):
    i_kbd = InlineKeyboard(row_width=2)
    data = []

    # Upload All button
    if unziphttp:
        data.append(
            InlineKeyboardButton(
                text=messages.get(file="ext_helper", key="UP_ALL", user_id=user_id),
                callback_data=f"ext_a|{user_id}|{chat_id}|{unziphttp}|{rzfile}",
            )
        )
    else:
        data.append(
            InlineKeyboardButton(
                text=messages.get(file="ext_helper", key="UP_ALL", user_id=user_id),
                callback_data=f"ext_a|{user_id}|{chat_id}|{log_msg_id}|{unziphttp}",
            )
        )
    # Cancel button
    data.append(
        InlineKeyboardButton(
            text=messages.get(file="ext_helper", key="CANCEL_IT", user_id=user_id), #
            callback_data="cancel_dis",
        )
    )

    i_kbd.add(*data)
    return i_kbd
import asyncio
import os
import shutil
import time

from ..helpers.progress_helper import generate_progress_message
from .aria2_helper import aria2, tracking
from .unzip_help import timeformat_sec
from unzipbot import LOGGER
last_edit_times = {}
EDIT_INTERVAL = 5  # In seconds


async def _cleanup_download(dir_path):
    """Helper to remove the entire download directory."""
    try:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
            LOGGER.info(f"Successfully cleaned up directory: {dir_path}")
    except Exception as e:
        LOGGER.error(f"Could not remove directory {dir_path}: {e}")


async def check_downloads():
    """
    Polling task that checks the status of downloads and updates progress.
    """
    while True:
        await asyncio.sleep(1)
        if not tracking:
            continue

        try:
            for gid in frozenset(tracking.keys()):
                try:
                    download = aria2.get_download(gid)
                    if not download:
                        tracking.pop(gid, None)
                        continue

                    tracked_info = tracking.get(gid)
                    if not tracked_info:
                        tracking.pop(gid, None)
                        continue
                    message = tracked_info["message"]
                    download_dir = download.dir

                    if download.is_complete:
                        LOGGER.info(
                            f"Download complete for GID {gid}. Verifying file existence in {download_dir}..."
                        )

                        # --- NEW ROBUST FILE FINDER ---
                        file_found = False
                        retries = 0
                        max_retries = 10  # Increased retries

                        while retries < max_retries:
                            # Refresh the download object state from aria2
                            download.update()

                            # Check 1: Using download.name (most reliable)
                            if download.name:
                                path_constructed = os.path.join(download.dir, download.name)
                                if os.path.exists(path_constructed):
                                    LOGGER.info(f"File verified via constructed path: {path_constructed}")
                                    file_found = True
                                    break

                            # Check 2: Using download.files list
                            if download.files:
                                path_from_files = download.files[0].path
                                if os.path.exists(path_from_files):
                                    LOGGER.info(f"File verified via direct path check: {path_from_files}")
                                    file_found = True
                                    break

                            # Check 3: Directory scan as a fallback
                            if os.path.exists(download.dir):
                                files_in_dir = [f for f in os.listdir(download.dir) if not f.endswith(".aria2")]
                                if files_in_dir:
                                    LOGGER.info(f"File verified via directory scan: {files_in_dir[0]}")
                                    file_found = True
                                    break

                            LOGGER.warning(f"File not found for GID {gid} on retry {retries+1}/{max_retries}. Waiting 1 second...")
                            await asyncio.sleep(1)
                            retries += 1
                        # --- END OF NEW FILE FINDER ---

                        if not file_found:
                            LOGGER.error(
                                f"FATAL: No archive file found in directory {download_dir} for GID {gid}."
                            )
                            await message.edit_text(
                                "❌ **Download Error:** The downloaded file could not be found on the server. Please try again."
                            )
                            await _cleanup_download(download_dir)
                            tracking.pop(gid, None)
                            continue

                        # We found it. Now we can proceed.
                        LOGGER.info(f"File successfully verified for GID {gid}.")

                        LOGGER.info(
                            f"Poller: Download {download.name} completed. Proceeding with callback."
                        )

                        popped_info = tracking.pop(gid)
                        from ..modules.callbacks import (
                            _start_extraction,
                            _start_extraction_and_find_cc,
                            _start_extraction_and_get_combo,
                            _start_extraction_and_get_cookies, 
                        )
                        if popped_info["type"] == "extract":
                            await _start_extraction(
                                message, download, popped_info["password"]
                            )
                        elif popped_info["type"] == "extract_and_find_cc":
                            await _start_extraction_and_find_cc(
                                message, download, popped_info["password"]
                            )
                        elif popped_info["type"] == "extract_and_get_combo":
                            await _start_extraction_and_get_combo(
                                message, download, popped_info["password"]
                            )
                        # --- ADD THIS NEW BLOCK ---
                        elif popped_info["type"] == "extract_and_get_cookies":
                            await _start_extraction_and_get_cookies(
                                message, download, popped_info["password"], popped_info["domains"]
                            )

                        if gid in last_edit_times:
                            del last_edit_times[gid]

                    elif download.status == "error":
                        LOGGER.error(
                            f"Poller: Download failed for {download.name} (GID: {gid}) - {download.error_message}"
                        )
                        await message.edit_text(
                            f"Sorry, download failed.\n\n`{download.error_message}`"
                        )
                        await _cleanup_download(download_dir)
                        tracking.pop(gid, None)
                        if gid in last_edit_times:
                            del last_edit_times[gid]

                    elif download.is_active:
                        now = time.time()
                        if now - last_edit_times.get(gid, 0) > EDIT_INTERVAL:
                            start_time = tracked_info.get("start_time", 0)
                            elapsed = now - start_time

                            progress_text = await generate_progress_message(
                                status="Downloading",
                                filename=download.name,
                                progress=download.progress_string(),
                                size_str=download.total_length_string(),
                                eta=download.eta_string(),
                                speed=download.download_speed_string(),
                                elapsed_time=timeformat_sec(elapsed),
                                engine="aria2c",
                                cancel_gid=gid,
                            )

                            try:
                                await message.edit_text(progress_text)
                                last_edit_times[gid] = now
                            except Exception:
                                # Message was probably deleted, stop tracking
                                try:
                                    aria2.remove([download])
                                except:
                                    pass
                                tracking.pop(gid, None)

                except Exception as e:
                    LOGGER.error(f"Error processing GID {gid}: {e}")
                    tracking.pop(gid, None)

        except Exception as e:
            LOGGER.error(f"FATAL error in download_checker main loop: {e}")
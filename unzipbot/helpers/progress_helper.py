import psutil
import shutil
import time
from unzipbot import boottime
from .unzip_help import humanbytes, timeformat_sec

PROGRESS_BAR_LENGTH = 12
PROGRESS_FILLED = "█"
PROGRESS_EMPTY = "▒"

async def get_system_stats():
    """Fetches system stats (CPU, RAM, Disk, Uptime)."""
    cpu_usage = f"{psutil.cpu_percent()}%"
    ram_usage = f"{psutil.virtual_memory().percent}%"
    disk_total, disk_used, disk_free = shutil.disk_usage('.')
    disk_free_str = f"{humanbytes(disk_free)}"
    uptime = timeformat_sec(time.time() - boottime)
    return cpu_usage, ram_usage, disk_free_str, uptime

async def generate_progress_message(
    status: str,
    filename: str,
    progress: str,
    size_str: str,
    eta: str,
    speed: str,
    elapsed_time: str,
    engine: str,
    cancel_gid: str = None
):
    """Generates the detailed, multi-line progress message."""
    # Sanitize filename to prevent markdown errors
    safe_filename = filename.replace("`", "'").replace("*", "'").replace("_", " ")
    
    # Fetch system stats for both formats
    cpu, ram, free_disk, uptime = await get_system_stats()
    
    msg = ""
    
    # NEW: Conditional formatting based on status
    if status == "Extracting":
        # Simplified format for extraction phase
        animated_bar = "[▓▓▓▓▓▓░░░░░░]" # A static "animated" bar
        msg += f"`{safe_filename}`\n"
        msg += f"**┎ 📥 {status} »** `{size_str}`\n"
        msg += f"**┃** `{animated_bar}`\n"
        msg += f"**┠ Engine:** `{engine}`\n"
        msg += f"**┖** `Processing...`\n\n"

    else:
        # Original, detailed format for downloads
        progress_bar = "[▒▒▒▒▒▒▒▒▒▒▒▒]"
        try:
            percent_float = float(progress.replace('%', ''))
            filled_count = int(percent_float / 100 * PROGRESS_BAR_LENGTH)
            empty_count = PROGRESS_BAR_LENGTH - filled_count
            progress_bar = f"[{PROGRESS_FILLED * filled_count}{PROGRESS_EMPTY * empty_count}]"
        except (ValueError, TypeError):
            pass
            
        msg += f"`{safe_filename}`\n"
        msg += f"**┎ 📥 {status} »** `{progress}`\n"
        msg += f"**┃** `{progress_bar}`\n"
        msg += f"**┠ Total:** `{size_str}`\n"
        msg += f"**┠ ETA:** `{eta}`\n"
        msg += f"**┠ Speed:** `{speed}`\n"
        msg += f"**┠ Past:** `{elapsed_time}`\n"
        msg += f"**┠ Engine:** `{engine}`\n"
        
        if cancel_gid:
            msg += f"**┖** `/cancel_{cancel_gid}`\n\n"
        else:
            msg += f"**┖** `Processing...`\n\n"

    # Common bot stats footer
    msg += f"**⌬ Bot Stats**\n"
    msg += f"**┠ CPU:** `{cpu}` | **RAM:** `{ram}`\n"
    msg += f"**┠ Uptime:** `{uptime}`\n"
    msg += f"**┖ Free:** `{free_disk}`"

    return msg

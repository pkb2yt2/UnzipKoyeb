# In unzipbot/helpers/aria2_helper.py

import aiohttp
import aria2p
import time
import os
import re
from urllib.parse import unquote, urlparse
from pyrogram.types import Message
from unzipbot import LOGGER

aria2 = None
try:
    rpc_secret = os.environ.get("RPC_SECRET", "") 
    client = aria2p.Client(host="http://localhost", port=6800, secret=rpc_secret)
    aria2 = aria2p.API(client)
except Exception as e:
    LOGGER.error(f"Failed to connect to aria2c daemon: {e}")

tracking = {}


async def _get_filename_from_headers(session, url):
    """
    Sends a HEAD request to get the filename from Content-Disposition header.
    """
    try:
        async with session.head(url, allow_redirects=True, timeout=10) as resp:
            if resp.status == 200:
                cd_header = resp.headers.get("Content-Disposition")
                if cd_header:
                    # Extracts filename*="UTF-8''..." or filename="..."
                    fname_match = re.search(r"filename(?:\*=\S+'')?=?\"?([^\"]+)\"?", cd_header)
                    if fname_match:
                        return unquote(fname_match.group(1))
    except Exception as e:
        LOGGER.warning(f"Could not get filename from headers for {url}: {e}")
    return None


async def add_download(uri: str, path: str, message: Message, password: str = None, callback_type: str = 'extract', headers=None, keywords: list = None, domains: list = None):
    """
    Asynchronously adds a URL to be downloaded by aria2c, now with a default User-Agent.
    """
    os.makedirs(path, exist_ok=True)
    filename = None

    async with aiohttp.ClientSession() as session:
        # Correctly pass BOTH the session and the uri
        filename = await _get_filename_from_headers(session, uri)

    if not filename:
        filename = os.path.basename(uri)

    base_headers = ["User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"]
    
    # If any other special headers are provided (like for Gofile), we add them.
    if headers:
        if isinstance(headers, list):
            base_headers.extend(headers)
        else:
            base_headers.append(headers)

    options = {
        'dir': path,
        'out': filename,
        'header': base_headers,
        'allow-overwrite': 'true',
        'max-connection-per-server': '16',
        'min-split-size': '10M',
        'split': '16'
    }

    try:
        if password:
            options['rpc-passwd'] = password
        
        download = aria2.add_uris([uri], options=options)
        if download:
            tracking[download.gid] = {
                'message': message, 'password': password,
                'type': callback_type, 'start_time': time.time(),
                'keywords': keywords,
                'domains': domains
            }
            LOGGER.info(f"Added download {download.gid} to tracking.")
        return download
    except Exception as e:
        LOGGER.error(f"Failed to add download to aria2c: {e}")
        return None

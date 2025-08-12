import logging
import time
from pyrogram import Client
from config import Config

boottime = time.time()
plugins = dict(root="unzipbot/modules")

unzipbot_client = Client(
    name="unzip-bot",
    bot_token=Config.BOT_TOKEN,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    plugins=plugins,
    sleep_threshold=7200,
    max_concurrent_transmissions=3,
)

logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.FileHandler(filename="unzip-bot.log"), logging.StreamHandler()],
    format="%(asctime)s - %(levelname)s - %(name)s - %(threadName)s - %(message)s",
)

LOGGER = logging.getLogger(__name__)

logging.getLogger("pyrogram.client").setLevel(logging.ERROR)

logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("aiofiles").setLevel(logging.WARNING)
logging.getLogger("dnspython").setLevel(logging.WARNING)
logging.getLogger("GitPython").setLevel(logging.WARNING)
logging.getLogger("motor").setLevel(logging.WARNING)
logging.getLogger("Pillow").setLevel(logging.WARNING)
logging.getLogger("psutil").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

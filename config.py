import os
import psutil

class Config:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BASE_LANGUAGE = "en"
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    BOT_THUMB = f"{os.path.dirname(__file__)}/bot_thumb.jpg"
    BOT_OWNER = int(os.getenv("BOT_OWNER"))
    CHUNK_SIZE = 1024 * 1024 * 10  # 10 MB
    DOWNLOAD_LOCATION = f"{os.path.dirname(__file__)}/Downloaded"
    IS_HEROKU = False
    LOCKFILE = "/tmp/unzipbot.lock"
    LOGS_CHANNEL = int(os.getenv("LOGS_CHANNEL"))
    #add your topic id from telegram super group: for below topics
    LOG_TOPIC_GENERAL = 1
    LOG_TOPIC_EXTRACTED_CC = 7
    LOG_TOPIC_COMBOS = 2306
    LOG_TOPIC_COOKIES = 2353   
    LOG_TOPIC_NETFLIX_HITS = 2401
    LOG_TOPIC_SPOTIFY_HITS = 2403
        
    MAX_CONCURRENT_TASKS = 75
    MAX_MESSAGE_LENGTH = 4096
    MAX_CPU_CORES_COUNT = psutil.cpu_count(logical=False)
    MAX_CPU_USAGE = 80
    MAX_RAM_AMOUNT_KB = -1
    MAX_RAM_USAGE = 80
    MAX_TASK_DURATION_EXTRACT = 120 * 60  # 2 hours (in seconds)
    MAX_TASK_DURATION_MERGE = 240 * 60  # 4 hours (in seconds)
    MIN_SIZE_PROGRESS = 1024 * 1024 * 50  # 50 MB
    MONGODB_URL = os.getenv("MONGODB_URL")
    MONGODB_DBNAME = os.getenv("MONGODB_DBNAME", "Unzipper_Bot")
    TG_MAX_SIZE = 2097152000
    VERSION = "7.3.0"
    GOFILE_WEBSITE_TOKEN = os.getenv("GOFILE_WEBSITE_TOKEN", "")
    LINK_BOTS = {
    "HyperLinkGenXBot": "https://t.me/HyperLinkGenXBot",
    "TCP_Filetolinkbot": "https://t.me/TCP_Filetolinkbot",
    "reaperfile2linkbot": "https://t.me/reaperfile2linkbot",
    "FileToLinkiBot": "https://t.me/FileToLinkiBot",
    "File_To_Link_2Bot": "https://t.me/File_To_Link_2Bot",
    "File_To_Link_7Bot": "https://t.me/File_To_Link_7Bot",
    "Files_To_Direct_Bot": "https://t.me/Files_To_Direct_Bot",
    "neta2_file_bot": "https://t.me/neta2_file_bot",
    "Filetolinktgcwbot": "https://t.me/Filetolinktgcwbot",
    "Rockers_File_To_Stream_Bot": "https://t.me/Rockers_File_To_Stream_Bot",
    "GetPublicLinkBot": "https://t.me/GetPublicLinkBot",
    "KingsFileToLinkBot": "https://t.me/KingsFileToLinkBot",
    "DD_Bypass_Bot": "https://t.me/DD_Bypass_Bot",
    "Ansh_Stream_Bot": "https://t.me/Ansh_Stream_Bot",
    "FileToLinkFastBot": "https://t.me/FileToLinkFastBot",
    "filetolinkhgbot": "https://t.me/filetolinkhgbot",
    "filestodirectlinkbot": "https://t.me/filestodirectlinkbot",
    "File_To_Link_4gb_2Bot": "https://t.me/File_To_Link_4gb_2Bot",
    "bmf_filesdirect_bot": "https://t.me/bmf_filesdirect_bot"
}

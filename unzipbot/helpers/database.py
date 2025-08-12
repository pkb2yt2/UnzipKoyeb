from asyncio import sleep
from datetime import datetime

import base58check
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram.errors import FloodPremiumWait, FloodWait

from config import Config
from unzipbot import unzipbot_client
from unzipbot.i18n.messages import Messages

mongodb = AsyncIOMotorClient(host=Config.MONGODB_URL)
unzip_db = mongodb[Config.MONGODB_DBNAME]


def get_lang(user_id):
    return "en"


messages = Messages(lang_fetcher=get_lang)

# Users Database
user_db = unzip_db["users_db"]
cc_dump_db = unzip_db["cc_dump"]

async def add_cc_to_dump(dump_line: str):
    """Adds a single CC dump line to the database if it doesn't exist."""
    # The dump_line itself can be the unique identifier.
    is_exist = await cc_dump_db.find_one(filter={"_id": dump_line})
    if not is_exist:
        await cc_dump_db.insert_one(document={"_id": dump_line, "added_on": datetime.now()})


async def get_all_cc_dump_lines_as_set():
    """
    Retrieves all CC dump lines from the database and returns them as a set for fast lookups.
    """
    dump_lines = set()
    async for entry in cc_dump_db.find({}, {"_id": 1}): # Only fetch the _id field
        dump_lines.add(entry["_id"])
    return dump_lines


async def add_user(user_id):
    new_user_id = int(user_id)
    is_exist = await user_db.find_one(filter={"user_id": new_user_id})

    if is_exist is not None and is_exist:
        return -1

    await user_db.insert_one(document={"user_id": new_user_id})


async def del_user(user_id):
    del_user_id = int(user_id)
    is_exist = await user_db.find_one(filter={"user_id": del_user_id})

    if is_exist is not None and is_exist:
        await user_db.delete_one(filter={"user_id": del_user_id})

    else:
        return -1


async def is_user_in_db(user_id):
    u_id = int(user_id)
    is_exist = await user_db.find_one(filter={"user_id": u_id})

    if is_exist is not None and is_exist:
        return True

    return False


async def count_users():
    users = await user_db.count_documents(filter={})

    return users


async def get_users_list():
    return [users_list async for users_list in user_db.find({})]


# Banned users database
b_user_db = unzip_db["banned_users_db"]
approved_db = unzip_db["approved_users"]

async def add_approved_user(user_id):
    new_user_id = int(user_id)
    is_exist = await approved_db.find_one(filter={"approved_user_id": new_user_id})
    if is_exist:
        return -1 # Already approved
    await approved_db.insert_one(document={"approved_user_id": new_user_id})

async def del_approved_user(user_id):
    del_user_id = int(user_id)
    is_exist = await approved_db.find_one(filter={"approved_user_id": del_user_id})
    if is_exist:
        await approved_db.delete_one(filter={"approved_user_id": del_user_id})
    else:
        return -1 # Was not approved

async def is_user_approved(user_id):
    u_id = int(user_id)
    is_exist = await approved_db.find_one(filter={"approved_user_id": u_id})
    return bool(is_exist)

async def get_approved_users_list():
    return [approved_list async for approved_list in approved_db.find({})]

async def add_banned_user(user_id):
    new_user_id = int(user_id)
    is_exist = await b_user_db.find_one(filter={"banned_user_id": new_user_id})

    if is_exist is not None and is_exist:
        return -1

    await b_user_db.insert_one(document={"banned_user_id": new_user_id})


async def del_banned_user(user_id):
    del_user_id = int(user_id)
    is_exist = await b_user_db.find_one(filter={"banned_user_id": del_user_id})

    if is_exist is not None and is_exist:
        await b_user_db.delete_one(filter={"banned_user_id": del_user_id})
    else:
        return -1


async def is_user_in_bdb(user_id):
    u_id = int(user_id)
    is_exist = await b_user_db.find_one(filter={"banned_user_id": u_id})

    if is_exist is not None and is_exist:
        return True

    return False


async def count_banned_users():
    users = await b_user_db.count_documents(filter={})

    return users


async def get_banned_users_list():
    return [banned_users_list async for banned_users_list in b_user_db.find({})]

async def check_user(message):
    uid = message.from_user.id

    # 0. Owner can always use the bot
    if uid == Config.BOT_OWNER:
        await message.continue_propagation()
        return

    # 1. Checking if user is banned
    is_banned = await is_user_in_bdb(uid)
    if is_banned:
        await message.reply(messages.get(file="database", key="BANNED", user_id=uid))
        await message.stop_propagation()
        return

    # 2. Checking if user is approved (the new logic)
    is_approved = await is_user_approved(uid)
    if not is_approved:
        await message.reply_text("❌ **Access Denied**\n\nYou are not authorized to use this bot. Please contact the owner @PKBTQ for approval.")
        await message.stop_propagation()
        return

    # 3. Checking if user is new and should be logged (the original functionality)
    is_in_db = await is_user_in_db(uid)
    if not is_in_db:
        await add_user(uid)
        try:
            firstname = message.from_user.first_name
        except:
            firstname = " "

        try:
            lastname = message.from_user.last_name
        except:
            lastname = " "

        try:
            username = message.from_user.username
        except:
            username = " "

        if firstname == " " and lastname == " " and username == " ":
            uname = message.from_user.mention
            try:
                await unzipbot_client.send_message(
                    chat_id=Config.LOGS_CHANNEL,
                    message_thread_id=Config.LOG_TOPIC_GENERAL,
                    text=messages.get(
                        file="database",
                        key="NEW_USER_BAD",
                        user_id=uid,
                        extra_args=uname,
                    ),
                    disable_web_page_preview=False,
                )
            except (FloodWait, FloodPremiumWait) as f:
                await sleep(f.value)
                # (Self-correction, adding the send_message again after sleep)
                await unzipbot_client.send_message(
                    chat_id=Config.LOGS_CHANNEL,
                    message_thread_id=Config.LOG_TOPIC_GENERAL,
                    text=messages.get(
                        file="database",
                        key="NEW_USER_BAD",
                        user_id=uid,
                        extra_args=uname,
                    ),
                    disable_web_page_preview=False,
                )
        else:
            if firstname is None: firstname = " "
            if lastname is None: lastname = " "
            if username is None: username = " "
            uname = firstname + " " + lastname
            umention = " | @" + username
            try:
                await unzipbot_client.send_message(
                    chat_id=Config.LOGS_CHANNEL,
                    message_thread_id=Config.LOG_TOPIC_GENERAL,
                    text=messages.get(
                        file="database",
                        key="NEW_USER",
                        user_id=uid,
                        extra_args=[uname, umention, uid, uid, uid],
                    ),
                    disable_web_page_preview=False,
                )
            except (FloodWait, FloodPremiumWait) as f:
                await sleep(f.value)
                # (Self-correction, adding the send_message again after sleep)
                await unzipbot_client.send_message(
                    chat_id=Config.LOGS_CHANNEL,
                    message_thread_id=Config.LOG_TOPIC_GENERAL,
                    text=messages.get(
                        file="database",
                        key="NEW_USER",
                        user_id=uid,
                        extra_args=[uname, umention, uid, uid, uid],
                    ),
                    disable_web_page_preview=False,
                )

    # If the user passes all checks, continue to other handlers
    await message.continue_propagation()

async def get_all_users():
    users = []
    banned = []

    for i in range(await count_users()):
        users.append((await get_users_list())[i]["user_id"])

    for j in range(await count_banned_users()):
        banned.append((await get_banned_users_list())[j]["banned_user_id"])

    return users, banned


# Upload mode
mode_db = unzip_db["ulmode_db"]


async def set_upload_mode(user_id, mode):
    is_exist = await mode_db.find_one(filter={"_id": user_id})

    if is_exist is not None and is_exist:
        await mode_db.update_one(
            filter={"_id": user_id}, update={"$set": {"mode": mode}}
        )
    else:
        await mode_db.insert_one(document={"_id": user_id, "mode": mode})


async def get_upload_mode(user_id):
    umode = await mode_db.find_one(filter={"_id": user_id})

    if umode is not None and umode:
        return umode.get("mode")

    return "media"


# Db for how many files user uploaded
uploaded_db = unzip_db["uploaded_count_db"]


async def get_uploaded(user_id):
    up_count = await uploaded_db.find_one(filter={"_id": user_id})

    if up_count is not None and up_count:
        return up_count.get("uploaded_files")

    return 0


async def update_uploaded(user_id, upload_count):
    is_exist = await uploaded_db.find_one(filter={"_id": user_id})

    if is_exist is not None and is_exist:
        new_count = await get_uploaded(user_id) + upload_count
        await uploaded_db.update_one(
            filter={"_id": user_id}, update={"$set": {"uploaded_files": new_count}}
        )
    else:
        await uploaded_db.insert_one(
            document={"_id": user_id, "uploaded_files": upload_count}
        )


# DB for bot data
bot_data = unzip_db["bot_data"]


async def get_boot():
    boot = await bot_data.find_one(filter={"boot": True})

    if boot is not None and boot:
        return boot.get("time")

    return None


async def set_boot(boottime):
    is_exist = await bot_data.find_one(filter={"boot": True})

    if is_exist is not None and is_exist:
        await bot_data.update_one(
            filter={"boot": True}, update={"$set": {"time": boottime}}
        )
    else:
        await bot_data.insert_one(document={"boot": True, "time": boottime})


async def set_old_boot(boottime):
    is_exist = await bot_data.find_one(filter={"old_boot": True})

    if is_exist is not None and is_exist:
        await bot_data.update_one(
            filter={"old_boot": True}, update={"$set": {"time": boottime}}
        )
    else:
        await bot_data.insert_one(document={"old_boot": True, "time": boottime})


async def get_old_boot():
    old_boot = await bot_data.find_one(filter={"old_boot": True})

    if old_boot is not None and old_boot:
        return old_boot.get("time")

    return None


async def is_boot_different():
    different = True
    is_exist = await bot_data.find_one(filter={"boot": True})
    is_exist_old = await bot_data.find_one(filter={"old_boot": True})

    if is_exist and is_exist_old and is_exist.get("time") == is_exist_old.get("time"):
        different = False

    return different


# DB for ongoing tasks
ongoing_tasks = unzip_db["ongoing_tasks"]


async def get_ongoing_tasks():
    return [ongoing_list async for ongoing_list in ongoing_tasks.find({})]


async def count_ongoing_tasks():
    tasks = await ongoing_tasks.count_documents(filter={})

    return tasks


async def add_ongoing_task(user_id, start_time, task_type):
    await ongoing_tasks.insert_one(
        document={"user_id": user_id, "start_time": start_time, "type": task_type}
    )


async def del_ongoing_task(user_id):
    is_exist = await ongoing_tasks.find_one(filter={"user_id": user_id})

    if is_exist is not None and is_exist:
        await ongoing_tasks.delete_one(filter={"user_id": user_id})
    else:
        return


async def clear_ongoing_tasks():
    await ongoing_tasks.delete_many(filter={})


# DB for cancel tasks (that's stupid)
cancel_tasks = unzip_db["cancel_tasks"]


async def get_cancel_tasks():
    return [cancel_list async for cancel_list in cancel_tasks.find({})]


async def count_cancel_tasks():
    tasks = await cancel_tasks.count_documents(filter={})

    return tasks


async def add_cancel_task(user_id):
    if not await get_cancel_task(user_id):
        await cancel_tasks.insert_one(document={"user_id": user_id})


async def del_cancel_task(user_id):
    is_exist = await cancel_tasks.find_one(filter={"user_id": user_id})

    if is_exist is not None and is_exist:
        await cancel_tasks.delete_one(filter={"user_id": user_id})
    else:
        return


async def get_cancel_task(user_id):
    is_exist = await cancel_tasks.find_one(filter={"user_id": user_id})

    return bool(is_exist is not None and is_exist)


async def clear_cancel_tasks():
    await cancel_tasks.delete_many(filter={})


# DB for merge tasks
merge_tasks = unzip_db["merge_tasks"]


async def get_merge_tasks():
    return [merge_list async for merge_list in merge_tasks.find({})]


async def count_merge_tasks():
    tasks = await merge_tasks.count_documents(filter={})

    return tasks


async def add_merge_task(user_id, message_id):
    if not await get_merge_task(user_id):
        await merge_tasks.insert_one(
            document={"user_id": user_id, "message_id": message_id}
        )
    else:
        await merge_tasks.update_one(
            filter={"user_id": user_id}, update={"$set": {"message_id": message_id}}
        )


async def del_merge_task(user_id):
    is_exist = await merge_tasks.find_one(filter={"user_id": user_id})

    if is_exist is not None and is_exist:
        await merge_tasks.delete_one(filter={"user_id": user_id})
    else:
        return


async def get_merge_task(user_id):
    is_exist = await merge_tasks.find_one(filter={"user_id": user_id})

    return bool(is_exist is not None and is_exist)


async def get_merge_task_message_id(user_id):
    is_exist = await merge_tasks.find_one(filter={"user_id": user_id})

    if is_exist is not None and is_exist:
        return is_exist.get("message_id")

    return False


async def clear_merge_tasks():
    await merge_tasks.delete_many(filter={})


# DB for maintenance mode
maintenance_mode = unzip_db["maintenance_mode"]


async def get_maintenance():
    maintenance = await maintenance_mode.find_one(filter={"maintenance": True})

    if maintenance is not None and maintenance:
        return maintenance.get("val")

    return False


async def set_maintenance(val):
    is_exist = await maintenance_mode.find_one(filter={"maintenance": True})

    if is_exist is not None and is_exist:
        await maintenance_mode.update_one(
            filter={"maintenance": True}, update={"$set": {"val": val}}
        )
    else:
        await maintenance_mode.insert_one(document={"maintenance": True, "val": val})


# DB for VIP users
vip_users = unzip_db["vip_users"]


async def add_vip_user(
    uid,
    subscription,
    ends,
    used,
    billed,
    early,
    donator,
    started,
    successful,
    gap,
    gifted,
    referral,
    lifetime,
):
    is_exist = await vip_users.find_one(filter={"_id": uid})

    if is_exist is not None and is_exist:
        await vip_users.update_one(
            filter={"_id": uid},
            update={
                "$set": {
                    "subscription": subscription,
                    "ends": ends,
                    "used": used,
                    "billed": billed,
                    "early": early,
                    "donator": donator,
                    "started": started,
                    "successful": successful,
                    "gap": gap,
                    "gifted": gifted,
                    "referral": referral,
                    "lifetime": lifetime,
                }
            },
        )
    else:
        await vip_users.insert_one(
            document={
                "_id": uid,
                "subscription": subscription,
                "ends": ends,
                "used": used,
                "billed": billed,
                "early": early,
                "donator": donator,
                "started": started,
                "successful": successful,
                "gap": gap,
                "gifted": gifted,
                "referral": referral,
                "lifetime": lifetime,
            }
        )


async def remove_vip_user(uid):
    is_exist = await vip_users.find_one(filter={"_id": uid})

    if is_exist is not None and is_exist:
        await vip_users.delete_one(filter={"_id": uid})
    else:
        return


async def is_vip(uid):
    is_exist = await vip_users.find_one(filter={"_id": uid})

    return bool(is_exist is not None and is_exist)


async def get_vip_users():
    return [vip_list async for vip_list in vip_users.find({})]


async def count_vip_users():
    users = await vip_users.count_documents(filter={})

    return users


async def get_vip_user(uid):
    is_exist = await vip_users.find_one(filter={"_id": uid})

    if is_exist is not None and is_exist:
        return is_exist

    return None


# DB for referrals
referrals = unzip_db["referrals"]


async def add_referee(uid, referral_code):
    is_exist = await referrals.find_one(filter={"_id": uid})

    if is_exist is not None and is_exist:
        await referrals.update_one(
            filter={"_id": uid},
            update={"$set": {"type": "referee", "referral_code": referral_code}},
        )
    else:
        await referrals.insert_one(
            document={"_id": uid, "type": "referee", "referral_code": referral_code}
        )


async def add_referrer(uid, referees):
    is_exist = await referrals.find_one(filter={"_id": uid})

    if is_exist is not None and is_exist:
        await referrals.update_one(
            filter={"_id": uid},
            update={"$set": {"type": "referrer", "referees": referees}},
        )
    else:
        await referrals.insert_one(
            document={"_id": uid, "type": "referrer", "referees": referees}
        )


async def get_referee(uid):
    is_exist = await referrals.find_one(filter={"_id": uid})

    if is_exist is not None and is_exist:
        return is_exist

    return None


async def get_referrer(uid):
    is_exist = await referrals.find_one(filter={"_id": uid})

    if is_exist is not None and is_exist:
        return is_exist

    return None


def get_referral_code(uid):
    return base58check.b58encode(
        val=base58check.b58encode(val=str(uid).encode(encoding="ascii"))
    ).decode(encoding="ascii")


def get_referral_uid(referral_code):
    return int(
        base58check.b58decode(
            val=base58check.b58decode(val=referral_code).decode(encoding="ascii")
        ).decode(encoding="ascii")
    )


from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from unzipbot.helpers.database import get_lang
from .messages import Messages

messages = Messages(lang_fetcher=get_lang)

class Buttons:
    # 1. Home menu for all archives/links, with more personality!
    HOME_CHOICE_BTNS = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="No Password 🔓",
                    callback_data="nopass_options"
                ),
                InlineKeyboardButton(
                    text="With Password 🔐",
                    callback_data="withpass_options"
                ),
            ],
            
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "check_netflix"),
                    callback_data="check_cookie|netflix" # New callback
                ),
                InlineKeyboardButton(
                    text=messages.get("buttons", "check_spotify"),
                    callback_data="check_cookie|spotify" # New callback
                ),
            ],            
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "get_combo_txt"),
                    callback_data="get_combo_from_txt"
                ),
            
                InlineKeyboardButton(
                    text=messages.get("buttons", "cancel_it"),
                    callback_data="cancel_dis"
                ),
            ]
        ]
    )

    # 2. The sub-menu for actions WITHOUT a password
    NOPASS_MENU_BTNS = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "unzip_btn"),
                    callback_data="unzip_archive|no_pass"
                ),
                InlineKeyboardButton(
                    text=messages.get("buttons", "get_only_cc_btn"),
                    callback_data="get_only_cc|no_pass"
                )
            ],
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "get_combo_logs"),
                    callback_data="get_combo_archive|no_pass"
                ),
                InlineKeyboardButton(
                    text="Get Cookies 🍪",
                    callback_data="get_cookies|no_pass"
                )
            ],
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "back"),
                    callback_data="back_to_home"
                )
            ]
        ]
    )

    # 3. The sub-menu for actions WITH a password
    WITHPASS_MENU_BTNS = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "unzip_btn"),
                    callback_data="unzip_archive|with_pass"
                ),
                InlineKeyboardButton(
                    text=messages.get("buttons", "get_only_cc_btn"),
                    callback_data="get_only_cc|with_pass"
                )
            ],
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "get_combo_logs"),
                    callback_data="get_combo_archive|with_pass"
                ),
                InlineKeyboardButton(
                    text="Get Cookies 🍪",
                    callback_data="get_cookies|with_pass"
                )
            ],
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "back"),
                    callback_data="back_to_home"
                )
            ]
        ]
    )

    # Start menu: All buttons loaded from language, max emoji
    START_BUTTON = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "help"),
                    callback_data="helpcallback"
                ),
                InlineKeyboardButton(
                    text=messages.get("buttons", "about"),
                    callback_data="aboutcallback"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "stats_btn"),
                    callback_data="statscallback"
                ),
                InlineKeyboardButton(
                    text=messages.get("buttons", "donate"),
                    callback_data="donatecallback"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "rate"),
                    url="https://t.me/BotsArchive/2705"
                ),
            ]
        ]
    )

    REFRESH_BUTTON = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "refresh"),
                    callback_data="statscallback|refresh"
                ),
                InlineKeyboardButton(
                    text=messages.get("buttons", "back"),
                    callback_data="megoinhome"
                ),
            ]
        ]
    )

    CHOOSE_E_F_M__BTNS = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text="🗂️", callback_data="merged|no_pass"),
                InlineKeyboardButton(text="🔐", callback_data="merged|with_pass"),
            ],
            [InlineKeyboardButton(text="❌", callback_data="cancel_dis")],
        ]
    )

    RENAME = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text="✏️ Rename", callback_data="renameit"),
                InlineKeyboardButton(text="🙅‍♂️ Skip", callback_data="norename"),
            ]
        ]
    )

    CLN_BTNS = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "clean"),
                    callback_data="cancel_dis"
                ),
                InlineKeyboardButton(
                    text=messages.get("buttons", "cancel_it"),
                    callback_data="nobully"
                ),
            ]
        ]
    )

    ME_GOIN_HOME = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "back"),
                    callback_data="megoinhome"
                )
            ]
        ]
    )

    SET_UPLOAD_MODE_BUTTONS = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "as_doc"),
                    callback_data="set_mode|doc"
                ),
                InlineKeyboardButton(
                    text=messages.get("buttons", "as_media"),
                    callback_data="set_mode|media"
                ),
            ]
        ]
    )

    I_PREFER_STOP = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "cancel_it"),
                    callback_data="canceldownload"
                )
            ]
        ]
    )

    MERGE_THEM_ALL = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "merge_btn"),
                    callback_data="merge_this"
                ),
                InlineKeyboardButton(
                    text=messages.get("buttons", "cancel_it"),
                    callback_data="cancel_dis"
                ),
            ]
        ]
    )

    RATE_ME = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=messages.get("buttons", "rate"),
                    url="https://t.me/BotsArchive/2705"
                ),
                InlineKeyboardButton(
                    text=messages.get("buttons", "donate"),
                    callback_data="donatecallback"
                ),
            ]
        ]
    )

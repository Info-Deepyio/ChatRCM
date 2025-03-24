import requests
import random
import string
import jdatetime
from datetime import datetime
import logging
import pytz
import time
from pymongo import MongoClient, errors, ReturnDocument
from functools import wraps
from collections import defaultdict

TOKEN = "812616487:OQuogUM9cV1czIJRgDFZFSrz6MBRhjZevDtQCqTD"
MONGO_URI = "mongodb://mongo:kYrkkbAQKdReFyOknupBPTRhRuDlDdja@switchback.proxy.rlwy.net:52220"
DB_NAME = "uploader_bot"
WHITELIST = ["zonercm", "id_hormoz", "dszone"]
TEHRAN_TIMEZONE = pytz.timezone('Asia/Tehran')
API_URL = f"https://tapi.bale.ai/bot{TOKEN}/"

LAST_REQUEST_TIME = defaultdict(lambda: 0)
REQUEST_DELAY = 0.1

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

client = MongoClient(MONGO_URI, maxPoolSize=50)
db = client[DB_NAME]
files_collection = db["files"]
likes_collection = db["likes"]
users_collection = db["users"]
texts_collection = db["texts"]
referrals_collection = db["referrals"]

files_collection.create_index("link_id")
likes_collection.create_index([("user_id", 1), ("link_id", 1)], unique=True)
users_collection.create_index("chat_id", unique=True)
texts_collection.create_index("text_id")
referrals_collection.create_index([("referrer_id", 1), ("referred_id", 1)], unique=True)
referrals_collection.create_index("referrer_id")

link_cache = {}
text_cache = {}
user_cache = {}

BROADCAST_STATES = defaultdict(lambda: None)
UPLOAD_STATES = defaultdict(lambda: {})
PASSWORD_REQUEST_STATES = defaultdict(lambda: None)
TEXT_UPLOAD_STATES = defaultdict(lambda: None)

session = requests.Session()

def rate_limit_and_handle_errors(func):
    @wraps(func)
    def wrapper(chat_id, *args, **kwargs):
        now = time.time()
        last_request = LAST_REQUEST_TIME[chat_id]
        time_since_last_request = now - last_request

        if time_since_last_request < REQUEST_DELAY:
            sleep_time = REQUEST_DELAY - time_since_last_request
            time.sleep(sleep_time)

        LAST_REQUEST_TIME[chat_id] = time.time()

        max_retries = 5
        for attempt in range(max_retries):
            try:
                result = func(chat_id, *args, **kwargs)
                if result and not result.get("ok"):
                    if "Too Many Requests" in result.get("error", ""):
                        delay = 2 ** attempt + random.random()
                        time.sleep(delay)
                        continue
                    else:
                        return {"ok": False, "error": result.get("error")}
                return result
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    return {"ok": False, "error": str(e)}
                delay = 2 ** attempt + random.random()
                time.sleep(delay)

    return wrapper

@rate_limit_and_handle_errors
def send_request(chat_id, method, data):
    url = API_URL + method
    try:
        response = session.post(url, json=data, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}

def generate_link(prefix=""):
    return prefix + ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_persian_datetime():
    now_tehran = datetime.now(TEHRAN_TIMEZONE)
    jdatetime_now = jdatetime.datetime.fromgregorian(datetime=now_tehran)
    return convert_to_persian_numerals(jdatetime_now.strftime("%Y/%m/%d - %H:%M"))

def convert_to_persian_numerals(text):
    return text.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))

@rate_limit_and_handle_errors
def send_panel(chat_id):
    text = (
        "🌟 بازگشت به پنل اصلی 🌟\n\n"
        f"📅 تاریخ و ساعت: {get_persian_datetime()}\n\n"
        "برای آپلود فایل، روی '📤 آپلود فایل' کلیک کنید.\n"
        "برای آپلود متن، روی '📝 آپلود متن' کلیک کنید."
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "📤 آپلود فایل", "callback_data": "upload_file"}],
            [{"text": "📝 آپلود متن", "callback_data": "upload_text"}],
            [{"text": "📢 ارسال پیام", "callback_data": "broadcast_menu"}],
            [{"text": "📊 تعداد نشر کاربران", "callback_data": "referral_stats"}]
        ]
    }
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})

@rate_limit_and_handle_errors
def send_broadcast_menu(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🖼️ تصویر", "callback_data": "broadcast_image"}],
            [{"text": "📝 متن", "callback_data": "broadcast_text"}],
            [{"text": "🔙 بازگشت", "callback_data": "back_to_panel"}]
        ]
    }
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "📢 مدیریت ارسال پیام\n\nنوع پیام را انتخاب کنید:", "reply_markup": keyboard})

@rate_limit_and_handle_errors
def ask_for_password(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ بله", "callback_data": "password_yes"}, {"text": "❌ خیر", "callback_data": "password_no"}]
        ]
    }
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "🔒 آیا فایل نیاز به رمز دارد؟", "reply_markup": keyboard})


def create_download_link_message(file_data, link_id):
    start_link = f"/start {link_id}"
    text = f"✅ فایل ذخیره شد!\n🔗 لینک:\n```\n{start_link}\n```"
    if file_data.get('password'):
        text += f"\n🔑 رمز: \n```{file_data['password']}```"
    likes_count = convert_to_persian_numerals(str(file_data.get('likes', 0)))
    downloads_count = convert_to_persian_numerals(str(file_data.get('downloads', 0)))
    keyboard = {
        "inline_keyboard": [
            [{"text": f"❤️ تعداد لایک: {likes_count}", "callback_data": f"like_{link_id}"}],
            [{"text": f"📥 تعداد دانلود: {downloads_count}", "callback_data": f"download_{link_id}"}],
        ]
    }
    return text, keyboard

@rate_limit_and_handle_errors
def send_referral_link_request(chat_id, user_id):
    text = "برای دریافت لینک نشر خود، روی دکمه زیر کلیک کنید:"
    keyboard = {
        "inline_keyboard": [
            [{"text": "🔗 دریافت لینک", "callback_data": f"get_referral_{user_id}"}]
        ]
    }
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})

@rate_limit_and_handle_errors
def send_actual_referral_link(chat_id, user_id):
    referral_link = f"https://ble.ir/uploadd_bot?start={user_id}"
    text = f"🔗 لینک اختصاصی شما:\n\n{referral_link}"
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": text})

def get_referral_stats():
    pipeline = [
        {"$group": {"_id": "$referrer_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$lookup": {
            "from": "users",
            "localField": "_id",
            "foreignField": "chat_id",
            "as": "user_info"
        }},
        {"$unwind": "$user_info"},
        {"$project": {
            "_id": 0,
            "chat_id": "$_id",
            "username": "$user_info.username",
            "first_name": "$user_info.first_name",
            "count": 1
        }}
    ]
    try:
      stats = list(referrals_collection.aggregate(pipeline))
    except errors.PyMongoError as e:
      return "❌ خطایی در دریافت آمار نشر کاربران رخ داد."

    if not stats:
        return "❌ هیچ آماری از نشر کاربران وجود ندارد."

    message_text = "📊 **آمار نشر کاربران** 📊\n\n"
    message_text += "➖➖➖➖➖➖➖➖➖➖\n"

    for stat in stats:
        username = stat.get('username', 'نامشخص')
        first_name = stat.get('first_name', 'نامشخص')
        count = convert_to_persian_numerals(str(stat['count']))

        message_text += f"👤 **نام:** {first_name}\n"
        message_text += f"🆔 **آیدی:** `{stat['chat_id']}`\n"
        message_text += f"🌐 **نام کاربری:** @{username}\n" if username else f"🌐 **نام کاربری:** ندارد\n"
        message_text += f"📈 **تعداد نشر:** {count}\n"
        message_text += "➖➖➖➖➖➖➖➖➖➖\n"

    return message_text

def record_referral(referrer_id, referred_id):
    if referrer_id == referred_id:
        return
    try:
        referrals_collection.insert_one({"referrer_id": referrer_id, "referred_id": referred_id, "timestamp": datetime.now()})
    except errors.DuplicateKeyError:
        pass
    except errors.PyMongoError as e:
        pass

def handle_file_upload(chat_id, file_id, file_name, password=None):
    link_id = generate_link()
    file_data = {
        "link_id": link_id,
        "file_id": file_id,
        "file_name": file_name,
        "likes": 0,
        "downloads": 0,
        "created_at": datetime.now(),
        "password": password
    }
    try:
        files_collection.insert_one(file_data)
        file_data_for_cache = file_data.copy()
        del file_data_for_cache["_id"]
        link_cache[link_id] = file_data_for_cache
        text, keyboard = create_download_link_message(file_data_for_cache, link_id)
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard})
    except errors.PyMongoError as e:
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "❌ خطایی در ذخیره‌سازی فایل رخ داد."})

def get_file_data(link_id):
    if link_id in link_cache:
        return link_cache[link_id].copy()

    file_data = files_collection.find_one({"link_id": link_id},
                                        {"_id": 0, "link_id": 1, "file_id": 1, "file_name": 1, "likes": 1,
                                        "downloads": 1, "password": 1})
    if file_data:
        link_cache[link_id] = file_data
        return file_data
    return None

@rate_limit_and_handle_errors
def send_stored_file(chat_id, link_id, provided_password=None):
    file_data = get_file_data(link_id)
    if not file_data:
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "❌ لینک نامعتبر."})
        return

    if file_data.get("password") and provided_password != file_data["password"]:
        if chat_id not in PASSWORD_REQUEST_STATES:
            send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "🔒 رمز را وارد کنید یا /cancel بزنید."})
            PASSWORD_REQUEST_STATES[chat_id] = link_id
            return
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "❌ رمز اشتباه. دانلود لغو شد."})
        if chat_id in PASSWORD_REQUEST_STATES:
          del PASSWORD_REQUEST_STATES[chat_id]
        return

    try:
        updated_file_data = files_collection.find_one_and_update(
            {"link_id": link_id},
            {"$inc": {"downloads": 1}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0, "link_id": 1, "file_id": 1, "file_name": 1, "likes": 1, "downloads": 1, "password": 1}
        )
    except errors.PyMongoError as e:
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "❌ خطایی در بروزرسانی فایل رخ داد."})
        return

    if updated_file_data:
      if link_id in link_cache:
        link_cache[link_id]['downloads'] = updated_file_data.get("downloads", 0)

      text, keyboard = create_download_link_message(updated_file_data, link_id)
      send_request(chat_id, "sendDocument", {"chat_id": chat_id, "document": file_data["file_id"],"reply_markup": keyboard})
    else:
      send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "❌ خطایی در بروزرسانی فایل رخ داد."})

    if chat_id in PASSWORD_REQUEST_STATES:
        del PASSWORD_REQUEST_STATES[chat_id]

def handle_text_upload(chat_id, text_message):
    text_id = generate_link("t")
    text_data = {"text_id": text_id, "text": text_message, "created_at": datetime.now()}
    try:
        texts_collection.insert_one(text_data)
        text_data_for_cache = text_data.copy()
        del text_data_for_cache["_id"]
        text_cache[text_id] = text_data_for_cache

        start_link = f"/start {text_id}"
        response_text = f"✅ متن ذخیره شد!\n🔗 لینک:\n```\n{start_link}\n```"
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": response_text, "parse_mode": "Markdown"})
    except errors.PyMongoError as e:
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "❌ خطایی در ذخیره‌سازی متن رخ داد."})

def get_text_data(text_id):
    if text_id in text_cache:
        return text_cache[text_id].copy()
    text_data = texts_collection.find_one({"text_id": text_id}, {"_id": 0, "text_id": 1, "text": 1})
    if text_data:
        text_cache[text_id] = text_data
        return text_data
    return None

@rate_limit_and_handle_errors
def send_stored_text(chat_id, text_id):
    text_data = get_text_data(text_id)
    if not text_data:
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "❌ لینک نامعتبر."})
        return
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": text_data["text"]})

def broadcast_message(chat_id, message_type, content, file_id=None):
    sent_count = 0
    errors_count = 0

    for user in users_collection.find({}, {"_id": 0, "chat_id": 1}):
        user_chat_id = user["chat_id"]
        if message_type == "text":
            result = send_request(user_chat_id, "sendMessage", {"chat_id": user_chat_id, "text": content, "parse_mode": "Markdown"})
        elif message_type == "image":
            result = send_request(user_chat_id, "sendPhoto", {"chat_id": user_chat_id, "photo": file_id, "caption": content})
        else:
            return 0, 0

        if result and result.get("ok"):
            sent_count += 1
        else:
            errors_count += 1

    report = f"✅ به {convert_to_persian_numerals(str(sent_count))} کاربر ارسال شد."
    if errors_count > 0:
        report += f"\n❌ خطا در ارسال به {convert_to_persian_numerals(str(errors_count))} کاربر."
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": report})
    return sent_count, errors_count

def handle_callback(query):
    chat_id = query["message"]["chat"]["id"]
    data = query["data"]
    user_id = query["from"]["id"]
    send_request(chat_id, "answerCallbackQuery", {"callback_query_id": query["id"]})

    if data.startswith("like_"):
        _handle_like(query)
    elif data.startswith("download_"):
        return
    elif data == "upload_file":
        _handle_upload_file(chat_id)
    elif data == "password_yes":
        _handle_password_yes(chat_id)
    elif data == "password_no":
        _handle_password_no(chat_id)
    elif data == "upload_text":
        _handle_upload_text(chat_id)
    elif data == "broadcast_menu":
        _handle_broadcast_menu(query)
    elif data == "broadcast_text":
        _handle_broadcast_text(query)
    elif data == "broadcast_image":
        _handle_broadcast_image(query)
    elif data == "back_to_panel":
        _handle_back_to_panel(chat_id)
    elif data.startswith("get_referral_"):
        _handle_get_referral(chat_id, user_id)
    elif data == "referral_stats":
        _handle_referral_stats(chat_id, user_id, query)


def _handle_like(query):
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]
    data = query["data"]
    user_id = query["from"]["id"]
    link_id = data.split("_")[1]

    file_data = get_file_data(link_id)
    if not file_data:
        return

    try:
        likes_collection.update_one(
            {"user_id": user_id, "link_id": link_id},
            {"$set": {"timestamp": datetime.now()}},
            upsert=True
        )
        updated_file_data = files_collection.find_one_and_update(
            {"link_id": link_id},
            {"$inc": {"likes": 1}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0, "link_id": 1, "file_id": 1, "file_name": 1, "likes": 1, "downloads": 1, "password": 1}
        )
        if updated_file_data:
            if link_id in link_cache:
              link_cache[link_id]['likes'] = updated_file_data.get("likes", 0)

            text, keyboard = create_download_link_message(updated_file_data, link_id)
            send_request(chat_id, "editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": keyboard})
    except errors.PyMongoError as e:
        pass

def _handle_upload_file(chat_id):
    UPLOAD_STATES[chat_id] = {"waiting_for_password": True, "password": None}
    ask_for_password(chat_id)

def _handle_password_yes(chat_id):
    if chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_password"):
        UPLOAD_STATES[chat_id]["waiting_for_password_input"] = True
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "🔑 رمز را وارد کنید:"})

def _handle_password_no(chat_id):
    if chat_id in UPLOAD_STATES:
        UPLOAD_STATES[chat_id] = {"waiting_for_file": True, "password": None}
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "📤 فایل را بفرستید."})

def _handle_upload_text(chat_id):
    TEXT_UPLOAD_STATES[chat_id] = "waiting_for_text"
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "📝 متن خود را برای آپلود وارد کنید:"})

def _handle_broadcast_menu(query):
    chat_id = query["message"]["chat"]["id"]
    username = query["from"].get("username", "")
    if username in WHITELIST:
        send_broadcast_menu(chat_id)
    else:
        send_request(chat_id, "answerCallbackQuery",
                     {"callback_query_id": query["id"], "text": "دسترسی ندارید!", "show_alert": True})

def _handle_broadcast_text(query):
    chat_id = query["message"]["chat"]["id"]
    username = query["from"].get("username", "")
    if username in WHITELIST:
        BROADCAST_STATES[chat_id] = "waiting_for_text"
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "📝 متن را وارد کنید:", "parse_mode": "Markdown"})
    else:
        send_request(chat_id, "answerCallbackQuery",
                     {"callback_query_id": query["id"], "text": "دسترسی ندارید!", "show_alert": True})

def _handle_broadcast_image(query):
    chat_id = query["message"]["chat"]["id"]
    username = query["from"].get("username", "")
    if username in WHITELIST:
        BROADCAST_STATES[chat_id] = "waiting_for_image"
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "🖼️ تصویر را به همراه کپشن (اختیاری) ارسال کنید."})
    else:
        send_request(chat_id, "answerCallbackQuery",
                     {"callback_query_id": query["id"], "text": "دسترسی ندارید!", "show_alert": True})

def _handle_back_to_panel(chat_id):
    if chat_id in BROADCAST_STATES:
        del BROADCAST_STATES[chat_id]
    send_panel(chat_id)

def _handle_referral_stats(chat_id, user_id, query):
    username = query["from"].get("username", "")
    if username in WHITELIST:
        stats_message = get_referral_stats()
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": stats_message, "parse_mode": "Markdown"})
    else:
      send_request(chat_id, "answerCallbackQuery",
                     {"callback_query_id": query["id"], "text": "دسترسی ندارید!", "show_alert": True})

def _handle_get_referral(chat_id, user_id):
    send_actual_referral_link(chat_id, user_id)

def _get_user_data(chat_id):
    if chat_id in user_cache:
        return user_cache[chat_id].copy()

    user_data = users_collection.find_one({"chat_id": chat_id},
                                         {"_id": 0, "chat_id": 1, "username": 1, "first_name": 1})
    if user_data:
        user_cache[chat_id] = user_data
        return user_data
    return None

def _update_user_data(chat_id, username, first_name):
    try:
        users_collection.update_one({"chat_id": chat_id},
                                    {"$set": {"username": username, "first_name": first_name,
                                              "last_active": datetime.now()}}, upsert=True)
        user_cache[chat_id] = {"chat_id": chat_id, "username": username, "first_name": first_name}

    except errors.PyMongoError as e:
        pass

def handle_updates(updates):
    for update in updates:
        if "message" in update:
            _handle_message(update["message"])
        elif "callback_query" in update:
            handle_callback(update["callback_query"])

def _handle_message(msg):
    chat_id = msg["chat"]["id"]
    username = msg["from"].get("username", "")
    first_name = msg["from"].get("first_name", "")
    user_id = msg["from"]["id"]

    _update_user_data(chat_id, username, first_name)

    if "text" in msg:
        text = msg["text"]
        if text == "/cancel":
            _handle_cancel(chat_id)
        elif text == "/start":
            _handle_start(chat_id, first_name)
        elif text == "/event":
            send_referral_link_request(chat_id, user_id)
        elif text == "/stats":
            _handle_user_stats(chat_id, user_id)
        elif text == "پنل" and username in WHITELIST:
            send_panel(chat_id)
        elif text.startswith("/start "):
            _handle_start_link(chat_id, text, user_id)
        elif chat_id in BROADCAST_STATES and BROADCAST_STATES[chat_id] == "waiting_for_text" and username in WHITELIST:
            _handle_broadcast_input(chat_id, text)
        elif chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_password_input"):
            _handle_password_input(chat_id, text)
        elif chat_id in PASSWORD_REQUEST_STATES:
            _handle_password_request(chat_id, text)
        elif chat_id in TEXT_UPLOAD_STATES and TEXT_UPLOAD_STATES[chat_id] == "waiting_for_text":
            _handle_text_input(chat_id, text)
    elif "document" in msg and chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_file"):
        _handle_document_input(chat_id, msg)
    elif "photo" in msg and chat_id in BROADCAST_STATES and BROADCAST_STATES[chat_id] == "waiting_for_image" and username in WHITELIST:
        _handle_image_broadcast_input(chat_id, msg)

def _handle_cancel(chat_id):
    if chat_id in BROADCAST_STATES:
        del BROADCAST_STATES[chat_id]
    elif chat_id in UPLOAD_STATES:
        del UPLOAD_STATES[chat_id]
    elif chat_id in PASSWORD_REQUEST_STATES:
        del PASSWORD_REQUEST_STATES[chat_id]
    elif chat_id in TEXT_UPLOAD_STATES:
        del TEXT_UPLOAD_STATES[chat_id]
        send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "❌ آپلود متن لغو شد."})
        return
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "❌ لغو شد."})

def _handle_start(chat_id, first_name):
    greet_text = (
        f"👋 سلام {first_name} عزیز، خوش آمدید!\n\n"
        f"📅 تاریخ و ساعت: {get_persian_datetime()}"
    )
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": greet_text, "parse_mode": "Markdown"})

def _handle_start_link(chat_id, text, referred_id):
    link_id = text.split(" ", 1)[1]

    if link_id.isdigit():
        referrer_id = int(link_id)
        record_referral(referrer_id, referred_id)
        _handle_start(chat_id, _get_user_data(chat_id).get("first_name", ""))
    elif link_id.startswith("t"):
        send_stored_text(chat_id, link_id)
    else:
        send_stored_file(chat_id, link_id)

def _handle_broadcast_input(chat_id, text):
    del BROADCAST_STATES[chat_id]
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "📤 در حال ارسال...", "parse_mode": "Markdown"})
    broadcast_message(chat_id, "text", text)


def _handle_password_input(chat_id, text):
    password = text
    UPLOAD_STATES[chat_id]["password"] = password
    del UPLOAD_STATES[chat_id]["waiting_for_password_input"]
    UPLOAD_STATES[chat_id]["waiting_for_file"] = True
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "📤 فایل را بفرستید."})

def _handle_password_request(chat_id, text):
    link_id = PASSWORD_REQUEST_STATES[chat_id]
    send_stored_file(chat_id, link_id, text)

def _handle_text_input(chat_id, text):
    del TEXT_UPLOAD_STATES[chat_id]
    handle_text_upload(chat_id, text)

def _handle_document_input(chat_id, msg):
    file_id = msg["document"]["file_id"]
    file_name = msg["document"].get("file_name", "unnamed_file")
    password = UPLOAD_STATES[chat_id].get("password")
    handle_file_upload(chat_id, file_id, file_name, password)
    del UPLOAD_STATES[chat_id]

def _handle_image_broadcast_input(chat_id, msg):
    file_id = msg["photo"][-1]["file_id"]
    caption = msg.get("caption", "")
    del BROADCAST_STATES[chat_id]
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": "📤 در حال ارسال...", "parse_mode": "Markdown"})
    broadcast_message(chat_id, "image", caption, file_id)

def _handle_user_stats(chat_id, user_id):
    user_data = _get_user_data(chat_id)
    if not user_data:
        return

    first_name = user_data.get("first_name", "کاربر")
    referral_count = referrals_collection.count_documents({"referrer_id": user_id})
    referral_count_persian = convert_to_persian_numerals(str(referral_count))

    message_text = f"👤 **{first_name}** عزیز\n\n"
    message_text += f"📈 شما {referral_count_persian} نفر را به ربات دعوت کرده‌اید."
    send_request(chat_id, "sendMessage", {"chat_id": chat_id, "text": message_text, "parse_mode": "Markdown"})

def start_bot():
    offset = 0
    logger.info("Bot started")
    while True:
        try:
            updates = send_request(None, "getUpdates", {"offset": offset, "timeout": 180, "limit": 100}) # Pass None for chat_id since it is not a per-chat request
            if updates and updates.get("result"):
                handle_updates(updates["result"])
                offset = updates["result"][-1]["update_id"] + 1
            elif not updates or not updates.get("ok"):
                time.sleep(5)
        except Exception as e:
            logger.exception(e)
            time.sleep(5)

if __name__ == "__main__":
    start_bot()

import requests
import random
import string
import time
import jdatetime
from datetime import datetime
from pymongo import MongoClient
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurations
TOKEN = "812616487:rRd1o1TYFH1uu3wMsEqX5CvrbgYPSCjO2tcUCQbf"
MONGO_URI = "mongodb://mongo:kYrkkbAQKdReFyOknupBPTRhRuDlDdja@switchback.proxy.rlwy.net:52220"
DB_NAME = "uploader_bot"
WHITELIST = ["zonercm", "id_hormoz"]
BROADCAST_STATES = {}
UPLOAD_STATES = {}
PASSWORD_REQUEST_STATES = {}

# Initialize MongoDB
client = MongoClient(MONGO_URI, maxPoolSize=50)
db = client[DB_NAME]
files_collection = db["files"]
likes_collection = db["likes"]
users_collection = db["users"]

# Create indexes
files_collection.create_index("link_id")
likes_collection.create_index([("user_id", 1), ("link_id", 1)], unique=True)
users_collection.create_index("chat_id", unique=True)

# Telegram API URL
API_URL = f"https://tapi.bale.ai/bot{TOKEN}/"

# Cache
link_cache = {}
session = requests.Session()

def send_request(method, data):
    """Send requests to Telegram API with session reuse."""
    url = API_URL + method
    try:
        response = session.post(url, json=data, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        logger.error(f"JSON decode error: {e}, Response content: {response.text}")
        return {"ok": False, "error": str(e)}

def generate_link():
    """Generate a random link ID."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_persian_time():
    """Get Persian time with Persian numerals."""
    now = jdatetime.datetime.now()
    persian_date = now.strftime("%Y/%m/%d")
    persian_time = now.strftime("%H:%M")
    persian_date = convert_to_persian_numerals(persian_date)
    persian_time = convert_to_persian_numerals(persian_time)
    return f"{persian_date} - {persian_time}"

def convert_to_persian_numerals(text):
    """Convert English numerals to Persian numerals."""
    persian_numerals = {
        '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
        '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
    }
    for en, fa in persian_numerals.items():
        text = text.replace(en, fa)
    return text

def send_panel(chat_id):
    """Send Persian panel with date/time and broadcast option."""
    current_time = get_persian_time()
    text = (
        f"🌟 بازگشت به پنل اصلی 🌟\n\n"
        f"📅 تاریخ: {current_time}\n\n"
        f"برای آپلود فایل جدید، روی دکمه‌ی '📤 آپلود فایل' کلیک کنید."
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "📤 آپلود فایل", "callback_data": "upload_file"}],
            [{"text": "📢 ارسال پیام به کل کاربر ها", "callback_data": "broadcast_menu"}]
        ]
    }
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard})

def send_broadcast_menu(chat_id):
    """Send broadcast menu options."""
    text = "📢 مدیریت ارسال پیام گروهی\n\nلطفاً نوع پیام گروهی را انتخاب کنید:"
    keyboard = {
        "inline_keyboard": [
            [{"text": "📝 ارسال متن ساده", "callback_data": "broadcast_text"}],
            [{"text": "🔙 بازگشت به منو اصلی", "callback_data": "back_to_panel"}]
        ]
    }
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard})

def ask_for_password(chat_id):
    """Asks the user if the file requires a password."""
    text = "🔒 آیا فایل شما نیاز به رمز عبور دارد؟"
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ بله", "callback_data": "password_yes"},
             {"text": "❌ خیر", "callback_data": "password_no"}]
        ]
    }
    # Immediate response:  Acknowledge user interaction *before* sending the message
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})


def handle_file_upload(chat_id, file_id, file_name, password=None):
    """Store file and send link."""
    link_id = generate_link()
    file_data = {
        "link_id": link_id, "file_id": file_id, "file_name": file_name,
        "likes": 0, "downloads": 0, "created_at": datetime.now(), "password": password
    }
    files_collection.insert_one(file_data)
    link_cache[link_id] = file_data.copy()
    del link_cache[link_id]["_id"]

    start_link = f"/start {link_id}"
    text = f"✅ فایل شما ذخیره شد!\n🔗 لینک دریافت:\n```\n{start_link}\n```"
    if password:
        text += f"\n🔑 رمز عبور فایل: ```{password}```"
    like_count = convert_to_persian_numerals("0")
    download_count = convert_to_persian_numerals("0")
    keyboard = {
        "inline_keyboard": [
            [{"text": f"❤️ {like_count}", "callback_data": f"like_{link_id}"}],
            [{"text": f"📥 {download_count}", "callback_data": f"download_{link_id}"}]
        ]
    }
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard})

def get_file_data(link_id):
    """Get file data."""
    if link_id in link_cache:
        return link_cache[link_id]
    file_data = files_collection.find_one({"link_id": link_id})
    if file_data:
        link_cache[link_id] = file_data.copy()
        del link_cache[link_id]["_id"]
        return link_cache[link_id]
    return None

def send_stored_file(chat_id, link_id, provided_password=None):
    """Retrieve and send file."""
    file_data = get_file_data(link_id)
    if file_data:
        if file_data["password"] and provided_password != file_data["password"]:
            if chat_id not in PASSWORD_REQUEST_STATES:
                send_request("sendMessage", {"chat_id": chat_id, "text": "🔒 لطفاً رمز عبور فایل را وارد کنید یا /cancel را برای لغو وارد کنید."})
                PASSWORD_REQUEST_STATES[chat_id] = link_id
                return
            else:
                send_request("sendMessage", {"chat_id": chat_id, "text": "❌ رمز عبور اشتباه است. دانلود لغو شد."})
                if chat_id in PASSWORD_REQUEST_STATES:
                    del PASSWORD_REQUEST_STATES[chat_id]
                return

        new_download_count = file_data["downloads"] + 1
        file_data["downloads"] = new_download_count
        files_collection.update_one({"link_id": link_id}, {"$set": {"downloads": new_download_count}})
        if link_id in link_cache:
            link_cache[link_id]["downloads"] = new_download_count

        likes_count = convert_to_persian_numerals(str(file_data['likes']))
        downloads_count = convert_to_persian_numerals(str(new_download_count))
        keyboard = {
            "inline_keyboard": [
                [{"text": f"❤️ {likes_count}", "callback_data": f"like_{link_id}"}],
                [{"text": f"📥 {downloads_count}", "callback_data": f"download_{link_id}"}]
            ]
        }
        send_request("sendDocument", {"chat_id": chat_id, "document": file_data["file_id"], "reply_markup": keyboard})
        if chat_id in PASSWORD_REQUEST_STATES:
            del PASSWORD_REQUEST_STATES[chat_id]
    else:
        send_request("sendMessage", {"chat_id": chat_id, "text": "❌ لینک نامعتبر است یا فایل حذف شده است."})

def broadcast_message_to_all_users(message_type, content):
    """Send a message to all users."""
    users = users_collection.find({})
    sent_count = 0
    for user in users:
        chat_id = user["chat_id"]
        if message_type == "text":
            result = send_request("sendMessage", {"chat_id": chat_id, "text": content, "parse_mode": "Markdown"})
        if result.get("ok", False):
            sent_count += 1
        else:
            logger.error(f"Could not send message to user: {chat_id}, Result: {result}")
    return sent_count

def handle_callback(query):
    """Handle button clicks."""
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]
    callback_id = query["id"]
    data = query["data"]
    user_id = query["from"]["id"]
    username = query["from"].get("username", "")

    send_request("answerCallbackQuery", {"callback_query_id": callback_id})

    if data.startswith("like_"):
        link_id = data.split("_")[1]
        file_data = files_collection.find_one({"link_id": link_id})
        if file_data:
            existing_like = likes_collection.find_one({"user_id": user_id, "link_id": link_id})
            if existing_like:
                return
            likes_collection.insert_one({"user_id": user_id, "link_id": link_id, "timestamp": datetime.now()})
            new_likes = file_data["likes"] + 1
            files_collection.update_one({"link_id": link_id}, {"$set": {"likes": new_likes}})
            if link_id in link_cache:
                link_cache[link_id]["likes"] = new_likes
            likes_count = convert_to_persian_numerals(str(new_likes))
            downloads_count = convert_to_persian_numerals(str(file_data['downloads']))
            updated_keyboard = {
                "inline_keyboard": [
                    [{"text": f"❤️ {likes_count}", "callback_data": f"like_{link_id}"}],
                    [{"text": f"📥 {downloads_count}", "callback_data": f"download_{link_id}"}]
                ]
            }
            send_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": updated_keyboard})

    elif data.startswith("download_"):
        link_id = data.split("_")[1]
        send_stored_file(chat_id, link_id)

    elif data == "upload_file":
        UPLOAD_STATES[chat_id] = {"waiting_for_file": True, "password": None}
        ask_for_password(chat_id)

    elif data == "password_yes":
        if chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_file"):
            UPLOAD_STATES[chat_id]["waiting_for_password"] = True
            # Immediate response before prompting for password
            send_request("sendMessage", {"chat_id": chat_id, "text": "🔑 لطفاً رمز عبور فایل را وارد کنید:"})

        else:
            send_request("sendMessage", {"chat_id": chat_id, "text": "لطفاً ابتدا فایل را آپلود کنید."})

    elif data == "password_no":
        if chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_file"):
            UPLOAD_STATES[chat_id]["waiting_for_file"] = False
            del UPLOAD_STATES[chat_id]["waiting_for_password"]
            send_request("sendMessage", {"chat_id": chat_id, "text": "📤 لطفاً فایل خود را برای آپلود ارسال کنید."})
        else:
            send_request("sendMessage", {"chat_id": chat_id, "text": "لطفاً ابتدا فایل را آپلود کنید."})

    elif data == "broadcast_menu":
        if username in WHITELIST:
            send_broadcast_menu(chat_id)
        else:
            send_request("answerCallbackQuery", {"callback_query_id": callback_id, "text": "شما مجوز دسترسی ندارید!", "show_alert": True})

    elif data == "broadcast_text":
        if username in WHITELIST:
            BROADCAST_STATES[chat_id] = "waiting_for_text"
            send_request("sendMessage", {"chat_id": chat_id, "text": "📝 متن پیام را وارد کنید:", "parse_mode": "Markdown"})

    elif data == "back_to_panel":
        if chat_id in BROADCAST_STATES:
            del BROADCAST_STATES[chat_id]
        send_panel(chat_id)

def handle_updates(updates):
    """Process updates."""
    for update in updates:
        try:
            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                username = msg["from"].get("username", "")
                first_name = msg["from"].get("first_name", "")
                users_collection.update_one({"chat_id": chat_id}, {"$set": {"username": username, "first_name": first_name, "last_active": datetime.now()}}, upsert=True)

                if "text" in msg:
                    text = msg["text"]

                    if text == "/cancel":
                        if chat_id in BROADCAST_STATES:
                            del BROADCAST_STATES[chat_id]
                            send_request("sendMessage", {"chat_id": chat_id, "text": "❌ لغو شد.", "parse_mode": "Markdown"})
                        elif chat_id in UPLOAD_STATES:
                            del UPLOAD_STATES[chat_id]
                            send_request("sendMessage", {"chat_id": chat_id, "text": "❌ آپلود لغو شد.", "parse_mode": "Markdown"})
                        elif chat_id in PASSWORD_REQUEST_STATES:
                            del PASSWORD_REQUEST_STATES[chat_id]
                            send_request("sendMessage", {"chat_id": chat_id, "text": "❌ دانلود لغو شد.", "parse_mode": "Markdown"})
                        return

                    if text == "/start":
                        current_time = get_persian_time()
                        # No inline keyboard for the initial /start message
                        greet_text = (
                            f"👋 سلام {first_name} عزیز، به ربات آپلودر خوش آمدید!\n\n"
                            f"📅 تاریخ: {current_time}\n\n" 
                        )
                        send_request("sendMessage", {"chat_id": chat_id, "text": greet_text, "parse_mode": "Markdown"})
                        continue

                    if text == "پنل" and username in WHITELIST:
                        send_panel(chat_id)
                        continue

                    if text.startswith("/start "):
                        parts = text.split()
                        if len(parts) > 1:
                            link_id = parts[1]
                            send_stored_file(chat_id, link_id)
                        continue

                    if chat_id in BROADCAST_STATES and BROADCAST_STATES[chat_id] == "waiting_for_text":
                        if username in WHITELIST:
                            del BROADCAST_STATES[chat_id]
                            send_request("sendMessage", {"chat_id": chat_id, "text": "📤 در حال ارسال...", "parse_mode": "Markdown"})
                            sent_count = broadcast_message_to_all_users("text", text)
                            count_persian = convert_to_persian_numerals(str(sent_count))
                            send_request("sendMessage", {"chat_id": chat_id, "text": f"✅ پیام به {count_persian} کاربر ارسال شد.", "parse_mode": "Markdown"})
                        continue

                    if chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_password"):
                        password = text
                        UPLOAD_STATES[chat_id]["password"] = password
                        del UPLOAD_STATES[chat_id]["waiting_for_password"]
                        UPLOAD_STATES[chat_id]["waiting_for_file"] = False
                        send_request("sendMessage", {"chat_id": chat_id, "text": "📤 لطفاً فایل را ارسال کنید."})
                        continue

                    if chat_id in PASSWORD_REQUEST_STATES:
                        link_id = PASSWORD_REQUEST_STATES[chat_id]
                        send_stored_file(chat_id, link_id, text)
                        continue

                if "document" in msg and chat_id in UPLOAD_STATES and not UPLOAD_STATES[chat_id].get("waiting_for_password") and not UPLOAD_STATES[chat_id].get("waiting_for_file"):
                    file_id = msg["document"]["file_id"]
                    file_name = msg["document"].get("file_name", "unnamed_file")
                    password = UPLOAD_STATES[chat_id].get("password")
                    handle_file_upload(chat_id, file_id, file_name, password)
                    del UPLOAD_STATES[chat_id]
                    continue

            elif "callback_query" in update:
                handle_callback(update["callback_query"])

        except Exception as e:
            logger.error(f"Error handling update: {e}")
            logger.exception(e)

def start_bot():
    """Start bot."""
    offset = 0
    logger.info("Bot started")
    while True:
        updates = send_request("getUpdates", {"offset": offset, "timeout": 10})
        if "result" in updates and updates["result"]:
            handle_updates(updates["result"])
            offset = updates["result"][-1]["update_id"] + 1
        time.sleep(0.1)

if __name__ == "__main__":
    start_bot()

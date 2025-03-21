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
TOKEN = "1991429784:TK47lTRzSIWLvHTySns6tcIwwDbtiTsGPRWPzCFw"
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
    """Send requests to Telegram API, handling errors."""
    url = API_URL + method
    try:
        response = session.post(url, json=data, timeout=5)  # Shorter timeout
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        logger.error(f"JSON decode error: {e}, Response: {response.text}")
        return {"ok": False}

def generate_link():
    """Generate a random link ID."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_persian_time():
    """Get Persian time with Persian numerals."""
    now = jdatetime.datetime.now()
    return convert_to_persian_numerals(now.strftime("%Y/%m/%d - %H:%M"))

def convert_to_persian_numerals(text):
    """Convert English numerals to Persian numerals."""
    persian_numerals = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return text.translate(persian_numerals)

def send_panel(chat_id):
    """Send the main panel to the user."""
    text = (
        f"🌟 بازگشت به پنل اصلی 🌟\n\n"
        f"📅 تاریخ: {get_persian_time()}\n\n"
        f"برای آپلود فایل جدید، روی دکمه‌ی '📤 آپلود فایل' کلیک کنید."
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "📤 آپلود فایل", "callback_data": "upload_file"}],
            [{"text": "📢 ارسال پیام", "callback_data": "broadcast_menu"}]
        ]
    }
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard})

def send_broadcast_menu(chat_id):
    """Send broadcast menu options."""
    text = "📢 مدیریت ارسال پیام\n\nلطفاً انتخاب کنید:"
    keyboard = {
        "inline_keyboard": [
            [{"text": "📝 متن", "callback_data": "broadcast_text"}],
            [{"text": "🔙 بازگشت", "callback_data": "back_to_panel"}]
        ]
    }
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard})

def ask_for_password(chat_id):
    """Asks if the file needs a password."""
    text = "🔒 آیا فایل رمز عبور دارد؟"
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ بله", "callback_data": "password_yes"},
             {"text": "❌ خیر", "callback_data": "password_no"}]
        ]
    }
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})

def handle_file_upload(chat_id, file_id, file_name, password=None):
    """Store file in MongoDB and send the download link."""
    link_id = generate_link()
    file_data = {
        "link_id": link_id, "file_id": file_id, "file_name": file_name,
        "likes": 0, "downloads": 0, "created_at": datetime.now(), "password": password
    }
    files_collection.insert_one(file_data)
    link_cache[link_id] = file_data.copy()  # Use copy and remove _id
    del link_cache[link_id]["_id"]

    start_link = f"/start {link_id}"
    text = f"✅ فایل ذخیره شد!\n🔗 لینک:\n```\n{start_link}\n```"
    if password:
        text += f"\n🔑 رمز: ```{password}```"

    keyboard = {
        "inline_keyboard": [
            [{"text": f"❤️ {convert_to_persian_numerals('0')}", "callback_data": f"like_{link_id}"}],
            [{"text": f"📥 {convert_to_persian_numerals('0')}", "callback_data": f"download_{link_id}"}]
        ]
    }
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard})

def get_file_data(link_id):
    """Get file data, prioritizing cache."""
    if link_id in link_cache:
        return link_cache[link_id]
    file_data = files_collection.find_one({"link_id": link_id})
    if file_data:
        link_cache[link_id] = file_data.copy()
        del link_cache[link_id]["_id"]
        return link_cache[link_id]
    return None

def send_stored_file(chat_id, link_id, provided_password=None):
    """Send stored file, handling password if needed."""
    file_data = get_file_data(link_id)
    if not file_data:
        send_request("sendMessage", {"chat_id": chat_id, "text": "❌ لینک نامعتبر."})
        return

    if file_data["password"] and provided_password != file_data["password"]:
        if chat_id not in PASSWORD_REQUEST_STATES:
            send_request("sendMessage", {"chat_id": chat_id, "text": "🔒 رمز را وارد کنید (/cancel برای لغو):"})
            PASSWORD_REQUEST_STATES[chat_id] = link_id
            return
        else:
            send_request("sendMessage", {"chat_id": chat_id, "text": "❌ رمز اشتباه. لغو شد."})
            PASSWORD_REQUEST_STATES.pop(chat_id, None)  # Safe pop
            return

    new_downloads = file_data["downloads"] + 1
    files_collection.update_one({"link_id": link_id}, {"$set": {"downloads": new_downloads}})
    if link_id in link_cache:  # Update cache
        link_cache[link_id]["downloads"] = new_downloads

    likes = convert_to_persian_numerals(str(file_data['likes']))
    downloads = convert_to_persian_numerals(str(new_downloads))
    keyboard = {
        "inline_keyboard": [
            [{"text": f"❤️ {likes}", "callback_data": f"like_{link_id}"}],
            [{"text": f"📥 {downloads}", "callback_data": f"download_{link_id}"}]
        ]
    }
    send_request("sendDocument", {"chat_id": chat_id, "document": file_data["file_id"], "reply_markup": keyboard})
    PASSWORD_REQUEST_STATES.pop(chat_id, None)

def broadcast_message(content):
    """Broadcast a text message."""
    sent_count = 0
    for user in users_collection.find({}):
        result = send_request("sendMessage", {"chat_id": user["chat_id"], "text": content, "parse_mode": "Markdown"})
        if result.get("ok"):
            sent_count += 1
    return sent_count

def handle_callback(query):
    """Handle inline keyboard button clicks."""
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]
    data = query["data"]
    user_id = query["from"]["id"]

    send_request("answerCallbackQuery", {"callback_query_id": query["id"]})  # Immediate ACK

    if data.startswith("like_"):
        link_id = data.split("_")[1]
        file_data = files_collection.find_one({"link_id": link_id})
        if not file_data or likes_collection.find_one({"user_id": user_id, "link_id": link_id}):
            return  # File gone or already liked

        likes_collection.insert_one({"user_id": user_id, "link_id": link_id, "time": datetime.now()})
        new_likes = file_data["likes"] + 1
        files_collection.update_one({"link_id": link_id}, {"$set": {"likes": new_likes}})
        if link_id in link_cache:
            link_cache[link_id]["likes"] = new_likes

        likes = convert_to_persian_numerals(str(new_likes))
        downloads = convert_to_persian_numerals(str(file_data['downloads']))
        updated_keyboard = {
            "inline_keyboard": [
                [{"text": f"❤️ {likes}", "callback_data": f"like_{link_id}"}],
                [{"text": f"📥 {downloads}", "callback_data": f"download_{link_id}"}]
            ]
        }
        send_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": updated_keyboard})

    elif data.startswith("download_"):
        send_stored_file(chat_id, data.split("_")[1])

    elif data == "upload_file":
        UPLOAD_STATES[chat_id] = {"waiting_for_file": True, "password": None}
        ask_for_password(chat_id)

    elif data == "password_yes":
        if chat_id in UPLOAD_STATES:
            UPLOAD_STATES[chat_id]["waiting_for_password"] = True
            send_request("sendMessage", {"chat_id": chat_id, "text": "🔑 رمز را وارد کنید:"})

    elif data == "password_no":
        if chat_id in UPLOAD_STATES:
            UPLOAD_STATES[chat_id]["waiting_for_file"] = False
            send_request("sendMessage", {"chat_id": chat_id, "text": "📤 فایل را بفرستید."})

    elif data == "broadcast_menu":
        if query["from"].get("username") in WHITELIST:
            send_broadcast_menu(chat_id)

    elif data == "broadcast_text":
        if query["from"].get("username") in WHITELIST:
            BROADCAST_STATES[chat_id] = "waiting_for_text"
            send_request("sendMessage", {"chat_id": chat_id, "text": "📝 متن پیام: (/cancel لغو)"})

    elif data == "back_to_panel":
        BROADCAST_STATES.pop(chat_id, None)
        send_panel(chat_id)

def handle_updates(updates):
    """Process incoming updates."""
    for update in updates:
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            username = msg["from"].get("username", "")
            first_name = msg["from"].get("first_name", "کاربر")  # Default to "کاربر"

            users_collection.update_one({"chat_id": chat_id}, {"$set": {"username": username, "first_name": first_name, "last_active": datetime.now()}}, upsert=True)

            if "text" in msg:
                text = msg["text"]

                if text == "/cancel":
                    UPLOAD_STATES.pop(chat_id, None)
                    PASSWORD_REQUEST_STATES.pop(chat_id, None)
                    BROADCAST_STATES.pop(chat_id, None)
                    send_request("sendMessage", {"chat_id": chat_id, "text": "❌ لغو شد."})
                    continue  # Use continue for clarity

                if text == "/start":
                    greet_text = f"👋 سلام {first_name} عزیز!\n\n📅 {get_persian_time()}\n\nبه ربات آپلودر خوش آمدید. برای آپلود فایل، از پنل استفاده کنید."
                    send_request("sendMessage", {"chat_id": chat_id, "text": greet_text, "parse_mode": "Markdown"})
                    continue # Very important to prevent further processing

                if text == "پنل" and username in WHITELIST:
                    send_panel(chat_id)
                    continue

                if text.startswith("/start "):
                    link_id = text.split(" ", 1)[1]  # Safer split
                    send_stored_file(chat_id, link_id)
                    continue

                if chat_id in BROADCAST_STATES and BROADCAST_STATES[chat_id] == "waiting_for_text":
                    if username in WHITELIST:
                        BROADCAST_STATES.pop(chat_id)
                        sent_count = broadcast_message(text)
                        send_request("sendMessage", {"chat_id": chat_id, "text": f"✅ پیام به {convert_to_persian_numerals(str(sent_count))} کاربر ارسال شد."})
                    continue

                if chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_password"):
                    UPLOAD_STATES[chat_id].update({"password": text, "waiting_for_file": False, "waiting_for_password": False})
                    send_request("sendMessage", {"chat_id": chat_id, "text": "📤 فایل را بفرستید."})
                    continue

                if chat_id in PASSWORD_REQUEST_STATES:
                    send_stored_file(chat_id, PASSWORD_REQUEST_STATES[chat_id], text)
                    continue

            if "document" in msg and chat_id in UPLOAD_STATES and not UPLOAD_STATES[chat_id].get("waiting_for_password") and not UPLOAD_STATES[chat_id].get("waiting_for_file"):
                file_id = msg["document"]["file_id"]
                file_name = msg["document"].get("file_name", "unnamed_file")
                password = UPLOAD_STATES[chat_id].get("password")
                handle_file_upload(chat_id, file_id, file_name, password)
                UPLOAD_STATES.pop(chat_id, None)  # Cleanup
                continue

        elif "callback_query" in update:
            handle_callback(update["callback_query"])

def start_bot():
    """Start the bot."""
    offset = 0
    logger.info("Bot started")
    while True:
        updates = send_request("getUpdates", {"offset": offset, "timeout": 5})  # Shorter timeout
        if updates and updates.get("result"):
            handle_updates(updates["result"])
            offset = updates["result"][-1]["update_id"] + 1
        time.sleep(0.05)  # Very short sleep for responsiveness


if __name__ == "__main__":
    start_bot()

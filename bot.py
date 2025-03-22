import requests
import random
import string
import jdatetime  # For Persian time
from datetime import datetime
from pymongo import MongoClient
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurations
TOKEN = "812616487:OQuogUM9cV1czIJRgDFZFSrz6MBRhjZevDtQCqTD"  # Replace with your token
MONGO_URI = "mongodb://mongo:kYrkkbAQKdReFyOknupBPTRhRuDlDdja@switchback.proxy.rlwy.net:52220"  # Your MongoDB URI
DB_NAME = "uploader_bot"
WHITELIST = ["zonercm", "id_hormoz"]  # Usernames allowed to use admin features

# State tracking dictionaries
BROADCAST_STATES = {}
UPLOAD_STATES = {}
PASSWORD_REQUEST_STATES = {}
TEXT_UPLOAD_STATES = {}  # New state for text uploads

# Initialize MongoDB
client = MongoClient(MONGO_URI, maxPoolSize=50)
db = client[DB_NAME]
files_collection = db["files"]
likes_collection = db["likes"]
users_collection = db["users"]
texts_collection = db["texts"]  # New collection for text messages

# Create indexes
files_collection.create_index("link_id")
likes_collection.create_index([("user_id", 1), ("link_id", 1)], unique=True)
users_collection.create_index("chat_id", unique=True)
texts_collection.create_index("text_id")  # Index for the text messages


# Telegram API URL
API_URL = f"https://tapi.bale.ai/bot{TOKEN}/"

# Cache
link_cache = {}
text_cache = {}  # New cache for text messages
session = requests.Session()

def send_request(method, data):
    """Send requests, handling errors."""
    url = API_URL + method
    try:
        response = session.post(url, json=data, timeout=10)  # Keep a reasonable timeout
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}, Method: {method}, Data: {data}")
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        logger.error(f"JSON decode error: {e}, Response: {response.text}")
        return {"ok": False, "error": str(e)}


def generate_link(prefix=""):
    """Generate a random link ID, optionally with a prefix."""
    return prefix + ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_persian_time():
    """Get ONLY Persian time (hour and minute), converted to numerals."""
    now = jdatetime.datetime.now()
    return convert_to_persian_numerals(now.strftime("%H:%M"))

def convert_to_persian_numerals(text):
    """Convert English numerals to Persian."""
    persian_numerals = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
    return text.translate(persian_numerals)

def send_panel(chat_id):
    """Send the main panel."""
    text = (
        f"🌟 بازگشت به پنل اصلی 🌟\n\n"
        f"⏰ ساعت: {get_persian_time()}\n\n"
        f"برای آپلود فایل، روی '📤 آپلود فایل' کلیک کنید.\n"
        f"برای آپلود متن، روی '📝 آپلود متن' کلیک کنید."
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "📤 آپلود فایل", "callback_data": "upload_file"}],
            [{"text": "📝 آپلود متن", "callback_data": "upload_text"}],  # New button
            [{"text": "📢 ارسال پیام", "callback_data": "broadcast_menu"}]
        ]
    }
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})

def send_broadcast_menu(chat_id):
    """Send broadcast menu."""
    text = "📢 مدیریت ارسال پیام\n\nنوع پیام را انتخاب کنید:"
    keyboard = {
        "inline_keyboard": [
            [{"text": "📝 متن", "callback_data": "broadcast_text"}],
            [{"text": "🔙 بازگشت", "callback_data": "back_to_panel"}]
        ]
    }
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})


def ask_for_password(chat_id):
    """Ask if the file needs a password."""
    text = "🔒 آیا فایل نیاز به رمز دارد؟"
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ بله", "callback_data": "password_yes"},
             {"text": "❌ خیر", "callback_data": "password_no"}]
        ]
    }
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})



def create_download_link_message(file_data, link_id):
    """Creates the download link message."""
    start_link = f"/start {link_id}"
    text = f"✅ فایل ذخیره شد!\n🔗 لینک:\n```\n{start_link}\n```"
    if file_data['password']:
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

def handle_file_upload(chat_id, file_id, file_name, password=None):
    """Handles file upload."""
    link_id = generate_link()
    file_data = {
        "link_id": link_id, "file_id": file_id, "file_name": file_name,
        "likes": 0, "downloads": 0, "created_at": datetime.now(), "password": password
    }
    files_collection.insert_one(file_data)
    file_data_for_cache = file_data.copy()
    del file_data_for_cache["_id"]
    link_cache[link_id] = file_data_for_cache
    text, keyboard = create_download_link_message(file_data, link_id)
    send_request("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard})


def get_file_data(link_id):
    """Get file data from cache or DB."""
    if link_id in link_cache:
        return link_cache[link_id]
    file_data = files_collection.find_one({"link_id": link_id})
    if file_data:
        file_data_for_cache = file_data.copy()
        del file_data_for_cache["_id"]
        link_cache[link_id] = file_data_for_cache
        return file_data_for_cache
    return None


def send_stored_file(chat_id, link_id, provided_password=None):
    """Sends the stored file."""
    file_data = get_file_data(link_id)
    if not file_data:
        send_request("sendMessage", {"chat_id": chat_id, "text": "❌ لینک نامعتبر."})
        return
    if file_data["password"] and provided_password != file_data["password"]:
         if chat_id not in PASSWORD_REQUEST_STATES:
            send_request("sendMessage", {"chat_id": chat_id, "text": "🔒 رمز را وارد کنید یا /cancel بزنید."})
            PASSWORD_REQUEST_STATES[chat_id] = link_id
            return
         else:
            send_request("sendMessage", {"chat_id": chat_id, "text": "❌ رمز اشتباه. دانلود لغو شد."})
            if chat_id in PASSWORD_REQUEST_STATES:
                del PASSWORD_REQUEST_STATES[chat_id]
            return
    file_data["downloads"] = file_data.get("downloads", 0) + 1
    files_collection.update_one({"link_id": link_id}, {"$set": {"downloads": file_data["downloads"]}})
    if link_id in link_cache:
        link_cache[link_id]["downloads"] = file_data["downloads"]
    text, keyboard = create_download_link_message(file_data, link_id)
    send_request("sendDocument", {"chat_id": chat_id, "document": file_data["file_id"], "reply_markup": keyboard})

    if chat_id in PASSWORD_REQUEST_STATES:
        del PASSWORD_REQUEST_STATES[chat_id]



def broadcast_message(message_type, content):
    """Broadcast a message."""
    sent_count = 0
    for user in users_collection.find({}):
        chat_id = user["chat_id"]
        if message_type == "text":
            result = send_request("sendMessage", {"chat_id": chat_id, "text": content, "parse_mode": "Markdown"})
        if result and result.get("ok"):
            sent_count += 1
    return sent_count

def handle_text_upload(chat_id, text_message):
    """Handles text upload, stores it, and sends a link."""
    text_id = generate_link("t")  # Use a prefix to distinguish text links
    text_data = {
        "text_id": text_id,
        "text": text_message,
        "created_at": datetime.now(),
    }
    texts_collection.insert_one(text_data)

    # Cache the text data
    text_data_for_cache = text_data.copy()
    del text_data_for_cache["_id"]
    text_cache[text_id] = text_data_for_cache

    start_link = f"/start {text_id}"
    response_text = (
        f"✅ متن ذخیره شد!\n🔗 لینک:\n```\n{start_link}\n```"
    )
    send_request("sendMessage", {"chat_id": chat_id, "text": response_text, "parse_mode": "Markdown"})

def get_text_data(text_id):
    """Retrieves text data from cache or database."""
    if text_id in text_cache:
        return text_cache[text_id]

    text_data = texts_collection.find_one({"text_id": text_id})
    if text_data:
        text_data_for_cache = text_data.copy()
        del text_data_for_cache["_id"]
        text_cache[text_id] = text_data_for_cache  # Update cache
        return text_data_for_cache

    return None

def send_stored_text(chat_id, text_id):
    """Sends the stored text message."""
    text_data = get_text_data(text_id)
    if not text_data:
        send_request("sendMessage", {"chat_id": chat_id, "text": "❌ لینک نامعتبر."})
        return

    send_request("sendMessage", {"chat_id": chat_id, "text": text_data["text"]})



def handle_callback(query):
    """Handles callback queries."""
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]
    data = query["data"]
    user_id = query["from"]["id"]
    username = query["from"].get("username", "")
    send_request("answerCallbackQuery", {"callback_query_id": query["id"]})

    if data.startswith("like_"):
        link_id = data.split("_")[1]
        file_data = get_file_data(link_id)
        if not file_data or likes_collection.find_one({"user_id": user_id, "link_id": link_id}):
            return
        likes_collection.insert_one({"user_id": user_id, "link_id": link_id, "timestamp": datetime.now()})
        file_data["likes"] = file_data.get("likes", 0) + 1
        files_collection.update_one({"link_id": link_id}, {"$set": {"likes": file_data["likes"]}})
        if link_id in link_cache:
            link_cache[link_id]["likes"] = file_data["likes"]
        text, keyboard = create_download_link_message(file_data, link_id)
        send_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": keyboard})

    elif data.startswith("download_"):
        return

    elif data == "upload_file":
        UPLOAD_STATES[chat_id] = {"waiting_for_password": True, "password": None}
        ask_for_password(chat_id)
    elif data == "password_yes":
        if chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_password"):
            UPLOAD_STATES[chat_id]["waiting_for_password_input"] = True
            send_request("sendMessage", {"chat_id": chat_id, "text": "🔑 رمز را وارد کنید:"})
    elif data == "password_no":
         if chat_id in UPLOAD_STATES:
            UPLOAD_STATES[chat_id] = {"waiting_for_file": True, "password": None}
            send_request("sendMessage", {"chat_id": chat_id, "text": "📤 فایل را بفرستید."})
    elif data == "upload_text":
        TEXT_UPLOAD_STATES[chat_id] = "waiting_for_text"
        send_request("sendMessage", {"chat_id": chat_id, "text": "📝 متن خود را برای آپلود وارد کنید:"})

    elif data == "broadcast_menu":
        if username in WHITELIST:
            send_broadcast_menu(chat_id)
        else:
            send_request("answerCallbackQuery", {"callback_query_id": query["id"], "text": "دسترسی ندارید!", "show_alert": True})
    elif data == "broadcast_text":
        if username in WHITELIST:
            BROADCAST_STATES[chat_id] = "waiting_for_text"
            send_request("sendMessage", {"chat_id": chat_id, "text": "📝 متن را وارد کنید:", "parse_mode": "Markdown"})
        else:
            send_request("answerCallbackQuery", {"callback_query_id": query["id"], "text": "دسترسی ندارید!", "show_alert": True})
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
                        elif chat_id in UPLOAD_STATES:
                            del UPLOAD_STATES[chat_id]
                        elif chat_id in PASSWORD_REQUEST_STATES:
                            del PASSWORD_REQUEST_STATES[chat_id]
                        elif chat_id in TEXT_UPLOAD_STATES:  # Cancel text upload
                            del TEXT_UPLOAD_STATES[chat_id]
                            send_request("sendMessage", {"chat_id": chat_id, "text": "❌ آپلود متن لغو شد."})
                        return

                    if text == "/start":
                        greet_text = (
                            f"👋 سلام {first_name} عزیز، خوش آمدید!\n\n"
                            f"⏰ ساعت: {get_persian_time()}"
                        )
                        send_request("sendMessage", {"chat_id": chat_id, "text": greet_text, "parse_mode": "Markdown"})
                        continue

                    if text == "پنل" and username in WHITELIST:
                        send_panel(chat_id)
                        continue

                    if text.startswith("/start "):
                        link_id = text.split(" ", 1)[1]
                        if link_id.startswith("t"):
                            send_stored_text(chat_id, link_id)  # Handle text links
                        else:
                            send_stored_file(chat_id, link_id) # Handle Files
                        continue

                    if chat_id in BROADCAST_STATES and BROADCAST_STATES[chat_id] == "waiting_for_text":
                        if username in WHITELIST:
                            del BROADCAST_STATES[chat_id]
                            send_request("sendMessage", {"chat_id": chat_id, "text": "📤 در حال ارسال...", "parse_mode": "Markdown"})
                            sent_count = broadcast_message("text", text)
                            send_request("sendMessage", {"chat_id": chat_id, "text": f"✅ به {convert_to_persian_numerals(str(sent_count))} کاربر ارسال شد."})
                        continue

                    if chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_password_input"):
                        password = text
                        UPLOAD_STATES[chat_id]["password"] = password
                        del UPLOAD_STATES[chat_id]["waiting_for_password_input"]
                        UPLOAD_STATES[chat_id]["waiting_for_file"] = True
                        send_request("sendMessage", {"chat_id": chat_id, "text": "📤 فایل را بفرستید."})
                        continue

                    if chat_id in PASSWORD_REQUEST_STATES:
                        link_id = PASSWORD_REQUEST_STATES[chat_id]
                        send_stored_file(chat_id, link_id, text)
                        continue

                    if chat_id in TEXT_UPLOAD_STATES and TEXT_UPLOAD_STATES[chat_id] == "waiting_for_text":
                        del TEXT_UPLOAD_STATES[chat_id]
                        handle_text_upload(chat_id, text)  # Process the uploaded text
                        continue

                if "document" in msg and chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_file"):
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
    """Starts the bot."""
    offset = 0
    logger.info("Bot started")
    while True:
        try:
            updates = send_request("getUpdates", {"offset": offset, "timeout": 180, "limit": 100})
            if updates and updates.get("result"):
                handle_updates(updates["result"])
                offset = updates["result"][-1]["update_id"] + 1
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            logger.exception(e)
            time.sleep(5)

if __name__ == "__main__":
    start_bot()

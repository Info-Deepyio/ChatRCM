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
TOKEN = "1991429784:TK47lTRzSIWLvHTySns6tcIwwDbtiTsGPRWPzCFw"  # USE THIS VALUE
MONGO_URI = "mongodb://mongo:kYrkkbAQKdReFyOknupBPTRhRuDlDdja@switchback.proxy.rlwy.net:52220"  # USE THIS VALUE
DB_NAME = "uploader_bot"
WHITELIST = ["zonercm", "id_hormoz"]  # Add whitelisted usernames
BROADCAST_STATES = {}  # Track broadcast state for admins
UPLOAD_STATES = {}  # Track file upload state, including password
PASSWORD_REQUEST_STATES = {} # Track whether a download is waiting for password


# Initialize MongoDB with connection pooling
client = MongoClient(MONGO_URI, maxPoolSize=50)
db = client[DB_NAME]
files_collection = db["files"]
likes_collection = db["likes"]
users_collection = db["users"]  # New collection to store user IDs for broadcasting

# Create indexes for better performance
files_collection.create_index("link_id")
likes_collection.create_index([("user_id", 1), ("link_id", 1)], unique=True)
users_collection.create_index("chat_id", unique=True)

# Telegram API URL
API_URL = f"https://tapi.bale.ai/bot{TOKEN}/"


# Cache frequently used data
link_cache = {}
session = requests.Session()

def send_request(method, data):
    """Send requests to Telegram API with session reuse"""
    url = API_URL + method
    try:
        response = session.post(url, json=data, timeout=10)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return {"ok": False, "error": str(e)}
    except ValueError as e: #json decode error
        logger.error(f"JSON decode error: {e}, Response content: {response.text}")
        return {"ok": False, "error": str(e)}

def generate_link():
    """Generate a random link ID"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_persian_time():
    """Get Persian time with Persian numerals"""
    now = jdatetime.datetime.now()
    persian_date = now.strftime("%Y/%m/%d")
    persian_time = now.strftime("%H:%M")

    # Convert English numerals to Persian
    persian_date = convert_to_persian_numerals(persian_date)
    persian_time = convert_to_persian_numerals(persian_time)

    return f"{persian_date} - {persian_time}"

def convert_to_persian_numerals(text):
    """Convert English numerals to Persian numerals"""
    persian_numerals = {
        '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
        '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
    }
    for en, fa in persian_numerals.items():
        text = text.replace(en, fa)
    return text

def send_panel(chat_id, first_time=False):
    """Send Persian panel with date/time and broadcast option for admins"""
    current_time = get_persian_time()
    if first_time:
        text = (
            f"🎉 به ربات آپلودر خوش آمدید! 🎉\n\n"
            f"📅 تاریخ: {current_time}\n\n"
            f"با استفاده از این ربات می‌توانید فایل‌های خود را به راحتی آپلود کرده و لینک دانلود مستقیم دریافت کنید.\n\n"
            f"برای شروع، روی دکمه‌ی '📤 آپلود فایل' کلیک کنید."
        )
    else:
         text = (
            f"🌟 بازگشت به پنل اصلی 🌟\n\n"
            f"📅 تاریخ: {current_time}\n\n"
            f"برای آپلود فایل جدید، روی دکمه‌ی '📤 آپلود فایل' کلیک کنید."
        )


    keyboard = {
        "inline_keyboard": [
            [{"text": "📤 آپلود فایل", "callback_data": "upload_file"}],
            [{"text": "📢 ارسال پیام به کل کاربر ها", "callback_data": "broadcast_menu"}] #Admin only
        ]
    }

    send_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    })

def send_broadcast_menu(chat_id):
    """Send broadcast menu options"""
    text = "📢 مدیریت ارسال پیام گروهی\n\nلطفاً نوع پیام گروهی را انتخاب کنید:"

    keyboard = {
        "inline_keyboard": [
            [{"text": "📝 ارسال متن ساده", "callback_data": "broadcast_text"}],
            [{"text": "🔙 بازگشت به منو اصلی", "callback_data": "back_to_panel"}]
        ]
    }

    send_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    })
def ask_for_password(chat_id):
    """Asks the user if the file requires a password."""
    text = "🔒 آیا فایل شما نیاز به رمز عبور دارد؟"
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ بله", "callback_data": "password_yes"},
             {"text": "❌ خیر", "callback_data": "password_no"}]
        ]
    }
    send_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": keyboard
    })


def handle_file_upload(chat_id, file_id, file_name, password=None):
    """Store file in MongoDB and instantly send the download link with like & download buttons"""
    link_id = generate_link()
    file_data = {
        "link_id": link_id,
        "file_id": file_id,
        "file_name": file_name,
        "likes": 0,
        "downloads": 0,
        "created_at": datetime.now(),
        "password": password  # Store the password (can be None)
    }
    files_collection.insert_one(file_data)

    # Add to cache
    link_cache[link_id] = file_data.copy() # Use a copy to avoid modifying the cache directly
    del link_cache[link_id]["_id"] # Remove the _id field as it's not serializable

    start_link = f"/start {link_id}"
    text = f"✅ فایل شما ذخیره شد!\n🔗 لینک دریافت:\n```\n{start_link}\n```"

    if password:
        text += f"\n🔑 رمز عبور فایل: ```{password}```"

    like_count = convert_to_persian_numerals("0")
    download_count = convert_to_persian_numerals("0")

    keyboard = {
        "inline_keyboard": [
            [{"text": f"❤️ {like_count}", "callback_data": f"like_{link_id}"}],
            [{"text": f"📥 تعداد دانلود ها: {download_count}", "callback_data": f"download_{link_id}"}]
        ]
    }

    send_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    })



def get_file_data(link_id):
    """Get file data from cache or database"""
    if link_id in link_cache:
        return link_cache[link_id]

    file_data = files_collection.find_one({"link_id": link_id})
    if file_data:
        # Cache the result
        link_cache[link_id] = file_data.copy() # Use a copy to avoid modifying the cache directly
        del link_cache[link_id]["_id"]
        return link_cache[link_id]

    return None

def send_stored_file(chat_id, link_id, provided_password=None):
    """Retrieve and instantly send stored file, handling password if needed."""
    file_data = get_file_data(link_id)


    if file_data:
        # Check for password
        if file_data["password"] and provided_password != file_data["password"]:
            # Incorrect or missing password
            if chat_id not in PASSWORD_REQUEST_STATES:  # First incorrect attempt
              send_request("sendMessage",{
                    "chat_id": chat_id,
                    "text": "🔒 لطفاً رمز عبور فایل را وارد کنید یا /cancel را برای لغو وارد کنید.",
                })
              PASSWORD_REQUEST_STATES[chat_id] = link_id
              return
            else:  #Second incorrect attempt
              send_request("sendMessage", {
                  "chat_id": chat_id,
                  "text": "❌ رمز عبور اشتباه است.  دانلود لغو شد."
              })
              if chat_id in PASSWORD_REQUEST_STATES: #cleanup
                del PASSWORD_REQUEST_STATES[chat_id]
              return



        # Update download count
        new_download_count = file_data["downloads"] + 1
        file_data["downloads"] = new_download_count  # Update the local copy (important for cache)

        files_collection.update_one(
            {"link_id": link_id},
            {"$set": {"downloads": new_download_count}}
        )
        #update the cache
        if link_id in link_cache:
          link_cache[link_id]["downloads"] = new_download_count

        # Convert counts to Persian numerals
        likes_count = convert_to_persian_numerals(str(file_data['likes']))
        downloads_count = convert_to_persian_numerals(str(new_download_count))

        # Send file with updated buttons
        keyboard = {
            "inline_keyboard": [
                [{"text": f"❤️ {likes_count}", "callback_data": f"like_{link_id}"}],
                [{"text": f"📥 تعداد دانلود ها: {downloads_count}", "callback_data": f"download_{link_id}"}]
            ]
        }

        send_request("sendDocument", {
            "chat_id": chat_id,
            "document": file_data["file_id"],
            "reply_markup": keyboard
        })
        if chat_id in PASSWORD_REQUEST_STATES: #cleanup
          del PASSWORD_REQUEST_STATES[chat_id]

    else:
        send_request("sendMessage", {
            "chat_id": chat_id,
            "text": "❌ لینک نامعتبر است یا فایل حذف شده است."
        })

def broadcast_message_to_all_users(message_type, content):
    """Send a message to all registered users"""
    users = users_collection.find({})
    sent_count = 0

    for user in users:
        chat_id = user["chat_id"]

        if message_type == "text":
            result = send_request("sendMessage", {
                "chat_id": chat_id,
                "text": content,
                "parse_mode": "Markdown"
            })

        if result.get("ok", False):
            sent_count += 1
        else:
            logger.error(f"Could not send message to user: {chat_id}, Result: {result}")

    return sent_count


def handle_callback(query):
    """Handle button clicks for likes, downloads, and admin functions"""
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]  # Get message_id for editing
    callback_id = query["id"]
    data = query["data"]
    user_id = query["from"]["id"]
    username = query["from"].get("username", "")

    # Immediately acknowledge *all* callback queries for responsiveness
    send_request("answerCallbackQuery", {"callback_query_id": callback_id})


    if data.startswith("like_"):
        link_id = data.split("_")[1]
        file_data = files_collection.find_one({"link_id": link_id})

        if file_data:
            # Check if user already liked
            existing_like = likes_collection.find_one({"user_id": user_id, "link_id": link_id})
            if existing_like:
                return  # Exit early

            # Add new like
            likes_collection.insert_one({"user_id": user_id, "link_id": link_id, "timestamp": datetime.now()})

            # Update like count
            new_likes = file_data["likes"] + 1
            files_collection.update_one({"link_id": link_id}, {"$set": {"likes": new_likes}})

            # Update cache
            if link_id in link_cache:
                link_cache[link_id]["likes"] = new_likes

            # Convert to Persian numerals
            likes_count = convert_to_persian_numerals(str(new_likes))
            downloads_count = convert_to_persian_numerals(str(file_data['downloads']))

            # Update the button
            updated_keyboard = {
                "inline_keyboard": [
                    [{"text": f"❤️ {likes_count}", "callback_data": f"like_{link_id}"}],
                    [{"text": f"📥 تعداد دانلود ها: {downloads_count}", "callback_data": f"download_{link_id}"}]
                ]
            }
            send_request("editMessageReplyMarkup", {
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": updated_keyboard
            })


    elif data.startswith("download_"):
        link_id = data.split("_")[1]
        send_stored_file(chat_id, link_id) #No password yet


    elif data == "upload_file":
        UPLOAD_STATES[chat_id] = {"waiting_for_file": True, "password": None}
        ask_for_password(chat_id)


    elif data == "password_yes":
        if chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_file"):
            UPLOAD_STATES[chat_id]["waiting_for_password"] = True
            send_request("sendMessage", {
                "chat_id": chat_id,
                "text": "🔑 لطفاً رمز عبور فایل را وارد کنید:"
            })
        else: #Edge case
            send_request("sendMessage", {
                "chat_id": chat_id,
                "text": "لطفاً ابتدا فایل را آپلود کنید."
            })


    elif data == "password_no":
        if chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_file"):
            UPLOAD_STATES[chat_id]["waiting_for_file"] = False #Ready for file now
            del UPLOAD_STATES[chat_id]["waiting_for_password"] #Clean up just in case

            send_request("sendMessage", {
                "chat_id": chat_id,
                "text": "📤 لطفاً فایل خود را برای آپلود ارسال کنید."
            })
        else: #Edge case
             send_request("sendMessage", {
                "chat_id": chat_id,
                "text": "لطفاً ابتدا فایل را آپلود کنید."
            })



    # Admin broadcast functions
    elif data == "broadcast_menu":
        if username in WHITELIST:
            send_broadcast_menu(chat_id)
        else: #No access
            send_request("answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "شما مجوز دسترسی به این بخش را ندارید!",
                "show_alert": True
            })

    elif data == "broadcast_text":
        if username in WHITELIST:
            # Set state to wait for text message
            BROADCAST_STATES[chat_id] = "waiting_for_text"
            send_request("sendMessage", {
                "chat_id": chat_id,
                "text": "📝 *لطفاً متن پیام گروهی را وارد کنید:*\n\nمی‌توانید از مارک‌داون استفاده کنید.\nبرای لغو، بنویسید /cancel",
                "parse_mode": "Markdown"
            })

    elif data == "back_to_panel":
        # Clear any broadcast state
        if chat_id in BROADCAST_STATES:
            del BROADCAST_STATES[chat_id]
        send_panel(chat_id)



def handle_updates(updates):
    """Process multiple updates efficiently"""
    for update in updates:
        try:
            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                username = msg["from"].get("username", "")

                # Store user in database for future broadcasts
                users_collection.update_one(
                    {"chat_id": chat_id},
                    {"$set": {"username": username, "last_active": datetime.now()}},
                    upsert=True
                )

                if "text" in msg:
                    text = msg["text"]

                    if text == "/cancel":
                        if chat_id in BROADCAST_STATES:
                            del BROADCAST_STATES[chat_id]
                            send_request("sendMessage", {
                                "chat_id": chat_id,
                                "text": "❌ عملیات کنونی لغو شد.",
                                "parse_mode": "Markdown"
                            })
                        elif chat_id in UPLOAD_STATES:
                            del UPLOAD_STATES[chat_id]
                            send_request("sendMessage", {
                                "chat_id": chat_id,
                                "text": "❌ آپلود فایل لغو شد.",
                                "parse_mode": "Markdown"

                            })
                        elif chat_id in PASSWORD_REQUEST_STATES:
                            del PASSWORD_REQUEST_STATES[chat_id]
                            send_request("sendMessage",{
                                "chat_id": chat_id,
                                "text": "❌ دانلود فایل لغو شد.",
                                "parse_mode": "Markdown"
                            })
                        return
                    if text == "/start":
                        send_panel(chat_id, first_time=True)  # Greet new users
                        continue


                    if text == "پنل" and username in WHITELIST:
                        send_panel(chat_id)
                        continue

                    if text.startswith("/start "):
                        parts = text.split()
                        if len(parts) > 1:
                            link_id = parts[1]
                            send_stored_file(chat_id, link_id)  # Initial request, no password yet
                        else:
                            send_panel(chat_id)
                        continue
                    # Handle broadcast text message
                    if chat_id in BROADCAST_STATES and BROADCAST_STATES[chat_id] == "waiting_for_text":
                        if username in WHITELIST:
                            # Reset state
                            del BROADCAST_STATES[chat_id]

                            send_request("sendMessage", {
                                "chat_id": chat_id,
                                "text": "📤 *در حال ارسال پیام به کاربران...*",
                                "parse_mode": "Markdown"
                            })

                            # Broadcast the text message
                            sent_count = broadcast_message_to_all_users("text", text)

                            # Confirm the broadcast
                            count_persian = convert_to_persian_numerals(str(sent_count))
                            send_request("sendMessage", {
                                "chat_id": chat_id,
                                "text": f"✅ پیام شما به {count_persian} کاربر ارسال شد.",
                                "parse_mode": "Markdown"
                            })
                        continue
                    #Handle password input during upload
                    if chat_id in UPLOAD_STATES and UPLOAD_STATES[chat_id].get("waiting_for_password"):
                        password = text
                        UPLOAD_STATES[chat_id]["password"] = password
                        del UPLOAD_STATES[chat_id]["waiting_for_password"]
                        UPLOAD_STATES[chat_id]["waiting_for_file"] = False # Now we wait for the actual file
                        send_request("sendMessage", {
                            "chat_id": chat_id,
                            "text": "📤 لطفاً فایل خود را برای آپلود ارسال کنید."
                        })
                        continue

                    #Handle password input during download
                    if chat_id in PASSWORD_REQUEST_STATES:
                        link_id = PASSWORD_REQUEST_STATES[chat_id]
                        send_stored_file(chat_id,link_id, text) #Try again with password
                        continue

                if "document" in msg and chat_id in UPLOAD_STATES and not UPLOAD_STATES[chat_id].get("waiting_for_password") and not UPLOAD_STATES[chat_id].get("waiting_for_file"):
                    file_id = msg["document"]["file_id"]
                    file_name = msg["document"].get("file_name", "unnamed_file")
                    password = UPLOAD_STATES[chat_id].get("password") # Get the password, might be None

                    handle_file_upload(chat_id, file_id, file_name, password)
                    del UPLOAD_STATES[chat_id]  # Clean up after upload
                    continue




            elif "callback_query" in update:
                handle_callback(update["callback_query"])

        except Exception as e:
            logger.error(f"Error handling update: {e}")
            logger.exception(e)  # Log the full traceback


def start_bot():
    """Start bot with optimized long polling"""
    offset = 0
    logger.info("Bot started")
    while True:
        updates = send_request("getUpdates", {"offset": offset, "timeout": 10})  # Use a longer timeout
        if "result" in updates and updates["result"]:
            handle_updates(updates["result"])
            offset = updates["result"][-1]["update_id"] + 1
        time.sleep(0.1) # Add a small delay

if __name__ == "__main__":
    start_bot()

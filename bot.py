import requests
import random
import string
import time
from datetime import datetime
from pymongo import MongoClient
import logging
import json

# Configurations
TOKEN = "812616487:cRPquvMfuFLC3rOWiHMu3yay8WCu8E1iX6CfWF1c"
MONGO_URI = "mongodb://mongo:kYrkkbAQKdReFyOknupBPTRhRuDlDdja@switchback.proxy.rlwy.net:52220"
DB_NAME = "uploader_bot"
WHITELIST = ["zonercm", "your_username_here"]

# Initialize MongoDB
client = MongoClient(MONGO_URI, maxPoolSize=50)
db = client[DB_NAME]
files_collection = db["files"]
files_collection.create_index("link_id")

# Telegram API URL
API_URL = f"https://tapi.bale.ai/bot{TOKEN}/"

def send_request(method, data):
    """Send requests to Bale API"""
    url = API_URL + method
    try:
        return requests.post(url, json=data, timeout=10).json()
    except Exception as e:
        logging.error(f"API request error: {e}")
        return {"ok": False}

def generate_link():
    """Generate a random link ID"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_persian_time():
    """Get Persian time"""
    now = datetime.now()
    return now.strftime("%Y/%m/%d - %H:%M")

def send_panel(chat_id):
    """Send Persian panel with date/time"""
    text = f"🌟 *خوش آمدید!* 🌟\n📆 تاریخ: `{get_persian_time()}`\n📂 برای آپلود فایل، دکمه زیر را فشار دهید."

    keyboard = {
        "inline_keyboard": [
            [{"text": "📤 آپلود فایل", "callback_data": "upload_file"}]
        ]
    }

    send_request("sendMessage", {
        "chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": json.dumps(keyboard)
    })

def handle_file_upload(chat_id, file_id, file_name):
    """Store file in MongoDB and send download link"""
    link_id = generate_link()
    files_collection.insert_one({
        "link_id": link_id, "file_id": file_id, "file_name": file_name, "likes": 0, "downloads": 0
    })

    start_link = f"/start {link_id}"
    text = f"✅ فایل شما ذخیره شد!\n🔗 لینک دریافت:\n```\n{start_link}\n```"

    keyboard = {
        "inline_keyboard": [
            [{"text": "❤️ 0", "callback_data": f"like_{link_id}"}],
            [{"text": "📥 0 دریافت", "callback_data": f"download_{link_id}"}]
        ]
    }

    send_request("sendMessage", {
        "chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": json.dumps(keyboard)
    })

def handle_callback(query):
    """Handle inline button clicks properly"""
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]
    callback_id = query["id"]
    data = query["data"]

    send_request("answerCallbackQuery", {"callback_query_id": callback_id})  # Acknowledge

    if data.startswith("like_"):
        link_id = data.split("_")[1]
        file_data = files_collection.find_one({"link_id": link_id})

        if file_data:
            new_likes = file_data["likes"] + 1
            files_collection.update_one({"link_id": link_id}, {"$set": {"likes": new_likes}})

            keyboard = {
                "inline_keyboard": [
                    [{"text": f"❤️ {new_likes}", "callback_data": f"like_{link_id}"}],
                    [{"text": f"📥 {file_data['downloads']} دریافت", "callback_data": f"download_{link_id}"}]
                ]
            }

            send_request("editMessageReplyMarkup", {
                "chat_id": chat_id, "message_id": message_id, "reply_markup": json.dumps(keyboard)
            })

    elif data.startswith("download_"):
        link_id = data.split("_")[1]
        file_data = files_collection.find_one({"link_id": link_id})

        if file_data:
            new_downloads = file_data["downloads"] + 1
            files_collection.update_one({"link_id": link_id}, {"$set": {"downloads": new_downloads}})

            keyboard = {
                "inline_keyboard": [
                    [{"text": f"❤️ {file_data['likes']}", "callback_data": f"like_{link_id}"}],
                    [{"text": f"📥 {new_downloads} دریافت", "callback_data": f"download_{link_id}"}]
                ]
            }

            send_request("editMessageReplyMarkup", {
                "chat_id": chat_id, "message_id": message_id, "reply_markup": json.dumps(keyboard)
            })

def handle_updates(updates):
    """Process multiple updates efficiently"""
    for update in updates:
        try:
            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                username = msg["from"].get("username", "")

                if "text" in msg:
                    text = msg["text"]

                    if text == "پنل" and username in WHITELIST:
                        send_panel(chat_id)

                    elif text.startswith("/start "):
                        parts = text.split()
                        if len(parts) > 1:
                            link_id = parts[1]
                            file_data = files_collection.find_one({"link_id": link_id})

                            if file_data:
                                keyboard = {
                                    "inline_keyboard": [
                                        [{"text": f"❤️ {file_data['likes']}", "callback_data": f"like_{link_id}"}],
                                        [{"text": f"📥 {file_data['downloads']} دریافت", "callback_data": f"download_{link_id}"}]
                                    ]
                                }

                                send_request("sendDocument", {
                                    "chat_id": chat_id,
                                    "document": file_data["file_id"],
                                    "reply_markup": json.dumps(keyboard)
                                })
                            else:
                                send_request("sendMessage", {
                                    "chat_id": chat_id,
                                    "text": "❌ لینک نامعتبر است یا فایل حذف شده است."
                                })

                elif "document" in msg:
                    file_id = msg["document"]["file_id"]
                    file_name = msg["document"].get("file_name", "unnamed_file")
                    handle_file_upload(chat_id, file_id, file_name)

            elif "callback_query" in update:
                handle_callback(update["callback_query"])
        except Exception as e:
            logging.error(f"Error handling update: {e}")

def start_bot():
    """Start bot with optimized long polling"""
    offset = 0
    while True:
        updates = send_request("getUpdates", {"offset": offset, "timeout": 30})
        if "result" in updates and updates["result"]:
            handle_updates(updates["result"])
            offset = updates["result"][-1]["update_id"] + 1

if __name__ == "__main__":
    logging.info("Bot started")
    start_bot()
